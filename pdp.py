import discord
from discord.ext import commands
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import random
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

# Debug : Afficher si les variables sont chargées
print(f"TOKEN chargé: {'Oui' if TOKEN else 'Non'}")
print(f"DATABASE_URL chargé: {'Oui' if DATABASE_URL else 'Non'}")

if not TOKEN:
    print("❌ ERREUR: DISCORD_TOKEN introuvable dans .env")
    exit(1)

if not DATABASE_URL:
    print("❌ ERREUR: DATABASE_URL introuvable dans .env")
    exit(1)

# Intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Connexion à la base de données
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        print(f"❌ Erreur connexion BDD: {e}")
        return None

# Categories disponibles
CATEGORIES = {
    'anime': 'anime_pdp',
    'boy': 'boy_pdp',
    'girl': 'girl_pdp',
    'banner': 'banner',
    'aesthetic': 'aesthetic',
    'cute': 'cute_pdp'
}

@bot.event
async def on_ready():
    print(f'✅ {bot.user} est connecté!')
    print(f"✅ Prefix: !")
    print(f"✅ Prêt dans {len(bot.guilds)} serveur(s)")

@bot.command(name='help')
async def help_command(ctx):
    """Affiche toutes les commandes disponibles"""
    embed = discord.Embed(
        title="🎨 Bot PFP Discord - Aide",
        description="**Commandes disponibles** (prefix: `!`)",
        color=discord.Color.from_rgb(88, 101, 242)
    )
    
    # Commandes principales
    embed.add_field(
        name="**🖼️ `!pdp <catégorie>`**",
        value="```Recherche d'avatars par catégorie\nEx: !pdp anime```\n**Catégories:** `anime`, `boy`, `girl`, `aesthetic`, `cute`",
        inline=False
    )
    
    embed.add_field(
        name="**🎭 `!banner`**",
        value="```Obtenir un banner aléatoire pour Discord```",
        inline=False
    )
    
    embed.add_field(
        name="**📊 `!stock`**",
        value="```Voir le stock d'images disponibles```",
        inline=False
    )
    
    embed.add_field(
        name="**🏆 `!trending`**",
        value="```Top des catégories les plus populaires```",
        inline=False
    )
    
    # Section utilitaires
    embed.add_field(
        name="**⚙️ Utilitaires**",
        value="`!ping` • Vérifier la latence\n`!stats` • Statistiques complètes\n`!help` • Afficher cette aide",
        inline=False
    )
    
    # Fonctionnalités
    embed.add_field(
        name="✨ **Fonctionnalités**",
        value="🔍 Preview • ✂️ Crop 512x512 • 🎨 Qualité HD • 🔄 Rotation auto • 📦 Collections • 🔥 Tendances",
        inline=False
    )
    
    embed.set_footer(text="Développé avec ❤️ • Chaque image est unique - Pas de doublon !")
    embed.set_thumbnail(url=bot.user.display_avatar.url if bot.user else None)
    
    await ctx.send(embed=embed)

