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
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import psycopg2
from psycopg2 import pool

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Charger les variables d'environnement
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

# Webhooks par catégorie (optionnel)
WEBHOOKS = {
    'boy': os.getenv('WEBHOOK_BOY', WEBHOOK_URL),
    'girl': os.getenv('WEBHOOK_GIRL', WEBHOOK_URL),
    'banner': os.getenv('WEBHOOK_BANNER', WEBHOOK_URL),
    'match': os.getenv('WEBHOOK_MATCH', WEBHOOK_URL),
    'anime': os.getenv('WEBHOOK_ANIME', WEBHOOK_URL),
    'aesthetic': os.getenv('WEBHOOK_AESTHETIC', WEBHOOK_URL),
    'cute': os.getenv('WEBHOOK_CUTE', WEBHOOK_URL),
}

# Pool de connexions PostgreSQL
try:
    connection_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL)
    logging.info("Pool PostgreSQL initialisé")
except Exception as e:
    logging.error(f"Erreur pool PostgreSQL: {e}")
    connection_pool = None

# Configuration Discord Bot
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Flask API
app = Flask(__name__)
CORS(app)

# Catégories valides
CATEGORIES = ['anime', 'boy', 'girl', 'aesthetic', 'cute', 'banner', 'match']

# ============================================================================
# FONCTIONS DATABASE
# ============================================================================

def get_db_connection():
    """Récupérer une connexion depuis le pool"""
    if connection_pool:
        return connection_pool.getconn()
    return None

def release_db_connection(conn):
    """Libérer une connexion vers le pool"""
    if connection_pool and conn:
        connection_pool.putconn(conn)

def insert_image(category, url):
    """Insérer une image dans la base de données"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO images (category, url) VALUES (%s, %s) ON CONFLICT (url) DO NOTHING RETURNING id",
                (category, url)
            )
            result = cursor.fetchone()
            conn.commit()
            return result is not None
    except Exception as e:
        logging.error(f"Erreur insertion image: {e}")
        conn.rollback()
        return False
    finally:
        release_db_connection(conn)

def get_random_images(category, count=1):
    """Récupérer des images aléatoires"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT url FROM images WHERE category = %s AND used = FALSE ORDER BY RANDOM() LIMIT %s",
                (category, count)
            )
            results = cursor.fetchall()
            
            if results:
                urls = [row[0] for row in results]
                cursor.execute(
                    "UPDATE images SET used = TRUE WHERE url = ANY(%s)",
                    (urls,)
                )
                conn.commit()
                return urls
            return []
    except Exception as e:
        logging.error(f"Erreur récupération images: {e}")
        return []
    finally:
        release_db_connection(conn)

def get_stock():
    """Récupérer le stock par catégorie"""
    conn = get_db_connection()
    if not conn:
        return {}
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT category, COUNT(*) FROM images WHERE used = FALSE GROUP BY category"
            )
            results = cursor.fetchall()
            return {row[0]: row[1] for row in results}
    except Exception as e:
        logging.error(f"Erreur récupération stock: {e}")
        return {}
    finally:
        release_db_connection(conn)

# ============================================================================
# SCRAPING PINTEREST
# ============================================================================

