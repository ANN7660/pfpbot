import discord
from discord.ext import commands
from discord.ui import View, Button, Select
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
from io import BytesIO
from PIL import Image, ImageDraw
from collections import defaultdict, deque
from datetime import datetime, timedelta
import hashlib

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
# CONFIGURATION
# ========================================
class Config:
    MAX_REQUESTS_PER_MINUTE = 30
    CACHE_TTL = 3600
    REQUEST_TIMEOUT = 15
    MAX_IMAGES = 10

# ======================================== 
# RATE LIMITER
# ========================================
class RateLimiter:
    def __init__(self, max_per_minute=30):
        self.max_per_minute = max_per_minute
        self.requests = deque()
    
    async def acquire(self):
        now = datetime.now()
        while self.requests and self.requests[0] < now - timedelta(minutes=1):
            self.requests.popleft()
        
        if len(self.requests) >= self.max_per_minute:
            wait_time = (self.requests[0] + timedelta(minutes=1) - now).total_seconds()
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        
        self.requests.append(datetime.now())

rate_limiter = RateLimiter()

# ======================================== 
# CACHE SIMPLE
# ========================================
class SimpleCache:
    def __init__(self, ttl=3600):
        self.cache = {}
        self.ttl = ttl
    
    def get(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl):
                return data
            del self.cache[key]
        return None
    
    def set(self, key, value):
        self.cache[key] = (value, datetime.now())
        if len(self.cache) > 1000:
            oldest = min(self.cache.items(), key=lambda x: x[1][1])
            del self.cache[oldest[0]]

image_cache = SimpleCache()

# ======================================== 
# FLASK SERVER
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
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ======================================== 
# BOT CONFIGURATION
# ========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

_session = None

async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=Config.REQUEST_TIMEOUT)
        )
    return _session

# ======================================== 
# STATISTIQUES
# ========================================
search_stats = defaultdict(int)
daily_downloads = defaultdict(int)

def log_search(query: str):
    search_stats[query.lower()] += 1

def log_download(query: str):
    daily_downloads[query.lower()] += 1

# ======================================== 
# COLLECTIONS
# ========================================
COLLECTIONS = {
    'anime': ['anime pfp', 'anime avatar', 'manga pfp', 'anime aesthetic'],
    'gamer': ['gaming pfp', 'gamer aesthetic', 'esports logo', 'gaming avatar'],
    'aesthetic': ['aesthetic pfp', 'soft aesthetic', 'dark aesthetic', 'grunge aesthetic'],
    'dark': ['dark pfp', 'edgy pfp', 'dark aesthetic', 'gothic pfp'],
    'cute': ['cute pfp', 'kawaii pfp', 'soft pfp', 'adorable avatar'],
    'nature': ['nature pfp', 'forest aesthetic', 'ocean pfp', 'mountain avatar'],
}

# ======================================== 
# OPTIMISATION REQUÊTES
# ========================================
def optimize_pfp_query(query: str, color: str = None) -> str:
    """Optimise la requête de recherche pour obtenir de meilleurs résultats"""
    query_lower = query.lower().strip()
    
    if color:
        query = f"{query} {color}"
    
    if any(keyword in query_lower for keyword in ['pfp', 'avatar', 'discord']):
        return query
    
    common_keywords = {
        'boy': 'discord pfp boy avatar',
        'girl': 'discord pfp girl avatar',
        'anime': 'anime discord pfp avatar',
        'aesthetic': 'aesthetic discord pfp',
        'dark': 'dark aesthetic discord pfp',
        'cute': 'cute discord pfp',
        'gamer': 'gamer discord pfp',
    }
    
    if query_lower in common_keywords:
        result = common_keywords[query_lower]
        if color:
            result = f"{result} {color}"
        return result
    
    return f"{query} discord pfp"

