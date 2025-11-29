import discord
from discord.ext import commands
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
import random
from dotenv import load_dotenv
from flask import Flask, jsonify
from threading import Thread
import logging
from urllib.parse import urlparse

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Charger les variables d'environnement
load_dotenv()

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

# Validation des variables
if not TOKEN:
    logger.error("❌ DISCORD_TOKEN manquant !")
    exit(1)
if not DATABASE_URL:
    logger.error("❌ DATABASE_URL manquant !")
    exit(1)

logger.info("✅ Variables d'environnement chargées")

# Pool de connexions PostgreSQL
try:
    url = urlparse(DATABASE_URL)
    connection_pool = psycopg2.pool.SimpleConnectionPool(
        1, 10,
        host=url.hostname,
        port=url.port or 5432,
        database=url.path[1:],
        user=url.username,
        password=url.password,
        sslmode='require'
    )
    logger.info("✅ Pool PostgreSQL initialisé")
except Exception as e:
    logger.error(f"❌ Erreur pool DB: {e}")
    connection_pool = None

def get_db_connection():
    """Récupère une connexion depuis le pool"""
    try:
        if connection_pool:
            return connection_pool.getconn()
        else:
            return psycopg2.connect(DATABASE_URL, sslmode='require')
    except Exception as e:
        logger.error(f"❌ Erreur connexion DB: {e}")
        return None

def return_db_connection(conn):
    """Retourne une connexion au pool"""
    try:
        if connection_pool and conn:
            connection_pool.putconn(conn)
        elif conn:
            conn.close()
    except Exception as e:
        logger.error(f"❌ Erreur retour connexion: {e}")

# Flask pour Render Web Service
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "bot": bot.user.name if bot.is_ready() else "starting",
        "guilds": len(bot.guilds) if bot.is_ready() else 0,
        "users": len(bot.users) if bot.is_ready() else 0
    })

@app.route('/health')
def health():
    is_ready = bot.is_ready()
    return jsonify({
        "status": "ok" if is_ready else "starting",
        "bot_ready": is_ready,
        "latency_ms": round(bot.latency * 1000) if is_ready else None
    }), 200 if is_ready else 503

@app.route('/stats')
def stats_api():
    """API pour les stats"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "DB connection failed"}), 500
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT COUNT(*) as count FROM images WHERE status = 'pending'")
        pending = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM images WHERE status = 'sent'")
        sent = cursor.fetchone()['count']
        
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM images 
            WHERE status = 'pending'
            GROUP BY category
        """)
        stock = {row['category']: row['count'] for row in cursor.fetchall()}
        
        cursor.close()
        return_db_connection(conn)
        
        return jsonify({
            "guilds": len(bot.guilds),
            "users": len(bot.users),
            "pending": pending,
            "sent": sent,
            "stock": stock
        })
    except Exception as e:
        logger.error(f"❌ Erreur stats API: {e}")
        return jsonify({"error": str(e)}), 500

def run_flask():
    """Lance le serveur Flask"""
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Flask démarré sur port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Configuration du bot Discord
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# === ÉVÉNEMENTS ===

@bot.event
async def on_ready():
    logger.info(f'✅ {bot.user.name} connecté!')
    logger.info(f'✅ Actif dans {len(bot.guilds)} serveur(s)')
    await bot.change_presence(activity=discord.Game(name="!help pour aide"))

@bot.event
async def on_command_error(ctx, error):
    """Gestion globale des erreurs"""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Argument manquant ! Utilisez `!help` pour voir la syntaxe.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignorer les commandes inconnues
    else:
        logger.error(f"Erreur commande: {error}")
        await ctx.send("❌ Une erreur est survenue.")

# === COMMANDES ===

