# pdp.py — version finale (option 2: uniquement ajouter colonnes si manquantes)

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
# HELP
# ----------------------
@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="Commandes", color=0x1abc9c)
    embed.add_field(name="!pdp", value="Menu pour envoyer des images depuis la DB.", inline=False)
    embed.add_field(name="!pdpui", value="Version alternative UI.", inline=False)
    embed.add_field(name="!stock", value="Voir le stock restant.", inline=False)
    embed.add_field(name="!import", value="Guide pour importer des images.", inline=False)
    await ctx.send(embed=embed)

# ----------------------
# IMPORT
# ----------------------
@bot.command(name="import")
async def import_cmd(ctx):
    embed = discord.Embed(title="Import Pinterest", color=0x8e44ad)
    embed.add_field(name="URL", value="Collez l’URL Pinterest.")
    embed.add_field(name="Catégorie", value="Ex: boy, girl, anime...")
    embed.add_field(name="Nombre", value="1–50")
    await ctx.send(embed=embed)

# ----------------------
# UI SELECT
# ----------------------
from discord.ui import View

class PdpCategoryView(View):
    def __init__(self):
        super().__init__(timeout=60)
        from discord.ui import Select
        self.add_item(Select(
            placeholder="Choisir catégorie",
            options=[
                discord.SelectOption(label="boy", value="boy"),
                discord.SelectOption(label="girl", value="girl"),
                discord.SelectOption(label="anime", value="anime"),
                discord.SelectOption(label="aesthetic", value="aesthetic"),
                discord.SelectOption(label="cute", value="cute"),
                discord.SelectOption(label="banner", value="banner"),
                discord.SelectOption(label="match", value="match")
            ],
            custom_id="category_select"
        ))

    async def interaction_check(self, interaction):
        return True

    @discord.ui.select(custom_id="category_select")
    async def select_callback(self, interaction, select):
        category = select.values[0]
        await interaction.response.send_message(f"Combien d’images pour {category}? (1–20)")

        def check(msg):
            return msg.author == interaction.user and msg.channel == interaction.channel

        try:
            msg = await bot.wait_for("message", timeout=20, check=check)
            count = max(1, min(int(msg.content), 20))
        except:
            return await interaction.followup.send("Temps dépassé.")

        # Fetch images
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT url FROM images WHERE category=%s AND used=FALSE ORDER BY RANDOM() LIMIT %s", (category, count))
        rows = cur.fetchall()
        urls = [r["url"] for r in rows]

        if urls:
            cur.execute("UPDATE images SET used=TRUE WHERE url = ANY(%s)", (urls,))
            conn.commit()

        cur.close(); conn.close()

        if not urls:
            return await interaction.followup.send("Aucune image.")

        for u in urls:
            await interaction.followup.send(u)

# ----------------------
# COMMANDES
# ----------------------
@bot.command(name="pdp")
async def pdp(ctx):
    embed = discord.Embed(title="Choisir catégorie", color=0x3498db)
    await ctx.send(embed=embed, view=PdpCategoryView())

@bot.command(name="pdpui")
async def pdp_ui(ctx):
    embed = discord.Embed(title="UI Catégories", color=0x9b59b6)
    await ctx.send(embed=embed, view=PdpCategoryView())

# ----------------------
# STOCK
# ----------------------
@bot.command(name="stock")
async def stock_cmd(ctx):
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT category, COUNT(*) AS total FROM images WHERE used=FALSE GROUP BY category ORDER BY category")
    rows = cur.fetchall()
    cur.close(); conn.close()

    if not rows:
        return await ctx.send("Aucun stock.")

    embed = discord.Embed(title="Stock disponible", color=0xf1c40f)
    for r in rows:
        embed.add_field(name=r["category"], value=f"{r['total']} images", inline=False)
    await ctx.send(embed=embed)

# ----------------------
# RUN
# ----------------------
def start_bot():
    db_init()
    asyncio.run(bot.start(DISCORD_TOKEN))

Thread(target=run_flask).start()
start_bot()
