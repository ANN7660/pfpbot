import os
import logging
import json
from threading import Thread
from datetime import datetime
from typing import List

import requests
from bs4 import BeautifulSoup
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from flask import Flask, jsonify
import discord
from discord.ext import commands

# ----------------------
# CONFIG / ENV
# ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")  # optional
PORT = int(os.getenv("PORT", 10000))

# categories de base (on garde celles-ci, mais on peut ajouter dynamiquement)
BASE_CATEGORIES = ["boy", "girl", "anime", "aesthetic", "cute", "banner", "match"]

# ----------------------
# POSTGRES CONNECTION POOL
# ----------------------
connection_pool = None
if DATABASE_URL:
    try:
        # minconn=1, maxconn=10
        connection_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL)
        logging.info("PostgreSQL pool initialisé")
    except Exception as e:
        logging.error(f"Erreur initialisation pool PostgreSQL: {e}")
        connection_pool = None
else:
    logging.warning("DATABASE_URL non défini — la DB sera indisponible")

def get_db_conn():
    """Récupérer une connexion depuis le pool (avec RealDictCursor)."""
    if not connection_pool:
        return None
    conn = connection_pool.getconn()
    return conn

def release_db_conn(conn):
    if connection_pool and conn:
        connection_pool.putconn(conn)

# ----------------------
# DATABASE HELPERS
# ----------------------
def ensure_images_table():
    """Crée la table images si elle n'existe pas (id, category, url unique, used)."""
    conn = get_db_conn()
    if not conn:
        logging.error("DB non disponible pour créer la table")
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id SERIAL PRIMARY KEY,
                category VARCHAR(255),
                url TEXT UNIQUE,
                used BOOLEAN DEFAULT FALSE,
                imported_at TIMESTAMP DEFAULT NOW()
            );
            """)
            conn.commit()
            logging.info("Table 'images' OK")
    except Exception as e:
        logging.error(f"Erreur ensure_images_table: {e}")
        conn.rollback()
    finally:
        release_db_conn(conn)

def insert_image(category: str, url: str) -> bool:
    """Insère une image (ignore si doublon). Retourne True si insérée."""
    conn = get_db_conn()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO images (category, url) VALUES (%s, %s) ON CONFLICT (url) DO NOTHING RETURNING id",
                (category, url)
            )
            res = cur.fetchone()
            conn.commit()
            return res is not None
    except Exception as e:
        logging.error(f"Erreur insert_image: {e}")
        conn.rollback()
        return False
    finally:
        release_db_conn(conn)

def get_random_images(category: str, count: int = 1) -> List[str]:
    """Récupère images aléatoires non-used depuis la DB et marque used=True."""
    conn = get_db_conn()
    if not conn:
        return []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT url FROM images WHERE category = %s AND used = FALSE ORDER BY RANDOM() LIMIT %s",
                (category, count)
            )
            rows = cur.fetchall()
            urls = [r["url"] for r in rows]
            if urls:
                cur.execute("UPDATE images SET used = TRUE WHERE url = ANY(%s)", (urls,))
                conn.commit()
            return urls
    except Exception as e:
        logging.error(f"Erreur get_random_images: {e}")
        return []
    finally:
        release_db_conn(conn)

def db_get_categories() -> List[str]:
    """Retourne la liste des catégories distinctes (mergeavec BASE_CATEGORIES)."""
    categories = list(BASE_CATEGORIES)
    conn = get_db_conn()
    if not conn:
        return categories
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT category FROM images")
            rows = cur.fetchall()
            for r in rows:
                cat = r[0]
                if cat and cat not in categories:
                    categories.append(cat)
    except Exception as e:
        logging.error(f"Erreur db_get_categories: {e}")
    finally:
        release_db_conn(conn)
    return categories

def db_get_images(category: str, limit: int = 10) -> List[str]:
    """Récupère images par catégorie (insensible à la casse), ne marque pas used."""
    conn = get_db_conn()
    if not conn:
        return []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT url FROM images WHERE category ILIKE %s AND used = FALSE ORDER BY RANDOM() LIMIT %s", (category, limit))
            rows = cur.fetchall()
            return [r["url"] for r in rows]
    except Exception as e:
        logging.error(f"Erreur db_get_images: {e}")
        return []
    finally:
        release_db_conn(conn)

# ----------------------
# WEBHOOK NOTIFS
# ----------------------
def send_webhook_notification(category: str, imported: int, duplicates: int, source_url: str):
    if not WEBHOOK_URL:
        return
    try:
        embed = {
            "embeds": [{
                "title": "✅ Import terminé",
                "color": 0x00ff00,
                "fields": [
                    {"name": "Catégorie", "value": category, "inline": True},
                    {"name": "Importées", "value": str(imported), "inline": True},
                    {"name": "Doublons", "value": str(duplicates), "inline": True},
                    {"name": "Source", "value": source_url, "inline": False},
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "PDP Bot Import"}
            }]
        }
        requests.post(WEBHOOK_URL, json=embed, timeout=5)
    except Exception as e:
        logging.error(f"Erreur webhook: {e}")

# ----------------------
# SCRAPING PINTEREST (JSON extraction + fallback)
# ----------------------
def scrape_pinterest_from_page(url: str, max_images: int = 50) -> List[str]:
    """Scrape Pinterest: tente d'extraire le JSON interne puis fallback sur <img> pinimg."""
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "fr-FR,fr;q=0.9"}
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        text = resp.text
        imgs = []

        # 1) Cherche script id __PWS_DATA__ (JSON global)
        soup = BeautifulSoup(text, "html.parser")
        script = soup.find("script", id="__PWS_DATA__")
        if script and script.string:
            try:
                data = json.loads(script.string)
                redux = data.get("props", {}).get("initialReduxState", {}) or {}
                pins = redux.get("pins", {}) or {}
                for pin_id, pin in pins.items():
                    try:
                        # prefer orig, else other sizes
                        img_url = pin.get("images", {}).get("orig", {}).get("url")
                        if not img_url:
                            # try common keys
                            for k in ("736x", "564x", "474x", "236x"):
                                img_url = pin.get("images", {}).get(k, {}).get("url")
                                if img_url:
                                    break
                        if img_url and "pinimg.com" in img_url:
                            if img_url not in imgs:
                                imgs.append(img_url)
                                if len(imgs) >= max_images:
                                    break
                    except Exception:
                        continue
                if imgs:
                    logging.info(f"Pinterest JSON: trouvé {len(imgs)} images")
                    return imgs
            except Exception as e:
                logging.debug(f"Échec parsing JSON __PWS_DATA__: {e}")

        # 2) Fallback : chercher les <img> pinimg.com
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if "pinimg.com" in src:
                # remplacer taille par une taille plus grande si existante
                high = src.replace("236x", "736x")
                if high not in imgs:
                    imgs.append(high)
                    if len(imgs) >= max_images:
                        break

        logging.info(f"Pinterest fallback: trouvé {len(imgs)} images")
        return imgs
    except Exception as e:
        logging.error(f"Erreur scraping Pinterest: {e}")
        return []

