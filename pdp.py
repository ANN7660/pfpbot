# FULL UPDATED BOT CODE
# (Your consolidated, corrected, optimized complete file)

import os
import asyncio
import logging
import requests
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
from discord import Intents
from discord.ui import View, Select

# ----------------------
# ENVIRONMENT VARIABLES
# ----------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PORT = int(os.getenv("PORT", 10000))

logging.basicConfig(level=logging.INFO)

# ----------------------
# FLASK KEEP-ALIVE SERVER
# ----------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot online"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ----------------------
# DATABASE POOL
# ----------------------
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(
        1, 20,
        dsn=DATABASE_URL,
        cursor_factory=RealDictCursor
    )
    logging.info("PostgreSQL pool initialisé")
except Exception as e:
    logging.error(f"Erreur d'initialisation du pool DB: {e}")
    db_pool = None


def get_conn():
    if not db_pool:
        logging.error("Pool DB indisponible.")
        return None
    try:
        return db_pool.getconn()
    except Exception as e:
        logging.error(f"Erreur DB getconn: {e}")
        return None


def release_conn(conn):
    if db_pool and conn:
        db_pool.putconn(conn)

# ----------------------
# DISCORD BOT
# ----------------------
intents = Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ----------------------
# WEBHOOK
# ----------------------

def send_webhook(message: str):
    if not WEBHOOK_URL:
        logging.error("Webhook manquant")
        return
    try:
        requests.post(WEBHOOK_URL, json={"content": message})
    except Exception as e:
        logging.error(f"Erreur webhook: {e}")

# ----------------------
# HELP COMMAND
# ----------------------
@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="Liste des commandes", color=0x1abc9c)
    embed.add_field(name="!pdp", value="Menu interactif pour choisir une catégorie et envoyer des images.", inline=False)
    embed.add_field(name="!pdpui", value="Version alternative du menu.", inline=False)
    embed.add_field(name="!import", value="Affiche les instructions pour importer des images Pinterest dans la DB.", inline=False)
    embed.add_field(name="!url", value="Ancienne méthode de recherche.", inline=False)
    embed.add_field(name="!stock", value="Affiche le stock d’images disponibles par catégorie.", inline=False)
    embed.set_footer(text="Bot Pinterest – PostgreSQL")
    await ctx.send(embed=embed)

# ----------------------
# IMPORT COMMAND
# ----------------------
@bot.command(name="import")
async def import_cmd(ctx):
    embed = discord.Embed(title="Import Pinterest", color=0x8e44ad)
    embed.add_field(name="URL Pinterest", value="Collez l’URL.", inline=False)
    embed.add_field(name="Catégorie", value="boy, girl, anime, cute...", inline=False)
    embed.add_field(name="Nombre", value="max 50.", inline=False)
    await ctx.send(embed=embed)

# ----------------------
# CATEGORY UI
# ----------------------
class PdpCategoryView(View):
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
            discord.SelectOption(label="match", value="match"),
        ],
    )
    async def select_callback(self, interaction: discord.Interaction, select):
        category = select.values[0]
        await interaction.response.send_message(f"Combien d’images pour **{category}** ? (1-20)")

        def check(msg):
            return msg.author == interaction.user and msg.channel == interaction.channel

        try:
            msg = await bot.wait_for("message", timeout=20, check=check)
            count = max(1, min(int(msg.content), 20))
        except:
            await interaction.followup.send("Temps écoulé.")
            return

        conn = get_conn()
        if not conn:
            await interaction.followup.send("Erreur base de données.")
            return

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT url FROM images
                    WHERE category=%s AND used=FALSE
                    ORDER BY RANDOM()
                    LIMIT %s
                    """,
                    (category, count),
                )
                rows = cur.fetchall()
                urls = [r["url"] for r in rows]

                if urls:
                    cur.execute(
                        "UPDATE images SET used=TRUE WHERE url = ANY(%s)", (urls,)
                    )
                    conn.commit()
        finally:
            release_conn(conn)

        if not urls:
            await interaction.followup.send(f"Aucune image trouvée pour {category}.")
            return

        for url in urls:
            await interaction.followup.send(url)

# ----------------------
# PDP COMMANDS
# ----------------------
@bot.command(name="pdpui")
async def pdp_ui(ctx):
    embed = discord.Embed(title="Choisir catégorie", color=0x9b59b6)
    await ctx.send(embed=embed, view=PdpCategoryView())


@bot.command(name="pdp")
async def pdp(ctx):
    embed = discord.Embed(title="Choisir catégorie", color=0x3498db)
    await ctx.send(embed=embed, view=PdpCategoryView())

# ----------------------
# STOCK COMMAND
# ----------------------
@bot.command(name="stock")
async def stock_cmd(ctx):
    conn = get_conn()
    if not conn:
        await ctx.send("La base de données est indisponible.")
        return

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT category, COUNT(*) AS total
                FROM images
                WHERE used = FALSE
                GROUP BY category
                ORDER BY category ASC
                """
            )
            rows = cur.fetchall()

        if not rows:
            await ctx.send("Aucune image disponible.")
            return

        embed = discord.Embed(
            title="Stock disponible", description="Images non utilisées", color=0x2ecc71
        )

        for row in rows:
            embed.add_field(name=row["category"], value=f"{row['total']} images", inline=False)

        await ctx.send(embed=embed)

    finally:
        release_conn(conn)

# ----------------------
# RUN BOT + FLASK
# ----------------------

def start_bot():
    asyncio.run(bot.start(DISCORD_TOKEN))

Thread(target=run_flask).start()
start_bot()