@bot.command(name='help')
async def help_command(ctx):
    """Affiche toutes les commandes disponibles"""
    embed = discord.Embed(
        title="🎨 Bot PFP Discord - Aide",
        description="**Commandes disponibles** (prefix: `!`)",
        color=0x3B82F6
    )
    
    embed.add_field(
        name="🖼️ !pdp <catégorie>",
        value="Envoie 15 photos de profil aléatoires\n**Ex:** `!pdp anime`\n**Catégories:** anime, boy, girl, aesthetic, cute",
        inline=False
    )
    
    embed.add_field(
        name="🎭 !banner",
        value="Envoie 15 banners Discord aléatoires",
        inline=False
    )
    
    embed.add_field(
        name="📊 !stock",
        value="Voir le nombre d'images disponibles par catégorie",
        inline=False
    )
    
    embed.add_field(
        name="🔥 !trending",
        value="Top 5 des catégories les plus populaires",
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Utilitaires",
        value="`!ping` - Latence du bot\n`!stats` - Statistiques globales\n`!help` - Cette aide",
        inline=False
    )
    
    embed.set_footer(text="Développé avec ❤️ • 15 images par commande")
    
    await ctx.send(embed=embed)

@bot.command(name='pdp')
async def pdp(ctx, category: str = None):
    """Envoie 15 photos de profil aléatoires"""
    
    if not category:
        await ctx.send("❌ Spécifiez une catégorie !\n**Ex:** `!pdp anime`\n**Catégories:** anime, boy, girl, aesthetic, cute")
        return
    
    category = category.lower()
    valid_categories = ['anime', 'boy', 'girl', 'aesthetic', 'cute']
    
    if category not in valid_categories:
        await ctx.send(f"❌ Catégorie invalide !\n**Disponibles:** {', '.join(valid_categories)}")
        return
    
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion à la base de données!")
            return
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Récupérer 15 images aléatoires
        cursor.execute("""
            SELECT id, image_url FROM images 
            WHERE category = %s AND status = 'pending'
            ORDER BY RANDOM()
            LIMIT 15
        """, (category,))
        
        images = cursor.fetchall()
        
        if not images:
            await ctx.send(f"❌ Aucune image disponible dans **{category}** !")
            cursor.close()
            return_db_connection(conn)
            return
        
        # Envoyer les URLs
        urls = [img['image_url'] for img in images]
        
        # Discord limite à 2000 caractères par message
        message = '\n'.join(urls[:15])
        if len(message) > 2000:
            # Diviser en plusieurs messages si nécessaire
            chunks = [urls[i:i+10] for i in range(0, len(urls), 10)]
            for chunk in chunks:
                await ctx.send('\n'.join(chunk))
        else:
            await ctx.send(message)
        
        # Marquer comme envoyées
        ids = [img['id'] for img in images]
        cursor.execute("""
            UPDATE images 
            SET status = 'sent', sent_at = NOW()
            WHERE id = ANY(%s)
        """, (ids,))
        
        conn.commit()
        cursor.close()
        return_db_connection(conn)
        
        logger.info(f"✅ {len(images)} images {category} envoyées à {ctx.author}")
        
    except Exception as e:
        logger.error(f"❌ Erreur pdp: {e}")
        await ctx.send("❌ Une erreur est survenue!")
        if conn:
            return_db_connection(conn)