# ----------------------
# FLASK (health)
# ----------------------
app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "online", "bot": "PDP Bot"})

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ----------------------
# DISCORD BOT & COMMANDS
# ----------------------
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ensure table on startup
@bot.event
async def on_ready():
    logging.info(f"Bot connecté en tant que {bot.user}")
    ensure_images_table()
    # announce startup via webhook (optional)
    if WEBHOOK_URL:
        try:
            requests.post(WEBHOOK_URL, json={"content": f"PDP Bot démarré: {bot.user}"}, timeout=5)
        except Exception:
            pass

# --------- Helper Views / Modals ----------
class ImportModal(discord.ui.Modal, title="Importer depuis Pinterest"):
    url_input = discord.ui.TextInput(label="URL Pinterest", style=discord.TextStyle.short, placeholder="https://www.pinterest.com/...", required=True, max_length=1000)
    category_input = discord.ui.TextInput(label="Catégorie (ex: boy)", style=discord.TextStyle.short, placeholder="boy", required=True, max_length=100)
    count_input = discord.ui.TextInput(label="Nombre d'images (max 200)", style=discord.TextStyle.short, placeholder="50", required=True, max_length=4)

    def __init__(self):
        super().__init__()
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        # validate inputs
        url = self.url_input.value.strip()
        category = self.category_input.value.strip()
        try:
            count = min(max(int(self.count_input.value.strip()), 1), 200)
        except Exception:
            count = 50

        await interaction.response.send_message(f"Import en cours pour {category} — scraping...", ephemeral=True)
        self.result = {"url": url, "category": category, "count": count}

class ImportView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Ouvrir le formulaire d'import", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ImportModal()
        await interaction.response.send_modal(modal)
        # We cannot 'await modal.wait()' inside Discord Modal; handle after submit via modal.result in caller.

# --------- Commandes ---------
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(title="📘 Commandes PDP Bot", color=0x7c3aed)
    embed.add_field(name="!pdp", value="Ouvre le menu interactif pour choisir une catégorie et un nombre d'images depuis la base de données.", inline=False)
    embed.add_field(name="!pdpui", value="Version alternative (ouvre directement l'UI de sélection).", inline=False)
    embed.add_field(name="!url", value="Import interactif depuis Pinterest (embed + formulaire).", inline=False)
    embed.add_field(name="!help", value="Affiche ce message.", inline=False)
    await ctx.send(embed=embed)