# ======================================== 
# VALIDATION URL
# ========================================
def is_valid_image_url(url: str) -> bool:
    """Valide une URL d'image"""
    try:
        if not url or len(url) > 2000:
            return False
        
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            return False
        
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        if not any(ext in url.lower() for ext in valid_extensions):
            return False
        
        blacklisted = ['localhost', '127.0.0.1', '0.0.0.0', '::1']
        if any(blocked in parsed.netloc.lower() for blocked in blacklisted):
            return False
        
        return True
    except:
        return False

# ======================================== 
# TRAITEMENT D'IMAGES
# ========================================
async def auto_crop_square(image_url: str) -> BytesIO:
    """Crop automatique en carré 512x512"""
    try:
        if not is_valid_image_url(image_url):
            logger.warning(f"URL invalide: {image_url}")
            return None
        
        await rate_limiter.acquire()
        
        session = await get_session()
        async with session.get(image_url, timeout=Config.REQUEST_TIMEOUT) as response:
            if response.status == 200:
                img_data = await response.read()
                
                if len(img_data) > Config.MAX_IMAGE_SIZE_MB * 1024 * 1024:
                    logger.warning("Image trop grande")
                    return None
                
                img = Image.open(BytesIO(img_data))
                
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                width, height = img.size
                size = min(width, height)
                
                left = (width - size) // 2
                top = (height - size) // 2
                right = left + size
                bottom = top + size
                
                img_cropped = img.crop((left, top, right, bottom))
                img_cropped = img_cropped.resize((512, 512), Image.Resampling.LANCZOS)
                
                output = BytesIO()
                img_cropped.save(output, format='PNG', optimize=True)
                output.seek(0)
                
                logger.info("✅ Image croppée 512x512")
                return output
    except asyncio.TimeoutError:
        logger.error("⏱️ Timeout crop")
    except Exception as e:
        logger.error(f"❌ Erreur crop: {e}")
    return None

async def create_profile_preview(image_url: str, username: str) -> BytesIO:
    """Crée une preview style Discord"""
    try:
        if not is_valid_image_url(image_url):
            return None
        
        await rate_limiter.acquire()
        
        session = await get_session()
        async with session.get(image_url, timeout=Config.REQUEST_TIMEOUT) as response:
            if response.status == 200:
                img_data = await response.read()
                avatar = Image.open(BytesIO(img_data))
                
                if avatar.mode != 'RGB':
                    avatar = avatar.convert('RGB')
                
                avatar = avatar.resize((128, 128), Image.Resampling.LANCZOS)
                
                mask = Image.new('L', (128, 128), 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, 128, 128), fill=255)
                
                preview = Image.new('RGB', (400, 200), color=(54, 57, 63))
                preview.paste(avatar, (20, 36), mask)
                
                draw_preview = ImageDraw.Draw(preview)
                draw_preview.text((160, 80), username, fill=(255, 255, 255))
                draw_preview.text((160, 110), "#0000", fill=(150, 150, 150))
                
                output = BytesIO()
                preview.save(output, format='PNG')
                output.seek(0)
                
                logger.info("✅ Preview créée")
                return output
    except Exception as e:
        logger.error(f"❌ Erreur preview: {e}")
    return None
    # ======================================== 
# RECHERCHE D'IMAGES
# ========================================

async def search_google_images(query: str, count: int = 10) -> list:
    """Recherche sur Google Images"""
    cache_key = f"google_{hashlib.md5(query.encode()).hexdigest()}"
    cached = image_cache.get(cache_key)
    if cached:
        logger.info(f"✅ Google cache hit")
        return cached
    
    try:
        await rate_limiter.acquire()
        
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={encoded_query}&tbm=isch&safe=active"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml',
            'Referer': 'https://www.google.com/'
        }
        
        async with session.get(url, headers=headers, timeout=Config.REQUEST_TIMEOUT) as response:
            if response.status == 200:
                html = await response.text()
                images = []
                
                pattern = r'"ou":"(https?://[^"]+)"'
                matches = re.findall(pattern, html)
                
                for match in matches:
                    if len(images) >= count:
                        break
                    if is_valid_image_url(match):
                        clean_url = match.split('&')[0]
                        images.append(clean_url)
                
                logger.info(f"✅ Google: {len(images)} images")
                image_cache.set(cache_key, images)
                return images[:count]
    except Exception as e:
        logger.error(f"❌ Google: {e}")
    return []

