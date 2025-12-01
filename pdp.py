# Code complet refait et corrigé

```python
import os
import asyncio
import logging
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
from discord import Intents

# ----------------------
# ENV VARIABLES
# ----------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PORT = int(os.getenv("PORT", 10000))

logging.basicConfig(level=logging.INFO)

# ----------------------
# FLASK SERVER
# ----------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot online"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ----------------------
# DATABASE
# ----------------------
def db_connect():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        logging.info("PostgreSQL connecté")
        return conn
    except Exception as e:
        logging.error(f"Erreur DB: {e}")
        return None

# ----------------------
# DATABASE QUERY IMAGES
# ----------------------
def db_get_images(query: str, limit=10):
    conn = db_connect()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT url
            FROM images
            WHERE category ILIKE %s
            LIMIT %s
        """, (f"%{query}%", limit))
        rows = cur.fetchall()
        return [row["url"] for row in rows]
    except Exception as e:
        logging.error(f"Erreur DB select: {e}")
        return []
    finally:
        conn.close()

# ----------------------
# DISCORD BOT
# ----------------------
intents = Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------------
# WEBHOOK ENVOI
# ----------------------
def send_webhook(msg):
    if not WEBHOOK_URL:
        logging.error("Webhook manquant")
        return
    try:
        requests.post(WEBHOOK_URL, json={"content": msg})
    except Exception as e:
        logging.error(f"Webhook err: {e}")

# ----------------------
# COMMANDES + MENUS INTERACTIFS
# ----------------------

@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="Liste des commandes", color=0x1abc9c)
    embed.add_field(name="!pdp", value="Ouvre le menu interactif pour choisir une catégorie et le nombre d'images à envoyer depuis la base de données.", inline=False)
    embed.add_field(name="!pdpui", value="Version alternative ouvrant directement l'UI.", inline=False)
    embed.add_field(name="!import", value="Affiche les instructions pour importer des images Pinterest dans la DB.", inline=False)
    embed.add_field(name="!url", value="(si activé) Recherche d’images via l’ancienne méthode.", inline=False)
    embed.set_footer(text="Bot Pinterest – Base de données PostgreSQL")
    await ctx.send(embed=embed)

# ----------------------
# COMMANDES + MENUS INTERACTIFS ORIGINAUX
# ----------------------
from discord.ui import View, Select

@bot.command(name="import")
async def import_cmd(ctx):
    embed = discord.Embed(title="Import Pinterest", color=0x8e44ad)
    embed.add_field(name="URL Pinterest", value="Collez votre URL ici.", inline=False)
    embed.add_field(name="Catégorie", value="Ex: boy, girl, anime, aesthetic", inline=False)
    embed.add_field(name="Nombre", value="Nombre d'images à importer (max 50)", inline=False)
    embed.set_footer(text="Utiliser la commande: !pfp <query>")
    await ctx.send(embed=embed)

# ----------------------
# UI INTERACTIVE POUR !pdp

class PdpCategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.select(
        placeholder="Choisir une catégorie",
        options=[
            discord.SelectOption(label="boy", value="boy"),
            discord.SelectOption(label="girl", value="girl"),
            discord.SelectOption(label="anime", value="anime"),
            discord.SelectOption(label="aesthetic", value="aesthetic"),
            discord.SelectOption(label="cute", value="cute"),
            discord.SelectOption(label="banner", value="banner"),
            discord.SelectOption(label="match", value="match")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select):
        category = select.values[0]
        await interaction.response.send_message(f"Combien d’images pour **{category}** ? (1‑20)")

        def check(msg):
            return msg.author == interaction.user and msg.channel == interaction.channel

        try:
            msg = await bot.wait_for("message", timeout=20, check=check)
            count = max(1, min(int(msg.content), 20))
        except:
            await interaction.followup.send("Temps dépassé.")
            return

        # Fetch DB
        try:
            conn = db_connect()
            cur = conn.cursor()
            cur.execute("SELECT url FROM images WHERE category=%s AND used=FALSE ORDER BY RANDOM() LIMIT %s", (category, count))
            rows = cur.fetchall()
            urls = [r["url"] for r in rows]

            if urls:
                cur.execute("UPDATE images SET used=TRUE WHERE url = ANY(%s)", (urls,))
                conn.commit()
        finally:
            cur.close()
            conn.close()

        if not urls:
            await interaction.followup.send(f"Aucune image trouvée pour {category}")
            return

        for url in urls:
            await interaction.followup.send(url)

@bot.command(name="pdpui")
async def pdp_ui(ctx):
    embed = discord.Embed(title="Choisis ta catégorie", description="Sélectionne une catégorie ci‑dessous.", color=0x9b59b6)
    await ctx.send(embed=embed, view=PdpCategoryView())

# ----------------------
# COMMANDES ORIGINALES

@bot.command(name="pdp")
async def pdp(ctx):
    embed = discord.Embed(title="Choisis une catégorie", description="Sélectionne une catégorie ci‑dessous.", color=0x3498db)
    await ctx.send(embed=embed, view=PdpCategoryView())

# ----------------------
# RUN BOTH
# ----------------------
def start_bot():
    asyncio.run(bot.start(DISCORD_TOKEN))():
    asyncio.run(bot.start(DISCORD_TOKEN))

Thread(target=run_flask).start()
start_bot()
```
