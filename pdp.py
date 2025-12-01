# main.py
import os
import logging
from threading import Thread
from urllib.parse import urlparse
from time import sleep
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sock import Sock
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
WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

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
CORS(app, resources={r"/*": {"origins": "*"}})
sock = Sock(app)

# Store WebSocket connections
ws_clients = []

@sock.route('/ws')
def websocket_handler(ws):
    """WebSocket endpoint for real-time updates"""
    ws_clients.append(ws)
    logger.info("Client WebSocket connecté")
    try:
        while True:
            data = ws.receive()
            if data:
                logger.info(f"WS reçu: {data}")
    except Exception as e:
        logger.info("Client WebSocket déconnecté")
    finally:
        if ws in ws_clients:
            ws_clients.remove(ws)

def broadcast_ws(message):
    """Envoie un message à tous les clients WebSocket"""
    import json
    dead_clients = []
    for ws in ws_clients:
        try:
            ws.send(json.dumps(message))
        except:
            dead_clients.append(ws)
    for ws in dead_clients:
        if ws in ws_clients:
            ws_clients.remove(ws)

@app.route('/', methods=['GET'])
def index():
    info = {
        "bot": bot.user.name if bot and bot.is_ready() else None,
        "guilds": len(bot.guilds) if bot and bot.is_ready() else 0,
        "status": "online" if bot and bot.is_ready() else "starting",
        "users": len(bot.users) if bot and bot.is_ready() else 0
    }
    return jsonify(info)

@app.route('/health', methods=['GET'])
def health():
    is_ready = bot.is_ready()
    return jsonify({"bot_ready": is_ready, "status": ("ok" if is_ready else "starting")}), (200 if is_ready else 503)

# ✅ ENDPOINT MANQUANT: /status
@app.route('/status', methods=['GET'])
def status():
    """Status du bot pour le panel"""
    return jsonify({
        "status": "online" if bot and bot.is_ready() else "offline",
        "bot_name": bot.user.name if bot and bot.is_ready() else None,
        "guilds": len(bot.guilds) if bot and bot.is_ready() else 0,
        "users": len(bot.users) if bot and bot.is_ready() else 0
    })

@app.route('/stats', methods=['GET'])
def stats_api():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "DB connection failed"}), 500
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Total photos
        cur.execute("SELECT COUNT(*) as count FROM images")
        total_photos = cur.fetchone()['count']
        
        # Total imports (groupés par scrape session)
        cur.execute("SELECT COUNT(DISTINCT category) as count FROM images")
        total_imports = cur.fetchone()['count']
        
        # Photos aujourd'hui
        cur.execute("SELECT COUNT(*) as count FROM images WHERE DATE(created_at) = CURRENT_DATE")
        today_photos = cur.fetchone()['count']
        
        # Dernière activité
        cur.execute("SELECT MAX(created_at) as last FROM images")
        last = cur.fetchone()['last']
        last_activity = last.strftime("%d/%m/%Y %H:%M") if last else "Jamais"
        
        # Stock par catégorie
        cur.execute("SELECT category, COUNT(*) as count FROM images WHERE status='pending' GROUP BY category")
        stock = {r['category']: r['count'] for r in cur.fetchall()}
        
        cur.close()
        return_db_connection(conn)
        
        return jsonify({
            "total_photos": total_photos,
            "total_imports": total_imports,
            "today_photos": today_photos,
            "last_activity": last_activity,
            "stock": stock,
            "guilds": len(bot.guilds) if bot and bot.is_ready() else 0,
            "users": len(bot.users) if bot and bot.is_ready() else 0
        })
    except Exception as e:
        logger.exception("Erreur /stats")
        return jsonify({"error": str(e)}), 500

# ✅ ENDPOINT MANQUANT: /photos
@app.route('/photos', methods=['GET'])
def get_photos():
    """Récupère les photos pour la galerie"""
    try:
        category = request.args.get('category', 'all')
        limit = int(request.args.get('limit', 100))
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "DB connection failed"}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        if category == 'all':
            cur.execute("SELECT id, image_url, category, status FROM images ORDER BY created_at DESC LIMIT %s", (limit,))
        else:
            cur.execute("SELECT id, image_url, category, status FROM images WHERE category = %s ORDER BY created_at DESC LIMIT %s", (category, limit))
        
        photos = []
        for row in cur.fetchall():
            photos.append({
                "id": row['id'],
                "url": row['image_url'],
                "category": row['category'],
                "status": row['status']
            })
        
        cur.close()
        return_db_connection(conn)
        
        return jsonify({"photos": photos, "count": len(photos)})
    except Exception as e:
        logger.exception("Erreur /photos")
        return jsonify({"error": str(e)}), 500