@bot.command(name='pdp')
async def pdp(ctx, category: str = None):
    """Obtenir une photo de profil aléatoire"""
    
    if not category:
        categories_list = ', '.join(CATEGORIES.keys())
        await ctx.send(f"❌ Veuillez spécifier une catégorie!\n📁 Catégories disponibles: `{categories_list}`\n💡 Exemple: `!pdp anime`")
        return
    
    category = category.lower()
    
    if category not in CATEGORIES:
        categories_list = ', '.join(CATEGORIES.keys())
        await ctx.send(f"❌ Catégorie invalide!\n📁 Catégories disponibles: `{categories_list}`")
        return
    
    db_category = CATEGORIES[category]
    
    try:
        conn = get_db_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion à la base de données!")
            return
            
        cur = conn.cursor()
        
        # Récupérer une image aléatoire "pending"
        cur.execute(
            "SELECT * FROM images WHERE category = %s AND status = 'pending' ORDER BY RANDOM() LIMIT 1",
            (db_category,)
        )
        
        image = cur.fetchone()
        
        if not image:
            await ctx.send(f"❌ Aucune image disponible dans la catégorie **{category}**!\n💡 Utilisez le panel pour ajouter des images.")
            cur.close()
            conn.close()
            return
        
        # Supprimer l'image (anti-doublon)
        cur.execute("DELETE FROM images WHERE id = %s", (image['id'],))
        conn.commit()
        
        # Créer un embed stylé
        embed = discord.Embed(
            title=f"🎨 {category.upper()} PFP",
            color=discord.Color.random()
        )
        embed.set_image(url=image['image_url'])
        embed.set_footer(text="✨ Image unique - Pas de doublon!")
        
        await ctx.send(embed=embed)
        
        print(f"✅ Image envoyée - Catégorie: {category}, ID: {image['id']}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        await ctx.send(f"❌ Une erreur est survenue: {str(e)}")

@bot.command(name='banner')
async def banner(ctx):
    """Obtenir un banner aléatoire"""
    
    try:
        conn = get_db_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion à la base de données!")
            return
            
        cur = conn.cursor()
        
        # Récupérer un banner aléatoire "pending"
        cur.execute(
            "SELECT * FROM images WHERE category = 'banner' AND status = 'pending' ORDER BY RANDOM() LIMIT 1"
        )
        
        image = cur.fetchone()
        
        if not image:
            await ctx.send(f"❌ Aucun banner disponible!\n💡 Utilisez le panel pour ajouter des banners.")
            cur.close()
            conn.close()
            return
        
        # Supprimer l'image (anti-doublon)
        cur.execute("DELETE FROM images WHERE id = %s", (image['id'],))
        conn.commit()
        
        # Créer un embed stylé
        embed = discord.Embed(
            title="🎨 BANNER",
            color=discord.Color.random()
        )
        embed.set_image(url=image['image_url'])
        embed.set_footer(text="✨ Image unique - Pas de doublon!")
        
        await ctx.send(embed=embed)
        
        print(f"✅ Banner envoyé - ID: {image['id']}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        await ctx.send(f"❌ Une erreur est survenue: {str(e)}")

@bot.command(name='stock')
async def stock(ctx):
    """Voir le nombre d'images disponibles par catégorie"""
    
    try:
        conn = get_db_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion à la base de données!")
            return
            
        cur = conn.cursor()
        
        # Compter les images par catégorie
        embed = discord.Embed(
            title="📊 Stock d'images disponibles",
            color=discord.Color.blue()
        )
        
        total = 0
        for display_name, db_name in CATEGORIES.items():
            cur.execute(
                "SELECT COUNT(*) as count FROM images WHERE category = %s AND status = 'pending'",
                (db_name,)
            )
            result = cur.fetchone()
            count = result['count'] if result else 0
            total += count
            
            emoji = "✅" if count > 0 else "❌"
            embed.add_field(
                name=f"{emoji} {display_name.capitalize()}",
                value=f"`{count}` image(s)",
                inline=True
            )
        
        embed.set_footer(text=f"Total: {total} image(s) disponible(s)")
        
        await ctx.send(embed=embed)
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        await ctx.send(f"❌ Une erreur est survenue: {str(e)}")

@bot.command(name='ping')
async def ping(ctx):
    """Vérifier si le bot est en ligne"""
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latence: `{latency}ms`",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name='stats')
async def stats(ctx):
    """Afficher les statistiques du bot"""
    try:
        conn = get_db_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion à la base de données!")
            return
            
        cur = conn.cursor()
        
        # Compter le total d'images
        cur.execute("SELECT COUNT(*) as count FROM images WHERE status = 'pending'")
        result = cur.fetchone()
        total_images = result['count'] if result else 0
        
        # Compter par catégorie
        cur.execute("SELECT category, COUNT(*) as count FROM images WHERE status = 'pending' GROUP BY category")
        categories = cur.fetchall()
        
        embed = discord.Embed(
            title="📊 Statistiques du Bot",
            color=discord.Color.purple()
        )
        
        embed.add_field(name="🖼️ Images totales", value=f"`{total_images}`", inline=True)
        embed.add_field(name="🌐 Serveurs", value=f"`{len(bot.guilds)}`", inline=True)
        embed.add_field(name="📡 Latence", value=f"`{round(bot.latency * 1000)}ms`", inline=True)
        
        if categories:
            cat_text = "\n".join([f"• {cat['category']}: `{cat['count']}`" for cat in categories])
            embed.add_field(name="📁 Par catégorie", value=cat_text, inline=False)
        
        embed.set_footer(text=f"Bot actif dans {len(bot.guilds)} serveur(s)")
        
        await ctx.send(embed=embed)
        
        cur.close()
        conn.close()
        
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")

@bot.command(name='trending')
async def trending(ctx):
    """Afficher les catégories les plus populaires"""
    try:
        conn = get_db_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion à la base de données!")
            return
            
        cur = conn.cursor()
        
        # Top catégories avec le plus d'images
        cur.execute("""
            SELECT category, COUNT(*) as count 
            FROM images 
            WHERE status = 'pending' 
            GROUP BY category 
            ORDER BY count DESC 
            LIMIT 5
        """)
        
        top_categories = cur.fetchall()
        
        embed = discord.Embed(
            title="🔥 Top Catégories Tendances",
            description="Les catégories les plus fournies",
            color=discord.Color.orange()
        )
        
        if top_categories:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, cat in enumerate(top_categories):
                category_name = cat['category'].replace('_pdp', '').replace('_', ' ').title()
                embed.add_field(
                    name=f"{medals[i]} {category_name}",
                    value=f"`{cat['count']}` images disponibles",
                    inline=False
                )
        else:
            embed.description = "❌ Aucune donnée disponible"
        
        embed.set_footer(text="Utilisez !pdp <catégorie> pour obtenir une image !")
        
        await ctx.send(embed=embed)
        
        cur.close()
        conn.close()
        
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")

# Lancer le bot
print("🚀 Démarrage du bot...")
bot.run(TOKEN)