async def search_pinterest(query: str, count: int = 10) -> list:
    """Recherche sur Pinterest"""
    cache_key = f"pinterest_{hashlib.md5(query.encode()).hexdigest()}"
    cached = image_cache.get(cache_key)
    if cached:
        logger.info(f"✅ Pinterest cache hit")
        return cached
    
    try:
        await rate_limiter.acquire()
        
        session = await get_session()
        search_query = f"{query} discord avatar"
        encoded_query = urllib.parse.quote(search_query)
        url = f"https://www.pinterest.com/search/pins/?q={encoded_query}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml',
        }
        
        async with session.get(url, headers=headers, timeout=Config.REQUEST_TIMEOUT) as response:
            if response.status == 200:
                html = await response.text()
                images = []
                
                pattern = r'"url":"(https://i\.pinimg\.com/[^"]+)"'
                matches = re.findall(pattern, html)
                
                for match in matches:
                    if len(images) >= count:
                        break
                    clean_url = match.replace('\\/', '/').split('?')[0]
                    if '/736x/' in clean_url or '/originals/' in clean_url:
                        if is_valid_image_url(clean_url):
                            images.append(clean_url)
                
                logger.info(f"✅ Pinterest: {len(images)} images")
                image_cache.set(cache_key, images)
                return images[:count]
    except Exception as e:
        logger.error(f"❌ Pinterest: {e}")
    return []

async def search_images(query: str, count: int = 10) -> list:
    """Recherche d'images agrégée avec retry"""
    all_images = []
    
    tasks = [
        search_pinterest(query, count),
        search_google_images(query, count)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, list):
            all_images.extend(result)
    
    random.shuffle(all_images)
    final_images = all_images[:count]
    
    logger.info(f"🎯 Total: {len(final_images)} images pour '{query}'")
    return final_images

# ======================================== 
# VUES DISCORD
# ========================================

