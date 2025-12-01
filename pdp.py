# pdp.py — Version complète avec toutes les fonctionnalités

import os
import asyncio
import logging
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
from discord import Intents
import re
import json
from urllib.parse import urlparse

# ----------------------
# ENV
# ----------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PORT = int(os.getenv("PORT", 10000))

logging.basicConfig(level=logging.INFO)

# ----------------------
# FLASK
# ----------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot online"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ----------------------
# DB CONNECT
# ----------------------
def db_connect():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        logging.error(f"DB error: {e}")
        return None

# ----------------------
# AUTO-CHECK STRUCTURE
# ----------------------
def db_init():
    conn = db_connect()
    if not conn:
        logging.error("Impossible d'initialiser la DB.")
        return

    cur = conn.cursor()

    # Ajoute colonnes si manquantes
    cur.execute("""
        ALTER TABLE images
        ADD COLUMN IF NOT EXISTS used BOOLEAN DEFAULT FALSE;
    """)

    cur.execute("""
        ALTER TABLE images
        ADD COLUMN IF NOT EXISTS category TEXT;
    """)

    conn.commit()
    cur.close()
    conn.close()
    logging.info("Structure DB vérifiée.")

# ----------------------
# DISCORD BOT
# ----------------------
intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ----------------------
# FONCTION SCRAPING PINTEREST
# ----------------------
async def scrape_pinterest(url, count):
    """
    Scrape Pinterest avec headers avancés et parsing HTML
    """
    try:
        # Headers plus complets pour éviter le blocage
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }
        
        # Nettoyer l'URL
        clean_url = url.rstrip('/')
        
        # Requête asynchrone
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.get(clean_url, headers=headers, timeout=20, allow_redirects=True)
        )
        
        if response.status_code != 200:
            logging.error(f"Erreur Pinterest: Status {response.status_code}")
            return []
        
        # Chercher les URLs d'images dans le HTML
        html_content = response.text
        image_urls = []
        
        # Pattern pour trouver les URLs Pinterest d'images
        patterns = [
            r'"url":"(https://i\.pinimg\.com/originals/[^"]+)"',
            r'"url":"(https://i\.pinimg\.com/736x/[^"]+)"',
            r'https://i\.pinimg\.com/originals/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]+\.(jpg|png|jpeg)',
            r'https://i\.pinimg\.com/736x/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]+\.(jpg|png|jpeg)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content)
            for match in matches:
                if isinstance(match, tuple):
                    img_url = match[0]
                else:
                    img_url = match
                
                # Nettoyer l'URL si elle contient des échappements
                img_url = img_url.replace('\\/', '/')
                
                if img_url not in image_urls:
                    image_urls.append(img_url)
                
                if len(image_urls) >= count:
                    break
            
            if len(image_urls) >= count:
                break
        
        logging.info(f"Trouvé {len(image_urls)} images sur Pinterest")
        return image_urls[:count]
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Erreur réseau Pinterest: {e}")
        return []
    except Exception as e:
        logging.error(f"Erreur scraping Pinterest: {e}")
        return []

# ----------------------
# COMMANDE !HELP
# ----------------------
@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="📚 Commandes disponibles",
        description="Voici toutes les commandes du bot",
        color=0x1abc9c
    )
    embed.add_field(
        name="🖼️ !pdp",
        value="Récupérer des images depuis la DB (interactif)",
        inline=False
    )
    embed.add_field(
        name="📌 !url",
        value="Importer des images depuis Pinterest",
        inline=False
    )
    embed.add_field(
        name="📊 !stock",
        value="Voir le stock restant par catégorie",
        inline=False
    )
    embed.add_field(
        name="❓ !help",
        value="Afficher ce message",
        inline=False
    )
    embed.set_footer(text="Bot Pinterest • Développé avec ❤️")
    await ctx.send(embed=embed)

