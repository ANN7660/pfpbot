import discord
from discord.ext import commands
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import random
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# Flask pour Render Web Service
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot PFP Discord is running!"

@app.route('/health')
def health():
    return {"status": "ok", "bot": "online"}

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# Charger les variables d'environnement
load_dotenv()

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

# Debug
print(f"TOKEN chargé: {'Oui' if TOKEN else 'Non'}")
print(f"DATABASE_URL chargé: {'Oui' if DATABASE_URL else 'Non'}")

if not TOKEN or not DATABASE_URL:
    print("❌ ERREUR : Variables d'environnement manquantes !")
    print("Assurez-vous que DISCORD_TOKEN et DATABASE_URL sont définis dans .env")
    exit(1)

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Connexion à la base de données
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    except Exception as e:
        print(f"❌ Erreur de connexion à la base : {e}")
        return None

# Événement : Bot prêt
@bot.event
async def on_ready():
    print(f'✅ {bot.user.name} est connecté!')
    print(f'✅ Prêt dans {len(bot.guilds)} serveur(s)')
    await bot.change_presence(activity=discord.Game(name="!help pour les commandes"))

# Commande : !help
@bot.command(name='help')
async def help_command(ctx):
    """Affiche toutes les commandes disponibles"""
    embed = discord.Embed(
        title="🎨 Bot PFP Discord - Aide",
        description="**Commandes disponibles** (prefix: `!`)",
        color=0x9b59b6
    )
    
    embed.add_field(
        name="🖼️ !pdp <catégorie>",
        value="Envoie plusieurs photos de profil aléatoires\nEx: `!pdp anime`\nCatégories: anime, boy, girl, aesthetic, cute",
        inline=False
    )
    
    embed.add_field(
        name="🎭 !banner",
        value="Envoie plusieurs banners aléatoires pour Discord",
        inline=False
    )
    
    embed.add_field(
        name="📊 !stock",
        value="Voir le nombre d'images disponibles par catégorie",
        inline=False
    )
    
    embed.add_field(
        name="🔥 !trending",
        value="Top des catégories les plus populaires",
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Utilitaires",
        value="`!ping` • Vérifier la latence\n`!stats` • Statistiques complètes\n`!help` • Afficher cette aide",
        inline=False
    )
    
    embed.add_field(
        name="✨ Fonctionnalités",
        value="🔍 Preview • ✂️ Crop 512x512 • 🎨 Qualité HD • 🔄 Rotation auto • 📦 Collections • 🔥 Tendances",
        inline=False
    )
    
    embed.set_footer(text="Développé avec ❤️ • Chaque image est unique - Pas de doublon !")
    
    await ctx.send(embed=embed)

