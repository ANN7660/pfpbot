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
import random
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

    # Crée la table si elle n'existe pas
    cur.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id SERIAL PRIMARY KEY,
            url TEXT UNIQUE NOT NULL,
            category TEXT,
            used BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Ajoute colonnes si manquantes (pour migration)
    try:
        cur.execute("""
            ALTER TABLE images
            ADD COLUMN IF NOT EXISTS used BOOLEAN DEFAULT FALSE;
        """)
    except Exception as e:
        logging.warning(f"Column 'used' might already exist: {e}")

    try:
        cur.execute("""
            ALTER TABLE images
            ADD COLUMN IF NOT EXISTS category TEXT;
        """)
    except Exception as e:
        logging.warning(f"Column 'category' might already exist: {e}")

    # Crée un index pour améliorer les performances
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_category_used 
        ON images(category, used) WHERE used = FALSE;
    """)

    conn.commit()
    cur.close()
    conn.close()
    logging.info("Structure DB vérifiée et créée si nécessaire.")

# ----------------------
# DISCORD BOT
# ----------------------
intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ----------------------
# EVENT READY
# ----------------------
@bot.event
async def on_ready():
    logging.info(f"Bot connecté : {bot.user}")
    
    # Vérifier la DB au démarrage
    conn = db_connect()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as total FROM images")
            result = cur.fetchone()
            total = result['total'] if result else 0
            cur.close()
            conn.close()
            logging.info(f"✅ DB OK - {total} images en stock")
        except Exception as e:
            logging.error(f"⚠️ Erreur DB au démarrage: {e}")
            logging.info("Tentative de réinitialisation...")
            conn.close()
            db_init()
    else:
        logging.error("❌ Impossible de se connecter à la DB")
    
    await bot.change_presence(activity=discord.Game(name="!help pour les commandes"))

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
        value="Importer des images manuellement (copier-coller les URLs)",
        inline=False
    )
    embed.add_field(
        name="📊 !stock",
        value="Voir le stock restant par catégorie",
        inline=False
    )
    embed.add_field(
        name="🧪 !test",
        value="Tester la détection d'URLs (debug)",
        inline=False
    )
    embed.add_field(
        name="❓ !help",
        value="Afficher ce message",
        inline=False
    )
    embed.set_footer(text="Bot Pinterest • Import manuel (Pinterest bloque le scraping auto)")
    await ctx.send(embed=embed)

# ----------------------
# COMMANDE !TEST (DEBUG)
# ----------------------
@bot.command(name="test")
async def test_cmd(ctx):
    """Commande de test pour vérifier la détection d'URLs"""
    
    embed = discord.Embed(
        title="🧪 Test de détection d'URLs",
        description="Collez vos URLs pour tester la détection",
        color=0x9b59b6
    )
    await ctx.send(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for("message", timeout=60, check=check)
        content = msg.content
        
        # Afficher le contenu brut
        await ctx.send(f"**Contenu reçu ({len(content)} caractères):**\n```{content[:500]}```")
        
        # Tester la détection
        url_pattern = r'https?://[^\s<>"\'\)]+(?:\.jpg|\.jpeg|\.png|\.gif|\.webp)?'
        urls = re.findall(url_pattern, content, re.IGNORECASE)
        
        if urls:
            result = "\n".join([f"{i+1}. {url}" for i, url in enumerate(urls)])
            await ctx.send(f"**URLs détectées ({len(urls)}):**\n```{result[:1500]}```")
        else:
            await ctx.send("❌ Aucune URL détectée")
            
    except asyncio.TimeoutError:
        await ctx.send("⏱️ Temps écoulé.")

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
        return await status_msg.edit(
            embed=discord.Embed(
                title="❌ Erreur de connexion",
                description="Impossible de se connecter à la base de données.",
                color=0xe74c3c
            )
        )
    
    cur = conn.cursor()
    
    try:
        cur.execute(
            "SELECT url FROM images WHERE category=%s AND used=FALSE ORDER BY RANDOM() LIMIT %s",
            (category, count)
        )
        rows = cur.fetchall()
        urls = [r["url"] for r in rows]
        
        if urls:
            cur.execute("UPDATE images SET used=TRUE WHERE url = ANY(%s)", (urls,))
            conn.commit()
    except psycopg2.errors.UndefinedColumn as e:
        logging.error(f"Erreur de colonne DB: {e}")
        cur.close()
        conn.close()
        return await status_msg.edit(
            embed=discord.Embed(
                title="❌ Erreur de structure DB",
                description="La table n'est pas correctement initialisée. Redémarrez le bot.",
                color=0xe74c3c
            )
        )
    except Exception as e:
        logging.error(f"Erreur lors de la récupération: {e}")
        cur.close()
        conn.close()
        return await status_msg.edit(
            embed=discord.Embed(
                title="❌ Erreur",
                description=f"Une erreur est survenue: {str(e)}",
                color=0xe74c3c
            )
        )
    
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
# COMMANDE !URL (VERSION MANUELLE + WEBHOOK)
# ----------------------
@bot.command(name="url")
async def url_cmd(ctx):
    """Import manuel d'images (copier-coller les URLs)"""
    
    embed = discord.Embed(
        title="📌 Import d'images",
        description="**Méthode manuelle** (Pinterest bloque le scraping automatique)",
        color=0xe74c3c
    )
    embed.add_field(
        name="📝 Instructions",
        value=(
            "1️⃣ Allez sur Pinterest et ouvrez le board\n"
            "2️⃣ Clic droit sur chaque image → **Copier l'adresse de l'image**\n"
            "3️⃣ Collez toutes les URLs ici (une par ligne ou séparées par des espaces)\n"
            "4️⃣ Choisissez combien importer\n"
            "5️⃣ Choisissez la catégorie"
        ),
        inline=False
    )
    embed.add_field(
        name="💡 Astuce",
        value="Collez 50+ URLs, puis choisissez d'en importer 10, 20, etc.",
        inline=False
    )
    embed.set_footer(text="Timeout: 120s")
    
    await ctx.send(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    # ---- ÉTAPE 1: RÉCUPÉRER LES URLs ----
    await ctx.send("**📎 Collez vos URLs d'images (une par ligne ou toutes d'un coup) :**")
    try:
        urls_msg = await bot.wait_for("message", timeout=120, check=check)
        
        content = urls_msg.content
        
        # Méthode 1: Diviser par lignes et espaces
        lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        all_parts = []
        for line in lines:
            all_parts.extend(line.split())
        
        # Méthode 2: Regex pour capturer toutes les URLs
        url_pattern = r'https?://[^\s<>"\'\)]+(?:\.jpg|\.jpeg|\.png|\.gif|\.webp)?'
        regex_urls = re.findall(url_pattern, content, re.IGNORECASE)
        
        # Combiner les deux méthodes
        all_urls = list(set(all_parts + regex_urls))
        
        # Filtrer les URLs valides d'images
        image_urls = []
        for url in all_urls:
            url = url.strip()
            # Accepter les URLs Pinterest ou directement les URLs d'images
            if any(domain in url.lower() for domain in ['pinimg.com', 'pinterest.com', '.jpg', '.jpeg', '.png', '.gif', '.webp']):
                if url not in image_urls:
                    image_urls.append(url)
        
        if not image_urls:
            return await ctx.send(
                "❌ Aucune URL d'image trouvée.\n\n"
                "**Astuce:** Faites clic droit sur une image Pinterest → **Copier l'adresse de l'image**\n"
                "Les URLs doivent contenir `pinimg.com` ou se terminer par `.jpg`, `.png`, etc."
            )
        
        # Afficher un aperçu
        preview = "\n".join([f"• {url[:60]}..." if len(url) > 60 else f"• {url}" for url in image_urls[:5]])
        if len(image_urls) > 5:
            preview += f"\n... et {len(image_urls) - 5} autres"
        
        confirm_embed = discord.Embed(
            title=f"✅ {len(image_urls)} URLs détectées",
            description=f"**Aperçu:**\n{preview}",
            color=0x2ecc71
        )
        await ctx.send(embed=confirm_embed)
        
    except asyncio.TimeoutError:
        return await ctx.send("⏱️ Temps écoulé.")
    
    # ---- ÉTAPE 2: NOMBRE À IMPORTER ----
    await ctx.send(f"**2️⃣ Combien d'images importer ? (1-{len(image_urls)}) :**\n*Tapez `all` pour tout importer*")
    try:
        count_msg = await bot.wait_for("message", timeout=60, check=check)
        count_input = count_msg.content.strip().lower()
        
        if count_input == "all":
            count = len(image_urls)
        else:
            count = int(count_input)
            count = max(1, min(count, len(image_urls)))
        
        # Sélectionner aléatoirement si moins que le total
        if count < len(image_urls):
            selected_urls = random.sample(image_urls, count)
        else:
            selected_urls = image_urls
        
        await ctx.send(f"✅ **{count} images sélectionnées** sur {len(image_urls)}")
        
    except ValueError:
        return await ctx.send("❌ Veuillez entrer un nombre valide ou 'all'.")
    except asyncio.TimeoutError:
        return await ctx.send("⏱️ Temps écoulé.")
    
    # ---- ÉTAPE 3: CATÉGORIE ----
    await ctx.send("**3️⃣ Choisissez une catégorie :**\n`boy`, `girl`, `anime`, `aesthetic`, `cute`, `banner`, `match`")
    try:
        cat_msg = await bot.wait_for("message", timeout=60, check=check)
        category = cat_msg.content.strip().lower()
        
        valid_cats = ["boy", "girl", "anime", "aesthetic", "cute", "banner", "match"]
        if category not in valid_cats:
            return await ctx.send(f"❌ Catégorie invalide. Choisissez parmi : {', '.join(valid_cats)}")
    except asyncio.TimeoutError:
        return await ctx.send("⏱️ Temps écoulé.")
    
    # ---- INSERTION EN DB ----
    status_msg = await ctx.send("⏳ **Insertion en cours...**")
    
    conn = db_connect()
    if not conn:
        return await status_msg.edit(content="❌ Erreur de connexion DB.")
    
    cur = conn.cursor()
    inserted = 0
    duplicates = 0
    inserted_urls = []
    
    for img_url in selected_urls:
        try:
            cur.execute(
                "INSERT INTO images (url, category, used) VALUES (%s, %s, FALSE)",
                (img_url, category)
            )
            if cur.rowcount > 0:
                inserted += 1
                inserted_urls.append(img_url)
            conn.commit()
        except psycopg2.IntegrityError:
            duplicates += 1
            conn.rollback()
        except Exception as e:
            logging.error(f"Erreur insertion: {e}")
            conn.rollback()
    
    cur.close()
    conn.close()
    
    # ---- ENVOI VIA WEBHOOK ----
    if inserted > 0 and WEBHOOK_URL:
        webhook_status = await ctx.send("📤 **Envoi des images vers le serveur privé...**")
        
        try:
            # Envoyer par batch de 10 images
            for i in range(0, len(inserted_urls), 10):
                batch = inserted_urls[i:i+10]
                
                webhook_embed = {
                    "embeds": [{
                        "title": f"📥 Nouvelles images - {category.upper()}",
                        "description": f"**Batch {i//10 + 1}** • {len(batch)} images",
                        "color": 3447003,
                        "fields": [
                            {
                                "name": f"Image {j+1}",
                                "value": f"[Voir l'image]({url})",
                                "inline": False
                            } for j, url in enumerate(batch)
                        ],
                        "footer": {
                            "text": f"Catégorie: {category} • Total inséré: {inserted}"
                        }
                    }]
                }
                
                response = requests.post(WEBHOOK_URL, json=webhook_embed, timeout=10)
                
                if response.status_code == 204:
                    await asyncio.sleep(1)  # Éviter le rate limit
                else:
                    logging.error(f"Webhook error: {response.status_code}")
            
            await webhook_status.edit(content="✅ **Images envoyées au serveur privé !**")
            
        except Exception as e:
            logging.error(f"Erreur webhook: {e}")
            await webhook_status.edit(content="⚠️ **Erreur lors de l'envoi au serveur privé**")
    
    # ---- RÉSULTAT FINAL ----
    final_embed = discord.Embed(
        title="✅ Import terminé !",
        color=0x2ecc71
    )
    final_embed.add_field(name="📊 URLs détectées", value=str(len(image_urls)), inline=True)
    final_embed.add_field(name="🎯 Sélectionnées", value=str(len(selected_urls)), inline=True)
    final_embed.add_field(name="✅ Insérées", value=str(inserted), inline=True)
    final_embed.add_field(name="⚠️ Doublons", value=str(duplicates), inline=True)
    final_embed.add_field(name="📁 Catégorie", value=category, inline=False)
    
    if inserted > 0 and WEBHOOK_URL:
        final_embed.add_field(name="📤 Webhook", value="✅ Envoyées au serveur privé", inline=False)
    
    await status_msg.edit(content=None, embed=final_embed)

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
# RUN
# ----------------------
def start_bot():
    db_init()
    bot.run(DISCORD_TOKEN)

Thread(target=run_flask).start()
start_bot()
