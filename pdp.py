# main.py
import os
import logging
from threading import Thread
from urllib.parse import urlparse
from time import sleep

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

import discord
from discord.ext import commands

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# load env
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')  # optionnel

if not TOKEN:
    logger.error("DISCORD_TOKEN manquant")
    raise SystemExit(1)
if not DATABASE_URL:
    logger.error("DATABASE_URL manquant")
    raise SystemExit(1)

# DB pool
try:
    url = urlparse(DATABASE_URL)
    connection_pool = psycopg2.pool.SimpleConnectionPool(
        1, 10,
        host=url.hostname,
        port=url.port or 5432,
        database=url.path[1:],
        user=url.username,
        password=url.password,
        sslmode='require' if url.hostname and 'render' in url.hostname else 'prefer'
    )
    logger.info("Pool PostgreSQL initialisé")
except Exception as e:
    logger.exception("Erreur initialisation pool DB")
    connection_pool = None

def get_db_connection():
    try:
        if connection_pool:
            return connection_pool.getconn()
        else:
            return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        logger.error("Erreur connexion DB: %s", e)
        return None

def return_db_connection(conn):
    try:
        if connection_pool and conn:
            connection_pool.putconn(conn)
        elif conn:
            conn.close()
    except Exception as e:
        logger.error("Erreur retour connexion: %s", e)

# Flask
app = Flask(__name__)
CORS(app)

@app.route('/', methods=['GET'])
def index():
    # Endpoint racine : informations simples
    info = {
        "bot": bot.user.name if bot and bot.is_ready() else None,
        "guilds": len(bot.guilds) if bot and bot.is_ready() else 0,
        "status": "online" if bot and bot.is_ready() else "starting",
        "users": len(bot.users) if bot and bot.is_ready() else 0
    }
    return jsonify(info)

@app.route('/health', methods=['GET'])
def health():
    # retourne 200 si bot prêt
    is_ready = bot.is_ready()
    return jsonify({"bot_ready": is_ready, "status": ("ok" if is_ready else "starting")}), (200 if is_ready else 503)

@app.route('/stats', methods=['GET'])
def stats_api():
    # retourne pending/sent/guilds/users et stock par catégorie si disponible
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "DB connection failed"}), 500
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) as count FROM images WHERE status='pending'")
        pending = cur.fetchone()['count']
        cur.execute("SELECT COUNT(*) as count FROM images WHERE status='sent'")
        sent = cur.fetchone()['count']
        cur.execute("SELECT category, COUNT(*) as count FROM images WHERE status='pending' GROUP BY category")
        stock = {r['category']: r['count'] for r in cur.fetchall()}
        cur.close()
        return_db_connection(conn)
        return jsonify({
            "guilds": len(bot.guilds) if bot and bot.is_ready() else 0,
            "users": len(bot.users) if bot and bot.is_ready() else 0,
            "pending": pending,
            "sent": sent,
            "stock": stock
        })
    except Exception as e:
        logger.exception("Erreur /stats")
        return jsonify({"error": str(e)}), 500

# Scraping implementation
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
                  " Chrome/115.0.0.0 Safari/537.36"
}

def extract_image_urls_from_html(html, base_url=None, limit=200):
    """Retourne une liste d'URLs d'images depuis le HTML"""
    urls = []
    soup = BeautifulSoup(html, 'html.parser')

    # Méthode 1: chercher les balises meta og:image / twitter:image
    meta_og = soup.find_all('meta', {"property": "og:image"})
    for m in meta_og:
        v = m.get('content')
        if v and v not in urls:
            urls.append(v)
            if len(urls) >= limit: return urls

    # Method 2: images <img>
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-image-src') or img.get('srcset')
        if not src: continue
        # si srcset contient plusieurs valeurs, prendre la première URL
        if src and ',' in src:
            src = src.split(',')[0].strip().split(' ')[0]
        if src and src not in urls:
            urls.append(src)
            if len(urls) >= limit: return urls

    # Method 3: chercher URLs complètes dans le HTML (regex)
    import re
    found = re.findall(r'https?://i\.pinimg\.com/[^"\']+', html)
    for u in found:
        if u not in urls:
            urls.append(u)
            if len(urls) >= limit: return urls

    return urls