@bot.command(name='banner')
async def banner(ctx):
    """Envoie 15 banners aléatoires"""
    
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion à la base de données!")
            return
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT id, image_url FROM images 
            WHERE category = 'banner' AND status = 'pending'
            ORDER BY RANDOM()
            LIMIT 15
        """)
        
        banners = cursor.fetchall()
        
        if not banners:
            await ctx.send("❌ Aucun banner disponible!")
            cursor.close()
            return_db_connection(conn)
            return
        
        # Envoyer les URLs
        urls = [b['image_url'] for b in banners]
        message = '\n'.join(urls)
        
        if len(message) > 2000:
            chunks = [urls[i:i+10] for i in range(0, len(urls), 10)]
            for chunk in chunks:
                await ctx.send('\n'.join(chunk))
        else:
            await ctx.send(message)
        
        # Marquer comme envoyés
        ids = [b['id'] for b in banners]
        cursor.execute("""
            UPDATE images 
            SET status = 'sent', sent_at = NOW()
            WHERE id = ANY(%s)
        """, (ids,))
        
        conn.commit()
        cursor.close()
        return_db_connection(conn)
        
        logger.info(f"✅ {len(banners)} banners envoyés à {ctx.author}")
        
    except Exception as e:
        logger.error(f"❌ Erreur banner: {e}")
        await ctx.send("❌ Une erreur est survenue!")
        if conn:
            return_db_connection(conn)

@bot.command(name='stock')
async def stock(ctx):
    """Afficher le stock d'images par catégorie"""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion à la base de données!")
            return
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM images 
            WHERE status = 'pending'
            GROUP BY category
            ORDER BY count DESC
        """)
        
        stocks = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) as total FROM images WHERE status = 'pending'")
        total = cursor.fetchone()['total']
        
        embed = discord.Embed(
            title="📊 Stock d'images disponibles",
            color=0x3B82F6
        )
        
        if stocks:
            for s in stocks:
                emoji = "✅" if s['count'] > 100 else "⚠️" if s['count'] > 20 else "❌"
                embed.add_field(
                    name=f"{emoji} {s['category'].capitalize()}",
                    value=f"**{s['count']:,}** image(s)",
                    inline=True
                )
        else:
            embed.description = "❌ Aucune image disponible"
        
        embed.set_footer(text=f"Total: {total:,} image(s) disponible(s)")
        
        await ctx.send(embed=embed)
        
        cursor.close()
        return_db_connection(conn)
        
    except Exception as e:
        logger.error(f"❌ Erreur stock: {e}")
        await ctx.send("❌ Une erreur est survenue!")
        if conn:
            return_db_connection(conn)

@bot.command(name='trending')
async def trending(ctx):
    """Afficher les catégories tendances"""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion à la base de données!")
            return
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM images 
            WHERE status = 'pending'
            GROUP BY category
            ORDER BY count DESC
            LIMIT 5
        """)
        
        trends = cursor.fetchall()
        
        embed = discord.Embed(
            title="🔥 Top Catégories",
            color=0xEF4444
        )
        
        if trends:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, trend in enumerate(trends):
                embed.add_field(
                    name=f"{medals[i]} {trend['category'].capitalize()}",
                    value=f"**{trend['count']:,}** images",
                    inline=False
                )
        else:
            embed.description = "❌ Aucune donnée"
        
        embed.set_footer(text="Utilisez !pdp <catégorie> pour 15 images")
        
        await ctx.send(embed=embed)
        
        cursor.close()
        return_db_connection(conn)
        
    except Exception as e:
        logger.error(f"❌ Erreur trending: {e}")
        await ctx.send("❌ Une erreur est survenue!")
        if conn:
            return_db_connection(conn)

@bot.command(name='ping')
async def ping(ctx):
    """Vérifier la latence du bot"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! **{latency}ms**")

@bot.command(name='stats')
async def stats(ctx):
    """Afficher les statistiques du bot"""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion à la base de données!")
            return
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT COUNT(*) as total FROM images WHERE status = 'pending'")
        pending = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM images WHERE status = 'sent'")
        sent = cursor.fetchone()['total']
        
        embed = discord.Embed(
            title="📈 Statistiques du Bot",
            color=0x10B981
        )
        
        embed.add_field(name="🔢 Serveurs", value=f"**{len(bot.guilds)}**", inline=True)
        embed.add_field(name="👥 Utilisateurs", value=f"**{len(bot.users):,}**", inline=True)
        embed.add_field(name="🏓 Latence", value=f"**{round(bot.latency * 1000)}ms**", inline=True)
        embed.add_field(name="📦 Disponibles", value=f"**{pending:,}**", inline=True)
        embed.add_field(name="✅ Envoyées", value=f"**{sent:,}**", inline=True)
        embed.add_field(name="📊 Total", value=f"**{pending + sent:,}**", inline=True)
        
        await ctx.send(embed=embed)
        
        cursor.close()
        return_db_connection(conn)
        
    except Exception as e:
        logger.error(f"❌ Erreur stats: {e}")
        await ctx.send("❌ Une erreur est survenue!")
        if conn:
            return_db_connection(conn)

# === DÉMARRAGE ===

if __name__ == "__main__":
    logger.info("🚀 Démarrage du bot Discord...")
    
    # Lancer Flask dans un thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("🌐 Serveur Flask démarré")
    
    # Démarrer le bot
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
    finally:
        if connection_pool:
            connection_pool.closeall()
            logger.info("🔒 Pool DB fermé")