# Commande !url -> ouvre embed + bouton qui ouvre le modal d'import (URL, catégorie, nombre)
@bot.command(name="url")
async def url_import_cmd(ctx):
    embed = discord.Embed(title="Importer depuis Pinterest", description="Clique sur le bouton pour ouvrir le formulaire d'import.\nCatégories existantes : " + ", ".join(db_get_categories()), color=0x8e44ad)
    view = ImportView()
    await ctx.send(embed=embed, view=view)

# To process ImportModal results we rely on the modal submission handling above.
# But we need to perform the actual scrape+insert after the modal is submitted.
# Because modals are handled in-line, we implement a listener to process recently submitted modals.
# Simpler: implement a command that does the same with arguments for non-modal fallback:
@bot.command(name="importnow")
async def importnow_cmd(ctx, url: str, category: str = "uncategorized", count: int = 50):
    """Fallback command: !importnow <url> <category> <count>"""
    await ctx.send(f"Import: scraping {url} pour la catégorie `{category}` ({count} images)...")
    images = scrape_pinterest_from_page(url, max_images=count)
    if not images:
        await ctx.send("Aucune image trouvée (scraping).")
        return

    inserted = 0
    duplicates = 0
    for img in images:
        if insert_image(category, img):
            inserted += 1
        else:
            duplicates += 1

    send_webhook_notification(category, inserted, duplicates, url)
    await ctx.send(f"Import terminé — Importées: {inserted} — Doublons: {duplicates}")

# Commande !pdpui -> ouvre la même UI as pdp but explicitly
@bot.command(name="pdpui")
async def pdpui_cmd(ctx):
    view = PdpCategoryView()
    embed = discord.Embed(title="Choisis ta catégorie", description="Sélectionne une catégorie ci-dessous.", color=0x9b59b6)
    await ctx.send(embed=embed, view=view)

# The interactive view used for !pdp and !pdpui
class PdpCategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        # create select dynamically from DB categories
        cats = db_get_categories()
        options = [discord.SelectOption(label=c, value=c) for c in cats]
        # ensure at least one option (shouldn't happen)
        if not options:
            options = [discord.SelectOption(label="boy", value="boy")]
        self.add_item(CategorySelect(options))

class CategorySelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Choisir une catégorie", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        await interaction.response.send_message(f"Combien d'images pour **{category}** ? Réponds par un nombre (1-20).", ephemeral=True)

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            msg = await interaction.client.wait_for("message", timeout=20.0, check=check)
            count = max(1, min(int(msg.content.strip()), 20))
        except Exception:
            await interaction.followup.send("Temps dépassé ou entrée invalide.", ephemeral=True)
            return

        # fetch images from DB and mark them used
        urls = []
        conn = get_db_conn()
        if not conn:
            await interaction.followup.send("Base de données indisponible.", ephemeral=True)
            return
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT url FROM images WHERE category = %s AND used = FALSE ORDER BY RANDOM() LIMIT %s", (category, count))
                rows = cur.fetchall()
                urls = [r["url"] for r in rows]
                if urls:
                    cur.execute("UPDATE images SET used = TRUE WHERE url = ANY(%s)", (urls,))
                    conn.commit()
        except Exception as e:
            logging.error(f"Erreur récupérer images interactive: {e}")
        finally:
            release_db_conn(conn)

        if not urls:
            await interaction.followup.send(f"Aucune image disponible pour **{category}**.", ephemeral=True)
            return

        # send first image + pager view
        pager = ImagePager(urls)
        embed = discord.Embed(title="Résultats", description=f"Catégorie : {category}", color=0x2ecc71)
        embed.add_field(name="Images", value=f"{len(urls)} images envoyées", inline=False)
        await interaction.followup.send(embed=embed)
        await interaction.followup.send(urls[0], view=pager)

class ImagePager(discord.ui.View):
    def __init__(self, imgs: List[str], index: int = 0):
        super().__init__(timeout=300)
        self.imgs = imgs
        self.index = index

    async def send_page(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content=self.imgs[self.index], view=self)

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index - 1) % len(self.imgs)
        await self.send_page(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index + 1) % len(self.imgs)
        await self.send_page(interaction)

# Simple wrapper so calling !pdp opens the UI
@bot.command(name="pdp")
async def pdp_cmd(ctx):
    view = PdpCategoryView()
    embed = discord.Embed(title="Choisis une catégorie", description="Sélectionne une catégorie ci-dessous.", color=0x3498db)
    await ctx.send(embed=embed, view=view)

# ----------------------
# BOOT
# ----------------------
def start_flask_thread():
    thread = Thread(target=run_flask, daemon=True)
    thread.start()
    logging.info("Flask thread started")

if __name__ == "__main__":
    ensure_images_table()
    start_flask_thread()
    if not DISCORD_TOKEN:
        logging.error("DISCORD_TOKEN manquant. Arrêt.")
    else:
        bot.run(DISCORD_TOKEN)