def scrape_pinterest(url, limit=200, timeout=10):
    """Lit une page pinterest et retourne liste d'URLs d'images (max limit)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        html = r.text
        urls = extract_image_urls_from_html(html, base_url=url, limit=limit)
        # Deduplicate and normalise
        clean = []
        for u in urls:
            if u.startswith('//'):
                u = 'https:' + u
            if u not in clean:
                clean.append(u)
            if len(clean) >= limit: break
        return clean
    except Exception as e:
        logger.exception("Erreur scrapping Pinterest: %s", e)
        return []

@app.route('/scrape', methods=['POST'])
def scrape_endpoint():
    """
    POST /scrape
    body: { "url": "...", "category": "anime", "limit": 50 }
    """
    data = request.get_json(force=True, silent=True) or {}
    url = data.get('url') or request.form.get('url')
    category = (data.get('category') or request.form.get('category') or 'uncategorized').strip()
    try:
        limit = int(data.get('limit') or request.form.get('limit') or 50)
    except:
        limit = 50
    if not url:
        return jsonify({"error": "url manquante"}), 400

    logger.info("Scraping demandé: %s (cat=%s limit=%d)", url, category, limit)
    # scraper
    found = scrape_pinterest(url, limit=limit)
    if not found:
        return jsonify({"inserted": 0, "found": 0, "message": "Aucune image trouvée"}), 200

    # Insert into DB (skip duplicates)
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "DB connection failed"}), 500
    cur = conn.cursor()
    inserted = 0
    try:
        for img_url in found:
            # optional: normalize URL or check existing
            cur.execute("SELECT id FROM images WHERE image_url = %s", (img_url,))
            if cur.fetchone():
                continue
            cur.execute(
                "INSERT INTO images (image_url, category, status) VALUES (%s,%s,%s) RETURNING id",
                (img_url, category, 'pending')
            )
            inserted += 1
            if inserted >= limit:
                break
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.exception("Erreur insertion images")
    finally:
        cur.close()
        return_db_connection(conn)

    logger.info("Scrape terminé: %d insérées", inserted)
    return jsonify({"inserted": inserted, "found": len(found)}), 200

# === Discord bot setup (votre code existant) ===
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

@bot.event
async def on_ready():
    logger.info(f'Bot connecté: {bot.user} — guilds: {len(bot.guilds)}')
    await bot.change_presence(activity=discord.Game(name="!help"))

# example simple pdp command (lit DB)
@bot.command(name='pdp')
async def pdp(ctx, category: str = None):
    if not category:
        await ctx.send("Spécifiez une catégorie.")
        return
    conn = get_db_connection()
    if not conn:
        await ctx.send("Erreur DB")
        return
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, image_url FROM images
        WHERE category = %s AND status = 'pending'
        ORDER BY RANDOM()
        LIMIT 15
    """, (category,))
    rows = cur.fetchall()
    if not rows:
        await ctx.send(f"Aucune image disponible pour {category}")
        return_db_connection(conn); return
    for r in rows:
        await ctx.send(r['image_url'])
    ids = [r['id'] for r in rows]
    cur.execute("UPDATE images SET status='sent', sent_at=now() WHERE id = ANY(%s)", (ids,))
    conn.commit()
    cur.close()
    return_db_connection(conn)

# Flask in thread + run bot
def run_flask():
    port = int(os.environ.get('PORT', 10000))
    logger.info("Flask running on port %s", port)
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.exception("Erreur bot")
    finally:
        if connection_pool:
            connection_pool.closeall()