class ImageSelectionView(View):
    def __init__(self, images: list, query: str, author: discord.Member):
        super().__init__(timeout=300)
        self.images = images
        self.query = query
        self.author = author
        self.selected = set()
        
        for i in range(min(len(images), 10)):
            button = Button(label=str(i + 1), style=discord.ButtonStyle.secondary, custom_id=f"select_{i}", row=i // 5)
            button.callback = self.make_callback(i)
            self.add_item(button)
        
        select_all = Button(label="✅ Tout", style=discord.ButtonStyle.primary, row=2)
        select_all.callback = self.select_all_callback
        self.add_item(select_all)
        
        download = Button(label="📥 DL", style=discord.ButtonStyle.success, row=2)
        download.callback = self.download_callback
        self.add_item(download)
        
        preview = Button(label="👁️", style=discord.ButtonStyle.secondary, row=2)
        preview.callback = self.preview_callback
        self.add_item(preview)
        
        crop = Button(label="✂️", style=discord.ButtonStyle.secondary, row=2)
        crop.callback = self.crop_callback
        self.add_item(crop)
    
    def make_callback(self, index):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                await interaction.response.send_message("❌ Seul l'auteur peut faire ça !", ephemeral=True)
                return
            
            if index in self.selected:
                self.selected.remove(index)
            else:
                self.selected.add(index)
            
            for item in self.children:
                if isinstance(item, Button) and item.custom_id == f"select_{index}":
                    item.style = discord.ButtonStyle.success if index in self.selected else discord.ButtonStyle.secondary
            
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        return callback
    
    async def select_all_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Seul l'auteur !", ephemeral=True)
            return
        
        self.selected = set(range(len(self.images)))
        
        for item in self.children:
            if isinstance(item, Button) and item.custom_id and item.custom_id.startswith("select_"):
                item.style = discord.ButtonStyle.success
        
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
    
    async def download_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Seul l'auteur !", ephemeral=True)
            return
        
        if not self.selected:
            await interaction.response.send_message("❌ Sélectionne au moins 1 image !", ephemeral=True)
            return
        
        selected_images = [self.images[i] for i in sorted(self.selected)]
        log_download(self.query)
        
        await interaction.response.defer()
        
        for img_url in selected_images:
            embed = discord.Embed(color=discord.Color.blue())
            embed.set_image(url=img_url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            await asyncio.sleep(0.5)
        
        await interaction.followup.send(f"✅ {len(selected_images)} image(s) envoyée(s) !", ephemeral=True)
    
    async def preview_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Seul l'auteur !", ephemeral=True)
            return
        
        if not self.selected:
            await interaction.response.send_message("❌ Sélectionne 1 image !", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        first_selected = min(self.selected)
        img_url = self.images[first_selected]
        
        preview_img = await create_profile_preview(img_url, self.author.display_name)
        
        if preview_img:
            file = discord.File(preview_img, filename="preview.png")
            embed = discord.Embed(title="👁️ Preview Discord", color=discord.Color.blue())
            embed.set_image(url="attachment://preview.png")
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
        else:
            await interaction.followup.send("❌ Erreur preview", ephemeral=True)
    
    async def crop_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Seul l'auteur !", ephemeral=True)
            return
        
        if not self.selected:
            await interaction.response.send_message("❌ Sélectionne au moins 1 image !", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        cropped_count = 0
        for idx in sorted(self.selected):
            img_url = self.images[idx]
            cropped_img = await auto_crop_square(img_url)
            
            if cropped_img:
                file = discord.File(cropped_img, filename=f"cropped_{idx+1}.png")
                await interaction.followup.send(file=file, ephemeral=True)
                cropped_count += 1
                await asyncio.sleep(0.5)
        
        await interaction.followup.send(f"✅ {cropped_count} image(s) croppée(s) en 512x512 !", ephemeral=True)
    
    def create_embed(self):
        embed = discord.Embed(
            title=f"🎨 {len(self.images)} Avatars trouvés",
            description=f"**Recherche:** {self.query}\n**Sélectionné:** {len(self.selected)}/{len(self.images)}",
            color=discord.Color.blue()
        )
        
        if self.images:
            embed.set_image(url=self.images[0])
        
        embed.set_footer(text=f"Demandé par {self.author.display_name}")
        return embed

# ======================================== 
# COMMANDES BOT
# ========================================

@bot.command(name='pfp')
async def pfp_command(ctx, *, args: str = None):
    """Recherche des avatars Discord PFP"""
    if not args:
        await ctx.send("❌ **Usage:** `!pfp <recherche>` ou `!pfp boy --color blue`")
        return
    
    query = args
    color = None
    
    if '--color' in args:
        parts = args.split('--color')
        query = parts[0].strip()
        color = parts[1].strip() if len(parts) > 1 else None
    
    loading_msg = await ctx.send(f"🔍 Recherche en cours{f' (couleur: {color})' if color else ''}: **{query}**...")
    
    try:
        log_search(query)
        optimized_query = optimize_pfp_query(query, color)
        
        images = await search_images(optimized_query, count=Config.MAX_IMAGES)
        
        if not images:
            await loading_msg.edit(content=f"❌ Aucun résultat pour: **{query}**\nEssaie: `!pfp anime`, `!pfp aesthetic`, `!pfp gamer`")
            return
        
        view = ImageSelectionView(images, query, ctx.author)
        await loading_msg.edit(content=None, embed=view.create_embed(), view=view)
        
    except Exception as e:
        logger.error(f"❌ Erreur pfp: {e}")
        await ctx.send(f"❌ Erreur: {str(e)}")

@bot.command(name='match')
async def match_command(ctx, *, query: str = None):
    """Recherche des PFP matchés pour couples"""
    if not query:
        query = "matching pfp"
    
    loading_msg = await ctx.send(f"💑 Recherche de PFP matchés...")
    
    try:
        optimized_query = f"{query} matching pfp couple"
        images = await search_images(optimized_query, count=Config.MAX_IMAGES)
        
        if not images:
            await loading_msg.edit(content="❌ Aucun résultat")
            return
        
        view = ImageSelectionView(images, "matching pfp", ctx.author)
        await loading_msg.edit(content=None, embed=view.create_embed(), view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")

@bot.command(name='collection')
async def collection_command(ctx, theme: str = None):
    """Affiche ou recherche une collection thématique"""
    if not theme or theme not in COLLECTIONS:
        embed = discord.Embed(title="📦 Collections Disponibles", color=discord.Color.gold())
        
        for name in COLLECTIONS.keys():
            embed.add_field(name=f"!collection {name}", value="✨", inline=True)
        
        await ctx.send(embed=embed)
        return
    
    loading_msg = await ctx.send(f"📦 Chargement collection **{theme}**...")
    
    try:
        keywords = COLLECTIONS[theme].copy()
        random.shuffle(keywords)
        
        all_images = []
        for keyword in keywords[:3]:
            images = await search_images(keyword, count=4)
            all_images.extend(images)
            if len(all_images) >= Config.MAX_IMAGES:
                break
        
        all_images = all_images[:Config.MAX_IMAGES]
        
        if not all_images:
            await loading_msg.edit(content="❌ Erreur de chargement")
            return
        
        view = ImageSelectionView(all_images, f"collection {theme}", ctx.author)
        await loading_msg.edit(content=None, embed=view.create_embed(), view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")

@bot.command(name='trending')
async def trending_command(ctx):
    """Affiche les recherches populaires"""
    if not search_stats:
        await ctx.send("📊 Pas encore de statistiques !")
        return
    
    sorted_searches = sorted(search_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    
    embed = discord.Embed(title="🔥 Recherches Populaires", color=discord.Color.red())
    
    medals = ["🥇", "🥈", "🥉"]
    for i, (query, count) in enumerate(sorted_searches):
        medal = medals[i] if i < 3 else f"{i+1}."
        embed.add_field(name=f"{medal} {query}", value=f"{count}x recherches", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='help')
async def help_command(ctx):
    """Affiche l'aide du bot"""
    embed = discord.Embed(title="🎨 Bot PFP Discord - Aide", color=discord.Color.green())
    
    embed.add_field(name="!pfp <recherche>", value="Recherche d'avatars (ex: `!pfp anime`)", inline=False)
    embed.add_field(name="!pfp boy --color blue", value="Recherche avec filtre couleur", inline=False)
    embed.add_field(name="!match [thème]", value="PFP matchés pour couples", inline=False)
    embed.add_field(name="!collection <theme>", value="Collections: anime, gamer, aesthetic, dark, cute, nature", inline=False)
    embed.add_field(name="!trending", value="Top des recherches populaires", inline=False)
    
    embed.add_field(name="✨ Fonctionnalités", value="👁️ Preview • ✂️ Crop 512x512 • 🎨 Filtre couleur • 💑 Matching • 📦 Collections • 🔥 Tendances", inline=False)
    
    embed.set_footer(text="Développé avec ❤️")
    await ctx.send(embed=embed)

# ======================================== 
# ÉVÉNEMENTS
# ========================================

@bot.event
async def on_ready():
    logger.info(f"✅ Bot connecté: {bot.user.name} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="!help | !pfp"))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Commande inconnue. Utilise `!help` pour voir les commandes disponibles.")
    else:
        logger.error(f"❌ Erreur commande: {error}")

@bot.event
async def on_disconnect():
    global _session
    if _session and not _session.closed:
        await _session.close()
        logger.info("🔌 Session fermée")

# ======================================== 
# DÉMARRAGE
# ========================================

if __name__ == "__main__":
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN manquant dans les variables d'environnement !")
        sys.exit(1)
    
    logger.info("🚀 Démarrage du serveur Flask...")
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("🤖 Démarrage du bot Discord...")
    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("⏹️ Arrêt du bot...")
    except Exception as e:
        logger.error(f"❌ Erreur critique: {e}")
        sys.exit(1)