# ✅ ENDPOINT MANQUANT: /history
@app.route('/history', methods=['GET'])
def get_history():
    """Récupère l'historique des imports"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "DB connection failed"}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Grouper les imports par catégorie et date
        cur.execute("""
            SELECT 
                category,
                COUNT(*) as photo_count,
                MIN(created_at) as date,
                'success' as status,
                'Pinterest' as source
            FROM images
            GROUP BY category, DATE(created_at)
            ORDER BY MIN(created_at) DESC
            LIMIT 50
        """)
        
        history = []
        for row in cur.fetchall():
            history.append({
                "category": row['category'],
                "photo_count": row['photo_count'],
                "date": row['date'].isoformat() if row['date'] else None,
                "status": row['status'],
                "source": row['source'],
                "duration": "N/A"
            })
        
        cur.close()
        return_db_connection(conn)
        
        return jsonify({"history": history})
    except Exception as e:
        logger.exception("Erreur /history")
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
    body: { "pinterest_link": "...", "category": "anime", "photo_count": 50 }
    """
    data = request.get_json(force=True, silent=True) or {}
    url = data.get('pinterest_link') or data.get('url') or request.form.get('url')
    category = (data.get('category') or request.form.get('category') or 'uncategorized').strip()
    try:
        limit = int(data.get('photo_count') or data.get('limit') or request.form.get('limit') or 50)
    except:
        limit = 50
    
    if not url:
        return jsonify({"error": "URL manquante"}), 400

    logger.info("Scraping demandé: %s (cat=%s limit=%d)", url, category, limit)
    
    # Notifier le début via WebSocket
    broadcast_ws({"type": "info", "message": f"Démarrage du scraping {category}..."})
    
    # Scraper
    found = scrape_pinterest(url, limit=limit)
    if not found:
        broadcast_ws({"type": "error", "message": "Aucune image trouvée"})
        return jsonify({"inserted": 0, "found": 0, "message": "Aucune image trouvée"}), 200

    # Insert into DB
    conn = get_db_connection()
    if not conn:
        broadcast_ws({"type": "error", "message": "Erreur DB"})
        return jsonify({"error": "DB connection failed"}), 500
    
    cur = conn.cursor()
    inserted = 0
    try:
        for i, img_url in enumerate(found):
            cur.execute("SELECT id FROM images WHERE image_url = %s", (img_url,))
            if cur.fetchone():
                continue
            cur.execute(
                "INSERT INTO images (image_url, category, status) VALUES (%s,%s,%s) RETURNING id",
                (img_url, category, 'pending')
            )
            inserted += 1
            
            # Envoyer progression via WebSocket
            if inserted % 10 == 0 or inserted == len(found):
                broadcast_ws({
                    "type": "progress",
                    "current": inserted,
                    "total": limit,
                    "speed": round(inserted / ((i+1)/10), 1)
                })
            
            if inserted >= limit:
                break
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.exception("Erreur insertion images")
        broadcast_ws({"type": "error", "message": f"Erreur: {str(e)}"})
    finally:
        cur.close()
        return_db_connection(conn)

    logger.info("Scrape terminé: %d insérées", inserted)
    
    # Notifier la fin
    broadcast_ws({
        "type": "complete",
        "total": inserted,
        "message": f"{inserted} photos scrapées avec succès"
    })
    
    return jsonify({
        "inserted": inserted,
        "found": len(found),
        "import_id": f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    }), 200

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

@bot.event
async def on_ready():
    logger.info(f'Bot connecté: {bot.user} — guilds: {len(bot.guilds)}')
    await bot.change_presence(activity=discord.Game(name="!help"))

@bot.command(name='pdp')
async def pdp(ctx, category: str = None, count: int = 15):
    """
    Commande pour envoyer des photos de profil
    Usage: !pdp <catégorie> [nombre]
    Exemple: !pdp boy 20
    """
    if not category:
        await ctx.send("❌ Spécifiez une catégorie: `!pdp <catégorie> [nombre]`\nExemple: `!pdp boy 20`")
        return
    
    # Limiter le nombre entre 1 et 50
    if count < 1:
        count = 1
    elif count > 50:
        await ctx.send(f"⚠️ Maximum 50 photos par commande. Je vais envoyer 50 photos.")
        count = 50
    
    conn = get_db_connection()
    if not conn:
        await ctx.send("❌ Erreur de connexion à la base de données")
        return
    
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Vérifier le stock disponible
    cur.execute("SELECT COUNT(*) as total FROM images WHERE category = %s AND status = 'pending'", (category,))
    stock = cur.fetchone()['total']
    
    if stock == 0:
        await ctx.send(f"❌ Aucune image disponible pour la catégorie `{category}`")
        return_db_connection(conn)
        return
    
    if stock < count:
        await ctx.send(f"⚠️ Seulement {stock} images disponibles pour `{category}`. Je vais les envoyer toutes.")
        count = stock
    
    # Récupérer les images
    cur.execute("""
        SELECT id, image_url FROM images
        WHERE category = %s AND status = 'pending'
        ORDER BY RANDOM()
        LIMIT %s
    """, (category, count))
    
    rows = cur.fetchall()
    
    if not rows:
        await ctx.send(f"❌ Aucune image disponible pour `{category}`")
        return_db_connection(conn)
        return
    
    # Message de confirmation
    await ctx.send(f"📸 Envoi de **{len(rows)} photos** de la catégorie `{category}`...")
    
    # Envoyer les images
    sent_count = 0
    for r in rows:
        try:
            await ctx.send(r['image_url'])
            sent_count += 1
        except Exception as e:
            logger.error(f"Erreur envoi image {r['id']}: {e}")
    
    # Marquer comme envoyées
    ids = [r['id'] for r in rows]
    cur.execute("UPDATE images SET status='sent', sent_at=now() WHERE id = ANY(%s)", (ids,))
    conn.commit()
    
    # Message de fin
    remaining = stock - sent_count
    await ctx.send(f"✅ **{sent_count} photos** envoyées ! Il reste **{remaining} photos** dans le stock `{category}`.")
    
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
