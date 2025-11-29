import discord
from discord.ext import commands
import os
import aiohttp
import asyncio
import logging
import sys
from threading import Thread
from flask import Flask
import urllib.parse
from bs4 import BeautifulSoup
import random
import re

# ======================================== 
# LOGGING
# ========================================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ======================================== 
# FLASK SERVER (Pour le monitoring)
# ========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Discord PFP actif!", 200

@app.route('/health')
def health():
    return {"status": "healthy"}, 200

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

# ======================================== 
# CONFIGURATION BOT
# ========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Session HTTP réutilisable
_session = None

async def get_session():
    """Obtenir ou créer une session HTTP"""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session

# ======================================== 
# RECHERCHE D'IMAGES - GOOGLE (Scraping amélioré)
# ========================================
async def search_google_images(query: str, count: int = 10) -> list:
    """Recherche d'images via Google Images avec extraction des vraies URLs"""
    try:
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        
        url = f"https://www.google.com/search?q={encoded_query}&tbm=isch&safe=active"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.google.com/'
        }
        
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                html = await response.text()
                images = []
                
                # Méthode 1 : Extraire depuis les données JSON de Google
                pattern = r'"ou":"(https?://[^"]+)"'
                matches = re.findall(pattern, html)
                
                for match in matches:
                    if len(images) >= count:
                        break
                    # Vérifier que c'est une vraie image
                    if any(ext in match.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                        # Nettoyer l'URL
                        clean_url = match.split('&')[0]
                        images.append(clean_url)
                
                # Méthode 2 : Parser avec BeautifulSoup si pas assez d'images
                if len(images) < count:
                    soup = BeautifulSoup(html, 'lxml')
                    img_tags = soup.find_all('img')
                    
                    for img in img_tags:
                        if len(images) >= count:
                            break
                        src = img.get('src') or img.get('data-src')
                        if src and src.startswith('http') and 'gstatic' not in src:
                            images.append(src)
                
                logger.info(f"✅ Google Images: {len(images)} images trouvées pour '{query}'")
                return images[:count]
            else:
                logger.warning(f"⚠️ Google Images: Status {response.status}")
                
    except asyncio.TimeoutError:
        logger.error(f"❌ Google Images: Timeout")
    except Exception as e:
        logger.error(f"❌ Google Images: {e}")
    return []

# ======================================== 
# RECHERCHE D'IMAGES - PEXELS API
# ========================================
async def search_pexels(query: str, count: int = 10) -> list:
    """Recherche d'images via Pexels API (gratuit)"""
    api_key = os.getenv('PEXELS_API_KEY')
    
    if not api_key:
        logger.warning("⚠️ PEXELS_API_KEY non définie")
        return []
    
    try:
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        
        url = f"https://api.pexels.com/v1/search?query={encoded_query}&per_page={count}&size=medium"
        
        headers = {
            'Authorization': api_key
        }
        
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                images = [photo['src']['large'] for photo in data.get('photos', [])]
                logger.info(f"✅ Pexels: {len(images)} images pour '{query}'")
                return images
            else:
                logger.warning(f"⚠️ Pexels: Status {response.status}")
                
    except asyncio.TimeoutError:
        logger.error(f"❌ Pexels: Timeout")
    except Exception as e:
        logger.error(f"❌ Pexels: {e}")
    return []

# ======================================== 
# RECHERCHE D'IMAGES - PIXABAY API
# ========================================
async def search_pixabay(query: str, count: int = 10) -> list:
    """Recherche d'images via Pixabay API (gratuit)"""
    api_key = os.getenv('PIXABAY_API_KEY')
    
    if not api_key:
        logger.warning("⚠️ PIXABAY_API_KEY non définie")
        return []
    
    try:
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        
        url = f"https://pixabay.com/api/?key={api_key}&q={encoded_query}&image_type=photo&per_page={count}"
        
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                images = [hit['largeImageURL'] for hit in data.get('hits', [])]
                logger.info(f"✅ Pixabay: {len(images)} images pour '{query}'")
                return images
            else:
                logger.warning(f"⚠️ Pixabay: Status {response.status}")
                
    except asyncio.TimeoutError:
        logger.error(f"❌ Pixabay: Timeout")
    except Exception as e:
        logger.error(f"❌ Pixabay: {e}")
    return []

# ======================================== 
# FONCTION PRINCIPALE DE RECHERCHE
# ========================================
async def search_images(query: str, count: int = 10) -> list:
    """Recherche d'images en combinant plusieurs sources"""
    all_images = []
    
    # Essayer toutes les sources en parallèle
    tasks = [
        search_pexels(query, count),
        search_pixabay(query, count),
        search_google_images(query, count)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, list):
            all_images.extend(result)
    
    # Mélanger et limiter
    random.shuffle(all_images)
    final_images = all_images[:count]
    
    logger.info(f"🎯 Total: {len(final_images)} images trouvées pour '{query}'")
    return final_images

# ======================================== 
# COMMANDE !pfp
# ========================================
@bot.command(name='pfp')
async def pfp_command(ctx, *, query: str = None):
    """Commande pour obtenir des photos de profil
    
    Usage: !pfp [boy/girl/anime/aesthetic...]
    """
    if not query:
        await ctx.send("❌ Usage: `!pfp <recherche>` (ex: `!pfp boy`, `!pfp anime girl`, `!pfp aesthetic`)")
        return
    
    # Message de chargement
    loading_msg = await ctx.send(f"🔍 Recherche d'images pour: **{query}**...")
    
    try:
        # Rechercher les images
        images = await search_images(query, count=5)
        
        if not images:
            await loading_msg.edit(content=f"❌ Aucune image trouvée pour: **{query}**")
            return
        
        # Supprimer le message de chargement
        await loading_msg.delete()
        
        # Envoyer les images avec embed
        for i, img_url in enumerate(images, 1):
            embed = discord.Embed(
                title=f"Photo de profil {i}/{len(images)}",
                description=f"Recherche: `{query}`",
                color=discord.Color.blue()
            )
            embed.set_image(url=img_url)
            embed.set_footer(text=f"Demandé par {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            
            # Pause entre les envois pour éviter le rate limit
            if i < len(images):
                await asyncio.sleep(0.5)
        
        logger.info(f"✅ Envoyé {len(images)} images à {ctx.author} pour '{query}'")
        
    except Exception as e:
        logger.error(f"❌ Erreur dans pfp_command: {e}")
        await ctx.send(f"❌ Erreur lors de la recherche: {str(e)}")

# ======================================== 
# COMMANDE !help (personnalisée)
# ========================================
@bot.command(name='help')
async def help_command(ctx):
    """Affiche l'aide du bot"""
    embed = discord.Embed(
        title="🤖 Bot PFP - Aide",
        description="Bot pour trouver des photos de profil",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="!pfp <recherche>",
        value="Recherche des photos de profil\nEx: `!pfp boy`, `!pfp anime girl`, `!pfp aesthetic`",
        inline=False
    )
    
    embed.add_field(
        name="Sources",
        value="🔹 Pexels API\n🔹 Pixabay API\n🔹 Google Images",
        inline=False
    )
    
    embed.set_footer(text="Créé avec ❤️")
    
    await ctx.send(embed=embed)

# ======================================== 
# ÉVÉNEMENTS BOT
# ========================================
@bot.event
async def on_ready():
    logger.info(f"✅ Bot connecté: {bot.user.name} (ID: {bot.user.id})")
    logger.info(f"🌐 Connecté à {len(bot.guilds)} serveur(s)")
    
    # Changer le statut du bot
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="!pfp | !help"
        )
    )

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Commande inconnue. Utilise `!help` pour voir les commandes disponibles.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant. Utilise `!help` pour voir l'usage correct.")
    else:
        logger.error(f"❌ Erreur: {error}")
        await ctx.send(f"❌ Une erreur est survenue: {str(error)}")

# ======================================== 
# NETTOYAGE
# ========================================
@bot.event
async def on_disconnect():
    global _session
    if _session and not _session.closed:
        await _session.close()
    logger.info("🔌 Session HTTP fermée")

# ======================================== 
# DÉMARRAGE
# ========================================
if __name__ == "__main__":
    # Vérifier le token Discord
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN non défini dans les variables d'environnement!")
        sys.exit(1)
    
    # Démarrer Flask dans un thread séparé
    logger.info("🚀 Démarrage du serveur Flask...")
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Démarrer le bot Discord
    logger.info("🤖 Démarrage du bot Discord...")
    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("⏹️ Arrêt du bot...")
    except Exception as e:
        logger.error(f"❌ Erreur critique: {e}")
        sys.exit(1)