# Commande : !pdp <category>
@bot.command(name='pdp')
async def pdp(ctx, category: str = None):
    """Envoie plusieurs photos de profil aléatoires"""
    
    if not category:
        await ctx.send("❌ Veuillez spécifier une catégorie !\nEx: `!pdp anime`\nCatégories disponibles: anime, boy, girl, aesthetic, cute")
        return
    
    category = category.lower()
    valid_categories = ['anime', 'boy', 'girl', 'aesthetic', 'cute']
    
    if category not in valid_categories:
        await ctx.send(f"❌ Catégorie invalide ! Choisissez parmi : {', '.join(valid_categories)}")
        return
    
    try:
        conn = get_db_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion à la base de données!")
            return
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Récupérer jusqu'à 5 images aléatoires
        cursor.execute("""
            SELECT id, image_url FROM images 
            WHERE category = %s AND status = 'pending'
            ORDER BY RANDOM()
            LIMIT 5
        """, (category,))
        
        images = cursor.fetchall()
        
        if not images:
            await ctx.send(f"❌ Aucune image disponible dans la catégorie **{category}**!")
            conn.close()
            return
        
        # Envoyer toutes les URLs en un seul message
        urls = [img['image_url'] for img in images]
        message = '\n'.join(urls)
        
        await ctx.send(message)
        
        # Marquer les images comme envoyées
        ids = [img['id'] for img in images]
        cursor.execute("""
            UPDATE images 
            SET status = 'sent', sent_at = NOW()
            WHERE id = ANY(%s)
        """, (ids,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur : {e}")
        await ctx.send("❌ Une erreur est survenue!")

# Commande : !banner
@bot.command(name='banner')
async def banner(ctx):
    """Envoie plusieurs banners aléatoires"""
    
    try:
        conn = get_db_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion à la base de données!")
            return
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Récupérer jusqu'à 5 banners aléatoires
        cursor.execute("""
            SELECT id, image_url FROM images 
            WHERE category = 'banner' AND status = 'pending'
            ORDER BY RANDOM()
            LIMIT 5
        """)
        
        banners = cursor.fetchall()
        
        if not banners:
            await ctx.send("❌ Aucun banner disponible!")
            conn.close()
            return
        
        # Envoyer toutes les URLs en un seul message
        urls = [banner['image_url'] for banner in banners]
        message = '\n'.join(urls)
        
        await ctx.send(message)
        
        # Marquer les banners comme envoyés
        ids = [banner['id'] for banner in banners]
        cursor.execute("""
            UPDATE images 
            SET status = 'sent', sent_at = NOW()
            WHERE id = ANY(%s)
        """, (ids,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur : {e}")
        await ctx.send("❌ Une erreur est survenue!")

# Commande : !stock
@bot.command(name='stock')
async def stock(ctx):
    """Afficher le stock d'images par catégorie"""
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
            color=0x3498db
        )
        
        if stocks:
            for stock in stocks:
                emoji = "✅" if stock['count'] > 0 else "❌"
                embed.add_field(
                    name=f"{emoji} {stock['category'].capitalize()}",
                    value=f"{stock['count']} image(s)",
                    inline=True
                )
        else:
            embed.description = "❌ Aucune image disponible"
        
        embed.set_footer(text=f"Total: {total} image(s) disponible(s)")
        
        await ctx.send(embed=embed)
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur : {e}")
        await ctx.send("❌ Une erreur est survenue!")

# Commande : !trending
@bot.command(name='trending')
async def trending(ctx):
    """Afficher les catégories tendances"""
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
            title="🔥 Top Catégories Tendances",
            color=0xe74c3c
        )
        
        if trends:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, trend in enumerate(trends):
                embed.add_field(
                    name=f"{medals[i]} {trend['category'].capitalize()}",
                    value=f"{trend['count']} images disponibles",
                    inline=False
                )
        else:
            embed.description = "❌ Aucune donnée disponible"
        
        embed.set_footer(text="Utilisez !pdp <catégorie> pour obtenir une image !")
        
        await ctx.send(embed=embed)
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur : {e}")
        await ctx.send("❌ Une erreur est survenue!")

# Commande : !ping
@bot.command(name='ping')
async def ping(ctx):
    """Vérifier la latence du bot"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latence: {latency}ms")

# Commande : !stats
@bot.command(name='stats')
async def stats(ctx):
    """Afficher les statistiques du bot"""
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
            color=0x2ecc71
        )
        
        embed.add_field(name="🔢 Total serveurs", value=len(bot.guilds), inline=True)
        embed.add_field(name="👥 Total utilisateurs", value=len(bot.users), inline=True)
        embed.add_field(name="🏓 Latence", value=f"{round(bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="📦 Images disponibles", value=pending, inline=True)
        embed.add_field(name="✅ Images envoyées", value=sent, inline=True)
        embed.add_field(name="📊 Total", value=pending + sent, inline=True)
        
        await ctx.send(embed=embed)
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur : {e}")
        await ctx.send("❌ Une erreur est survenue!")

# Lancer le bot
if __name__ == "__main__":
    print("🚀 Démarrage du bot...")
    
    # Lancer Flask dans un thread séparé
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("🌐 Serveur Flask démarré")
    
    bot.run(TOKEN)