# ----------------------
# COMMANDE !PDP
# ----------------------
@bot.command(name="pdp")
async def pdp(ctx):
    """Commande interactive pour récupérer des images"""
    
    embed = discord.Embed(
        title="🖼️ Récupérer des images",
        description="Choisissez une catégorie et le nombre d'images",
        color=0x3498db
    )
    embed.add_field(
        name="Catégories disponibles",
        value="`boy`, `girl`, `anime`, `aesthetic`, `cute`, `banner`, `match`",
        inline=False
    )
    embed.add_field(
        name="📌 Instructions",
        value="1️⃣ Tapez la catégorie\n2️⃣ Tapez le nombre (1-20)",
        inline=False
    )
    embed.set_footer(text="Timeout: 30s par étape")
    
    await ctx.send(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    # ---- ÉTAPE 1: CATÉGORIE ----
    await ctx.send("**1️⃣ Choisissez une catégorie :**")
    try:
        cat_msg = await bot.wait_for("message", timeout=30, check=check)
        category = cat_msg.content.strip().lower()
        
        valid_cats = ["boy", "girl", "anime", "aesthetic", "cute", "banner", "match"]
        if category not in valid_cats:
            return await ctx.send(f"❌ Catégorie invalide. Utilisez : {', '.join(valid_cats)}")
    except asyncio.TimeoutError:
        return await ctx.send("⏱️ Temps écoulé.")
    
    # ---- ÉTAPE 2: NOMBRE ----
    await ctx.send(f"**2️⃣ Combien d'images `{category}` ? (1-20) :**")
    try:
        count_msg = await bot.wait_for("message", timeout=30, check=check)
        count = int(count_msg.content.strip())
        count = max(1, min(count, 20))
    except ValueError:
        return await ctx.send("❌ Veuillez entrer un nombre valide.")
    except asyncio.TimeoutError:
        return await ctx.send("⏱️ Temps écoulé.")
    
    # ---- RÉCUPÉRATION ----
    loading_embed = discord.Embed(
        title="⏳ Récupération en cours...",
        description=f"Catégorie: `{category}`\nNombre: `{count}`",
        color=0xf39c12
    )
    status_msg = await ctx.send(embed=loading_embed)
    
    conn = db_connect()
    if not conn:
        return await status_msg.edit(content="❌ Erreur de connexion DB.")
    
    cur = conn.cursor()
    cur.execute(
        "SELECT url FROM images WHERE category=%s AND used=FALSE ORDER BY RANDOM() LIMIT %s",
        (category, count)
    )
    rows = cur.fetchall()
    urls = [r["url"] for r in rows]
    
    if urls:
        cur.execute("UPDATE images SET used=TRUE WHERE url = ANY(%s)", (urls,))
        conn.commit()
    
    cur.close()
    conn.close()
    
    # ---- ENVOI DES RÉSULTATS ----
    if not urls:
        return await status_msg.edit(
            embed=discord.Embed(
                title="❌ Aucune image disponible",
                description=f"Catégorie `{category}` épuisée.\nUtilisez `!stock` pour voir le stock.",
                color=0xe74c3c
            )
        )
    
    result_embed = discord.Embed(
        title="✅ Images récupérées !",
        description=f"**{len(urls)}** images de la catégorie `{category}`",
        color=0x2ecc71
    )
    await status_msg.edit(embed=result_embed)
    
    # Envoyer les URLs
    for i, url in enumerate(urls, 1):
        await ctx.send(f"`[{i}/{len(urls)}]` {url}")

# ----------------------
# COMMANDE !URL
# ----------------------
@bot.command(name="url")
async def url_cmd(ctx):
    """Commande pour importer des images depuis Pinterest"""
    
    embed = discord.Embed(
        title="📌 Import Pinterest",
        description="Remplissez les informations ci-dessous :",
        color=0xe74c3c
    )
    embed.add_field(name="1️⃣ URL Pinterest", value="Collez l'URL du board/profil", inline=False)
    embed.add_field(name="2️⃣ Catégorie", value="boy, girl, anime, aesthetic, cute, banner, match", inline=False)
    embed.add_field(name="3️⃣ Nombre", value="Combien d'images ? (1-50)", inline=False)
    embed.set_footer(text="Répondez dans l'ordre | Timeout: 60s par étape")
    
    await ctx.send(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    # ---- ÉTAPE 1: URL ----
    await ctx.send("**1️⃣ Entrez l'URL Pinterest :**")
    try:
        url_msg = await bot.wait_for("message", timeout=60, check=check)
        pinterest_url = url_msg.content.strip()
        
        # Validation basique
        if "pinterest" not in pinterest_url.lower():
            return await ctx.send("❌ L'URL doit contenir 'pinterest'")
    except asyncio.TimeoutError:
        return await ctx.send("⏱️ Temps écoulé.")
    
    # ---- ÉTAPE 2: CATÉGORIE ----
    await ctx.send("**2️⃣ Choisissez une catégorie :**\n`boy`, `girl`, `anime`, `aesthetic`, `cute`, `banner`, `match`")
    try:
        cat_msg = await bot.wait_for("message", timeout=60, check=check)
        category = cat_msg.content.strip().lower()
        
        valid_cats = ["boy", "girl", "anime", "aesthetic", "cute", "banner", "match"]
        if category not in valid_cats:
            return await ctx.send(f"❌ Catégorie invalide. Choisissez parmi : {', '.join(valid_cats)}")
    except asyncio.TimeoutError:
        return await ctx.send("⏱️ Temps écoulé.")
    
    # ---- ÉTAPE 3: NOMBRE ----
    await ctx.send("**3️⃣ Combien d'images ? (1-50) :**")
    try:
        count_msg = await bot.wait_for("message", timeout=60, check=check)
        count = int(count_msg.content.strip())
        count = max(1, min(count, 50))  # Limite entre 1 et 50
    except ValueError:
        return await ctx.send("❌ Veuillez entrer un nombre valide.")
    except asyncio.TimeoutError:
        return await ctx.send("⏱️ Temps écoulé.")
    
    # ---- RÉCAPITULATIF ----
    recap_embed = discord.Embed(
        title="✅ Récapitulatif",
        color=0x2ecc71
    )
    recap_embed.add_field(name="URL", value=pinterest_url, inline=False)
    recap_embed.add_field(name="Catégorie", value=category, inline=True)
    recap_embed.add_field(name="Nombre", value=str(count), inline=True)
    recap_embed.set_footer(text="Scraping en cours...")
    
    status_msg = await ctx.send(embed=recap_embed)
    
    # ---- LANCER LE SCRAPING ----
    try:
        scraped_urls = await scrape_pinterest(pinterest_url, count)
        
        if not scraped_urls:
            return await status_msg.edit(content="❌ Aucune image trouvée.")
        
        # ---- INSERTION EN DB ----
        conn = db_connect()
        if not conn:
            return await status_msg.edit(content="❌ Erreur de connexion DB.")
        
        cur = conn.cursor()
        inserted = 0
        
        for img_url in scraped_urls:
            try:
                cur.execute(
                    "INSERT INTO images (url, category, used) VALUES (%s, %s, FALSE) ON CONFLICT DO NOTHING",
                    (img_url, category)
                )
                if cur.rowcount > 0:
                    inserted += 1
            except Exception as e:
                logging.error(f"Erreur insertion: {e}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        # ---- RÉSULTAT FINAL ----
        final_embed = discord.Embed(
            title="✅ Import terminé !",
            color=0x2ecc71
        )
        final_embed.add_field(name="Trouvées", value=str(len(scraped_urls)), inline=True)
        final_embed.add_field(name="Insérées", value=str(inserted), inline=True)
        final_embed.add_field(name="Catégorie", value=category, inline=True)
        
        await status_msg.edit(embed=final_embed)
        
    except Exception as e:
        logging.error(f"Erreur scraping: {e}")
        await status_msg.edit(content=f"❌ Erreur: {str(e)}")

# ----------------------
# COMMANDE !STOCK
# ----------------------
@bot.command(name="stock")
async def stock_cmd(ctx):
    conn = db_connect()
    if not conn:
        return await ctx.send("❌ Erreur de connexion DB.")
    
    cur = conn.cursor()
    cur.execute("SELECT category, COUNT(*) AS total FROM images WHERE used=FALSE GROUP BY category ORDER BY category")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return await ctx.send("❌ Aucun stock disponible.")

    embed = discord.Embed(title="📊 Stock disponible", color=0xf1c40f)
    for r in rows:
        embed.add_field(name=r["category"], value=f"{r['total']} images", inline=False)
    
    embed.set_footer(text="Utilisez !pdp pour récupérer des images")
    await ctx.send(embed=embed)

# ----------------------
# EVENT READY
# ----------------------
@bot.event
async def on_ready():
    logging.info(f"Bot connecté : {bot.user}")
    await bot.change_presence(activity=discord.Game(name="!help pour les commandes"))

# ----------------------
# RUN
# ----------------------
def start_bot():
    db_init()
    bot.run(DISCORD_TOKEN)

Thread(target=run_flask).start()
start_bot()