def scrape_pinterest(url, max_images=50):
    """Scrapper des images depuis Pinterest"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        images = []
        
        # Rechercher les images Pinterest
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src')
            if src and 'pinimg.com' in src and '236x' in src:
                # Remplacer par la version haute qualité
                high_res = src.replace('236x', '736x')
                if high_res not in images:
                    images.append(high_res)
                    if len(images) >= max_images:
                        break
        
        logging.info(f"Trouvé {len(images)} images sur {url}")
        return images
    except Exception as e:
        logging.error(f"Erreur scraping: {e}")
        return []

# ============================================================================
# WEBHOOK NOTIFICATIONS
# ============================================================================

def send_webhook_notification(category, imported, duplicates, source_url):
    """Envoyer une notification webhook"""
    webhook_url = WEBHOOKS.get(category, WEBHOOK_URL)
    if not webhook_url:
        return
    
    try:
        embed = {
            "title": "✅ Import terminé",
            "color": 0x00ff00,
            "fields": [
                {"name": "📂 Catégorie", "value": category, "inline": True},
                {"name": "✅ Importées", "value": str(imported), "inline": True},
                {"name": "⚠️ Doublons", "value": str(duplicates), "inline": True},
                {"name": "🔗 Source", "value": source_url, "inline": False},
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "PFP Bot Import System"}
        }
        
        data = {"embeds": [embed]}
        requests.post(webhook_url, json=data, timeout=5)
    except Exception as e:
        logging.error(f"Erreur webhook: {e}")

# ============================================================================
# COMMANDE !urlpdp (INTERACTIVE)
# ============================================================================

class URLPDPView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.url = None
        self.category = None
        self.max_images = 50
    
    @discord.ui.button(label="📝 Entrer l'URL", style=discord.ButtonStyle.primary)
    async def url_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = URLModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        
        if modal.url:
            self.url = modal.url
            await interaction.followup.send(f"✅ URL enregistrée: {self.url}", ephemeral=True)
    
    @discord.ui.select(
        placeholder="📂 Choisir une catégorie",
        options=[
            discord.SelectOption(label="Boy", value="boy", emoji="👦"),
            discord.SelectOption(label="Girl", value="girl", emoji="👧"),
            discord.SelectOption(label="Anime", value="anime", emoji="🎌"),
            discord.SelectOption(label="Aesthetic", value="aesthetic", emoji="🌸"),
            discord.SelectOption(label="Cute", value="cute", emoji="🥰"),
            discord.SelectOption(label="Banner", value="banner", emoji="🎨"),
            discord.SelectOption(label="Match", value="match", emoji="💑"),
        ]
    )
    async def category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.category = select.values[0]
        await interaction.response.send_message(f"✅ Catégorie: **{self.category}**", ephemeral=True)
    
    @discord.ui.button(label="🔢 Nombre de photos", style=discord.ButtonStyle.secondary)
    async def count_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CountModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        
        if modal.count:
            self.max_images = modal.count
            await interaction.followup.send(f"✅ Nombre: {self.max_images} photos", ephemeral=True)
    
    @discord.ui.button(label="✅ Lancer l'import", style=discord.ButtonStyle.success)
    async def import_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.url:
            await interaction.response.send_message("❌ Aucune URL définie !", ephemeral=True)
            return
        
        if not self.category:
            await interaction.response.send_message("❌ Aucune catégorie choisie !", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Scraping
        start_time = datetime.now()
        images = scrape_pinterest(self.url, self.max_images)
        
        if not images:
            embed = discord.Embed(
                title="❌ Échec de l'import",
                description="Aucune image trouvée sur cette URL.",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Import dans la DB
        inserted = 0
        duplicates = 0
        
        for img_url in images:
            if insert_image(self.category, img_url):
                inserted += 1
            else:
                duplicates += 1
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Notification webhook
        send_webhook_notification(self.category, inserted, duplicates, self.url)
        
        # Embed de succès
        embed = discord.Embed(
            title="✅ Import terminé !",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="🔍 Trouvées", value=str(len(images)), inline=True)
        embed.add_field(name="✅ Importées", value=str(inserted), inline=True)
        embed.add_field(name="⚠️ Doublons", value=str(duplicates), inline=True)
        embed.add_field(name="📂 Catégorie", value=self.category, inline=True)
        embed.add_field(name="⏱️ Durée", value=f"{duration:.1f}s", inline=True)
        embed.set_footer(text=f"Demandé par {interaction.user.name}")
        
        await interaction.followup.send(embed=embed)

class URLModal(discord.ui.Modal, title="Entrer l'URL Pinterest"):
    url_input = discord.ui.TextInput(
        label="URL Pinterest",
        placeholder="https://www.pinterest.com/...",
        required=True,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        self.url = self.url_input.value
        await interaction.response.send_message("✅ URL enregistrée !", ephemeral=True)

class CountModal(discord.ui.Modal, title="Nombre de photos"):
    count_input = discord.ui.TextInput(
        label="Nombre (max 200)",
        placeholder="50",
        required=True,
        max_length=3
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.count = min(int(self.count_input.value), 200)
            await interaction.response.send_message(f"✅ Nombre défini: {self.count}", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Nombre invalide !", ephemeral=True)
            self.count = 50

@bot.command(name='urlpdp')
async def urlpdp(ctx):
    """Interface interactive pour importer des photos"""
    embed = discord.Embed(
        title="📥 Import de photos Pinterest",
        description="Utilisez les boutons ci-dessous pour configurer votre import :",
        color=0x7c3aed
    )
    embed.add_field(name="1️⃣", value="Cliquez sur **📝 Entrer l'URL**", inline=False)
    embed.add_field(name="2️⃣", value="Choisissez la **catégorie**", inline=False)
    embed.add_field(name="3️⃣", value="(Optionnel) Définir le **nombre**", inline=False)
    embed.add_field(name="4️⃣", value="Cliquez sur **✅ Lancer l'import**", inline=False)
    
    view = URLPDPView()
    await ctx.send(embed=embed, view=view)

# ============================================================================
# COMMANDES DISCORD CLASSIQUES
# ============================================================================

@bot.command(name='pdp')
async def pdp(ctx, category: str = None, count: int = 1):
    """Envoyer des photos de profil"""
    if not category or category.lower() not in CATEGORIES:
        await ctx.send(f"❌ Catégorie invalide ! Utilisez: {', '.join(CATEGORIES)}")
        return
    
    category = category.lower()
    count = min(max(count, 1), 10)
    
    images = get_random_images(category, count)
    
    if not images:
        await ctx.send(f"❌ Aucune image disponible pour **{category}** !")
        return
    
    for img_url in images:
        await ctx.send(img_url)

@bot.command(name='banner')
async def banner(ctx, count: int = 1):
    """Envoyer des bannières"""
    count = min(max(count, 1), 5)
    images = get_random_images('banner', count)
    
    if not images:
        await ctx.send("❌ Aucune bannière disponible !")
        return
    
    for img_url in images:
        await ctx.send(img_url)

@bot.command(name='stock')
async def stock(ctx):
    """Afficher le stock disponible"""
    stock_data = get_stock()
    
    if not stock_data:
        await ctx.send("❌ Aucune donnée de stock disponible !")
        return
    
    embed = discord.Embed(title="📊 Stock disponible", color=0x7c3aed)
    
    for cat, count in stock_data.items():
        embed.add_field(name=cat.capitalize(), value=f"{count} images", inline=True)
    
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    logging.info(f"Bot connecté en tant que {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        logging.error(f"Commande inconnue: {ctx.message.content}")
    else:
        logging.error(f"Erreur commande: {error}")

# ============================================================================
# FLASK API
# ============================================================================

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "bot": "Discord PFP Bot",
        "version": "2.0"
    })

@app.route('/stock')
def api_stock():
    return jsonify(get_stock())

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

def run_flask():
    port = int(os.getenv('PORT', 10000))
    logging.info(f"Flask running on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

# ============================================================================
# LANCEMENT
# ============================================================================

if __name__ == '__main__':
    try:
        # Lancer Flask dans un thread séparé
        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        # Lancer le bot Discord
        bot.run(TOKEN)
    except Exception as e:
        logging.error(f"Erreur bot: {e}")
