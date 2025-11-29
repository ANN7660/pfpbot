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
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from collections import defaultdict
import json
from datetime import datetime

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
    app.run(host='0.0.0.0', port=port, debug=False)

# ======================================== 
# CONFIGURATION BOT
# ========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

_session = None

async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session

# ======================================== 
# STATISTIQUES & TRENDING
# ========================================
search_stats = defaultdict(int)  # Compteur de recherches
daily_downloads = defaultdict(int)  # Téléchargements du jour

def log_search(query: str):
    """Enregistre une recherche pour les tendances"""
    search_stats[query.lower()] += 1

def log_download(query: str):
    """Enregistre un téléchargement"""
    daily_downloads[query.lower()] += 1

# ======================================== 
# COLLECTIONS THÉMATIQUES
# ========================================
COLLECTIONS = {
    'anime': ['anime pfp', 'anime avatar', 'manga pfp', 'anime aesthetic', 'anime boy pfp', 'anime girl pfp'],
    'gamer': ['gaming pfp', 'gamer aesthetic', 'esports logo', 'gaming avatar', 'cyberpunk gamer'],
    'aesthetic': ['aesthetic pfp', 'soft aesthetic', 'dark aesthetic', 'grunge aesthetic', 'vaporwave'],
    'dark': ['dark pfp', 'edgy pfp', 'dark aesthetic', 'gothic pfp', 'shadow aesthetic'],
    'cute': ['cute pfp', 'kawaii pfp', 'soft pfp', 'adorable avatar', 'pastel cute'],
    'nature': ['nature pfp', 'forest aesthetic', 'ocean pfp', 'mountain avatar', 'sunset pfp'],
}

# ======================================== 
# OPTIMISATION DES REQUÊTES
# ========================================
def optimize_pfp_query(query: str, color: str = None) -> str:
    """Optimise la requête avec support couleur"""
    query_lower = query.lower().strip()
    
    # Ajouter la couleur si spécifiée
    if color:
        query = f"{query} {color}"
    
    if any(keyword in query_lower for keyword in ['pfp', 'avatar', 'discord', 'profile picture']):
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
# TRAITEMENT D'IMAGES - AUTO CROP
# ========================================
async def auto_crop_square(image_url: str) -> BytesIO:
    """Recadre automatiquement une image en carré centré"""
    try:
        session = await get_session()
        async with session.get(image_url, timeout=10) as response:
            if response.status == 200:
                img_data = await response.read()
                img = Image.open(BytesIO(img_data))
                
                # Convertir en RGB si nécessaire
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Obtenir les dimensions
                width, height = img.size
                
                # Calculer la taille du carré (minimum des deux dimensions)
                size = min(width, height)
                
                # Calculer les coordonnées pour centrer le crop
                left = (width - size) // 2
                top = (height - size) // 2
                right = left + size
                bottom = top + size
                
                # Crop en carré
                img_cropped = img.crop((left, top, right, bottom))
                
                # Redimensionner à 512x512 (taille optimale Discord)
                img_cropped = img_cropped.resize((512, 512), Image.Resampling.LANCZOS)
                
                # Sauvegarder dans BytesIO
                output = BytesIO()
                img_cropped.save(output, format='PNG', optimize=True)
                output.seek(0)
                
                logger.info("✅ Image croppée en carré 512x512")
                return output
    except Exception as e:
        logger.error(f"❌ Erreur crop: {e}")
    return None

# ======================================== 
# PREVIEW PROFIL DISCORD
# ========================================
async def create_profile_preview(image_url: str, username: str) -> BytesIO:
    """Crée une preview du profil Discord avec l'avatar"""
    try:
        session = await get_session()
        async with session.get(image_url, timeout=10) as response:
            if response.status == 200:
                img_data = await response.read()
                avatar = Image.open(BytesIO(img_data))
                
                # Convertir en RGB
                if avatar.mode != 'RGB':
                    avatar = avatar.convert('RGB')
                
                # Redimensionner l'avatar en 128x128
                avatar = avatar.resize((128, 128), Image.Resampling.LANCZOS)
                
                # Créer un masque circulaire
                mask = Image.new('L', (128, 128), 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, 128, 128), fill=255)
                
                # Créer l'image de fond (style Discord)
                preview = Image.new('RGB', (400, 200), color=(54, 57, 63))
                
                # Ajouter l'avatar circulaire
                preview.paste(avatar, (20, 36), mask)
                
                # Ajouter le nom d'utilisateur (texte simple sans police)
                draw_preview = ImageDraw.Draw(preview)
                draw_preview.text((160, 80), username, fill=(255, 255, 255))
                draw_preview.text((160, 110), "#0000", fill=(150, 150, 150))
                
                # Sauvegarder
                output = BytesIO()
                preview.save(output, format='PNG')
                output.seek(0)
                
                logger.info("✅ Preview profil créée")
                return output
    except Exception as e:
        logger.error(f"❌ Erreur preview: {e}")
    return None

# ======================================== 
# RECHERCHE D'IMAGES
# ========================================
async def search_google_images(query: str, count: int = 10) -> list:
    try:
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={encoded_query}&tbm=isch&safe=active"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Referer': 'https://www.google.com/'
        }
        
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                html = await response.text()
                images = []
                
                pattern = r'"ou":"(https?://[^"]+)"'
                matches = re.findall(pattern, html)
                
                for match in matches:
                    if len(images) >= count:
                        break
                    if any(ext in match.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                        clean_url = match.split('&')[0]
                        images.append(clean_url)
                
                logger.info(f"✅ Google Images: {len(images)} images trouvées")
                return images[:count]
    except Exception as e:
        logger.error(f"❌ Google Images: {e}")
    return []

async def search_pexels(query: str, count: int = 10) -> list:
    api_key = os.getenv('PEXELS_API_KEY')
    if not api_key:
        return []
    
    try:
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.pexels.com/v1/search?query={encoded_query}&per_page={count}&size=medium"
        
        headers = {'Authorization': api_key}
        
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                images = [photo['src']['large'] for photo in data.get('photos', [])]
                logger.info(f"✅ Pexels: {len(images)} images")
                return images
    except Exception as e:
        logger.error(f"❌ Pexels: {e}")
    return []

async def search_pixabay(query: str, count: int = 10) -> list:
    api_key = os.getenv('PIXABAY_API_KEY')
    if not api_key:
        return []
    
    try:
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        url = f"https://pixabay.com/api/?key={api_key}&q={encoded_query}&image_type=photo&per_page={count}"
        
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                images = [hit['largeImageURL'] for hit in data.get('hits', [])]
                logger.info(f"✅ Pixabay: {len(images)} images")
                return images
    except Exception as e:
        logger.error(f"❌ Pixabay: {e}")
    return []

async def search_pinterest(query: str, count: int = 10) -> list:
    try:
        session = await get_session()
        search_query = f"{query} discord avatar"
        encoded_query = urllib.parse.quote(search_query)
        url = f"https://www.pinterest.com/search/pins/?q={encoded_query}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        
        async with session.get(url, headers=headers, timeout=10) as response:
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
                        images.append(clean_url)
                
                logger.info(f"✅ Pinterest: {len(images)} images")
                return images[:count]
    except Exception as e:
        logger.error(f"❌ Pinterest: {e}")
    return []

async def search_images(query: str, count: int = 10) -> list:
    all_images = []
    
    tasks = [
        search_pinterest(query, count),
        search_pexels(query, count),
        search_pixabay(query, count),
        search_google_images(query, count)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, list):
            all_images.extend(result)
    
    random.shuffle(all_images)
    final_images = all_images[:count]
    
    logger.info(f"🎯 Total: {len(final_images)} images trouvées")
    return final_images

# ======================================== 
# VUE - PREVIEW PROFIL
# ========================================
class PreviewView(View):
    def __init__(self, image_url: str, username: str, author: discord.Member):
        super().__init__(timeout=60)
        self.image_url = image_url
        self.username = username
        self.author = author
    
    @discord.ui.button(label="✅ Télécharger cette PFP", style=discord.ButtonStyle.success)
    async def download_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce menu !", ephemeral=True)
            return
        
        embed = discord.Embed(color=discord.Color.blue())
        embed.set_image(url=self.image_url)
        await interaction.response.send_message(embed=embed)

# FIN PARTIE 1/2 - VOIR PARTIE 2 POUR LE RESTE
# PARTIE 2/2 - CONTINUATION DU BOT

# ======================================== 
# VUE INTERACTIVE - SÉLECTION D'IMAGES
# ========================================
class ImageSelectionView(View):
    def __init__(self, images: list, query: str, author: discord.Member):
        super().__init__(timeout=300)
        self.images = images
        self.query = query
        self.author = author
        self.selected = set()
        
        # Boutons numérotés (1-10)
        for i in range(min(len(images), 10)):
            button = Button(
                label=str(i + 1),
                style=discord.ButtonStyle.secondary,
                custom_id=f"select_{i}",
                row=i // 5
            )
            button.callback = self.make_callback(i)
            self.add_item(button)
        
        # Boutons d'action
        select_all_btn = Button(label="✅ Tout", style=discord.ButtonStyle.primary, custom_id="select_all", row=2)
        select_all_btn.callback = self.select_all_callback
        self.add_item(select_all_btn)
        
        download_btn = Button(label="📥 Télécharger", style=discord.ButtonStyle.success, custom_id="download", row=2)
        download_btn.callback = self.download_callback
        self.add_item(download_btn)
        
        preview_btn = Button(label="👁️ Preview", style=discord.ButtonStyle.secondary, custom_id="preview", row=2)
        preview_btn.callback = self.preview_callback
        self.add_item(preview_btn)
        
        crop_btn = Button(label="✂️ Crop", style=discord.ButtonStyle.secondary, custom_id="crop", row=2)
        crop_btn.callback = self.crop_callback
        self.add_item(crop_btn)
    
    def make_callback(self, index):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce menu !", ephemeral=True)
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
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce menu !", ephemeral=True)
            return
        
        self.selected = set(range(len(self.images)))
        
        for item in self.children:
            if isinstance(item, Button) and item.custom_id.startswith("select_"):
                item.style = discord.ButtonStyle.success
        
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
    
    async def download_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce menu !", ephemeral=True)
            return
        
        if not self.selected:
            await interaction.response.send_message("❌ Aucune image sélectionnée !", ephemeral=True)
            return
        
        selected_images = [self.images[i] for i in sorted(self.selected)]
        log_download(self.query)
        
        channel_view = ChannelSelectionView(selected_images, self.author, interaction.message)
        await interaction.response.edit_message(embed=channel_view.create_embed(), view=channel_view)
    
    async def preview_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce menu !", ephemeral=True)
            return
        
        if not self.selected:
            await interaction.response.send_message("❌ Sélectionne au moins 1 image !", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Prendre la première image sélectionnée
        first_selected = min(self.selected)
        img_url = self.images[first_selected]
        
        # Créer la preview
        preview_img = await create_profile_preview(img_url, self.author.display_name)
        
        if preview_img:
            file = discord.File(preview_img, filename="preview.png")
            embed = discord.Embed(title="👁️ Preview Profil Discord", color=discord.Color.blue())
            embed.set_image(url="attachment://preview.png")
            
            preview_view = PreviewView(img_url, self.author.display_name, self.author)
            await interaction.followup.send(embed=embed, file=file, view=preview_view, ephemeral=True)
        else:
            await interaction.followup.send("❌ Erreur lors de la création de la preview", ephemeral=True)
    
    async def crop_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce menu !", ephemeral=True)
            return
        
        if not self.selected:
            await interaction.response.send_message("❌ Sélectionne au moins 1 image !", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Crop toutes les images sélectionnées
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
            description=f"**Recherche:** `{self.query}`\n**Sélectionné:** {len(self.selected)}/{len(self.images)}\n\n"
                       "🔢 Clique sur les numéros\n"
                       "👁️ Preview = Voir sur profil Discord\n"
                       "✂️ Crop = Recadrer en carré 512x512",
            color=discord.Color.blue()
        )
        
        if self.images:
            embed.set_image(url=self.images[0])
        
        embed.set_footer(text=f"Demandé par {self.author.display_name}")
        return embed

# ======================================== 
# VUE - SÉLECTION DE SALON
# ========================================
class ChannelSelectionView(View):
    def __init__(self, images: list, author: discord.Member, original_message: discord.Message):
        super().__init__(timeout=180)
        self.images = images
        self.author = author
        self.original_message = original_message
        
        channel_select = Select(placeholder="📂 Choisis un salon...", min_values=1, max_values=1, custom_id="channel_select")
        
        guild = author.guild
        text_channels = [ch for ch in guild.text_channels if ch.permissions_for(author).send_messages]
        
        for channel in text_channels[:25]:
            channel_select.add_option(label=f"#{channel.name}", value=str(channel.id), description=f"Envoyer dans #{channel.name}")
        
        channel_select.callback = self.channel_callback
        self.add_item(channel_select)
        
        here_btn = Button(label="📍 Ici", style=discord.ButtonStyle.primary, custom_id="here")
        here_btn.callback = self.here_callback
        self.add_item(here_btn)
        
        dm_btn = Button(label="💬 MP", style=discord.ButtonStyle.secondary, custom_id="dm")
        dm_btn.callback = self.dm_callback
        self.add_item(dm_btn)
    
    async def channel_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce menu !", ephemeral=True)
            return
        
        channel_id = int(interaction.data['values'][0])
        channel = interaction.guild.get_channel(channel_id)
        
        if not channel:
            await interaction.response.send_message("❌ Salon introuvable !", ephemeral=True)
            return
        
        await self.send_images(interaction, channel)
    
    async def here_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce menu !", ephemeral=True)
            return
        
        await self.send_images(interaction, interaction.channel)
    
    async def dm_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce menu !", ephemeral=True)
            return
        
        try:
            dm_channel = await self.author.create_dm()
            await self.send_images(interaction, dm_channel)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Je ne peux pas t'envoyer de MP !", ephemeral=True)
    
    async def send_images(self, interaction: discord.Interaction, target_channel):
        await interaction.response.defer()
        
        try:
            for img_url in self.images:
                embed = discord.Embed(color=discord.Color.blue())
                embed.set_image(url=img_url)
                await target_channel.send(embed=embed)
                await asyncio.sleep(0.5)
            
            for item in self.children:
                item.disabled = True
            
            await self.original_message.edit(view=self)
            
            destination = "en MP" if isinstance(target_channel, discord.DMChannel) else f"dans #{target_channel.name}"
            await interaction.followup.send(f"✅ {len(self.images)} image(s) envoyée(s) {destination} !", ephemeral=True)
            
        except Exception as e:
            logger.error(f"❌ Erreur envoi images: {e}")
            await interaction.followup.send(f"❌ Erreur: {str(e)}", ephemeral=True)
    
    def create_embed(self):
        embed = discord.Embed(
            title="📂 Où envoyer les images ?",
            description=f"**{len(self.images)} image(s) sélectionnée(s)**\n\n"
                       "🔹 Menu déroulant = Choisis un salon\n"
                       "🔹 📍 Ici = Ce salon\n"
                       "🔹 💬 MP = Message privé",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Demandé par {self.author.display_name}")
        return embed

# ======================================== 
# COMMANDES
# ========================================
@bot.command(name='pfp')
async def pfp_command(ctx, *, args: str = None):
    """Commande principale avec support --color"""
    if not args:
        await ctx.send("❌ Usage: `!pfp <recherche>` ou `!pfp <recherche> --color blue`")
        return
    
    # Parser les arguments
    query = args
    color = None
    
    if '--color' in args:
        parts = args.split('--color')
        query = parts[0].strip()
        color = parts[1].strip() if len(parts) > 1 else None
    
    loading_msg = await ctx.send(f"🔍 Recherche de 10 avatars{f' ({color})' if color else ''} pour: **{query}**...")
    
    try:
        log_search(query)
        optimized_query = optimize_pfp_query(query, color)
        logger.info(f"🔍 '{query}' → '{optimized_query}'")
        
        images = await search_images(optimized_query, count=10)
        
        if not images:
            await loading_msg.edit(content=f"❌ Aucun avatar trouvé pour: **{query}**")
            return
        
        view = ImageSelectionView(images, query, ctx.author)
        await loading_msg.edit(content=None, embed=view.create_embed(), view=view)
        
    except Exception as e:
        logger.error(f"❌ Erreur: {e}")
        await ctx.send(f"❌ Erreur: {str(e)}")

@bot.command(name='match')
async def match_command(ctx, *, query: str = None):
    """Trouve des PFP matchées (couples/amis)"""
    if not query:
        query = "matching pfp"
    
    loading_msg = await ctx.send(f"💑 Recherche de PFP matchées...")
    
    try:
        optimized_query = f"{query} matching pfp couple avatar"
        images = await search_images(optimized_query, count=10)
        
        if not images:
            await loading_msg.edit(content="❌ Aucune PFP matchée trouvée")
            return
        
        view = ImageSelectionView(images, "matching pfp", ctx.author)
        await loading_msg.edit(content=None, embed=view.create_embed(), view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")

@bot.command(name='collection')
async def collection_command(ctx, theme: str = None):
    """Accède aux collections thématiques"""
    if not theme or theme not in COLLECTIONS:
        embed = discord.Embed(title="📦 Collections Thématiques", color=discord.Color.gold())
        embed.description = "**Collections disponibles:**\n\n"
        
        for name, keywords in COLLECTIONS.items():
            embed.add_field(name=f"!collection {name}", value=f"{len(keywords)} variantes", inline=True)
        
        await ctx.send(embed=embed)
        return
    
    loading_msg = await ctx.send(f"📦 Chargement de la collection **{theme}**...")
    
    try:
        # Mélanger les mots-clés de la collection
        keywords = COLLECTIONS[theme].copy()
        random.shuffle(keywords)
        
        all_images = []
        for keyword in keywords[:3]:  # Prendre 3 mots-clés différents
            images = await search_images(keyword, count=4)
            all_images.extend(images)
            if len(all_images) >= 10:
                break
        
        all_images = all_images[:10]
        
        if not all_images:
            await loading_msg.edit(content=f"❌ Erreur de chargement")
            return
        
        view = ImageSelectionView(all_images, f"collection {theme}", ctx.author)
        await loading_msg.edit(content=None, embed=view.create_embed(), view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Erreur: {str(e)}")

@bot.command(name='trending')
async def trending_command(ctx):
    """Affiche les recherches tendances"""
    if not search_stats:
        await ctx.send("📊 Aucune statistique pour le moment !")
        return
    
    # Trier par popularité
    sorted_searches = sorted(search_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    
    embed = discord.Embed(title="🔥 Top 10 Tendances", color=discord.Color.red())
    
    medals = ["🥇", "🥈", "🥉"]
    for i, (query, count) in enumerate(sorted_searches):
        medal = medals[i] if i < 3 else f"{i+1}."
        embed.add_field(
            name=f"{medal} {query}",
            value=f"{count} recherches",
            inline=False
        )
    
    embed.set_footer(text="Utilise !pfp <tendance> pour essayer")
    await ctx.send(embed=embed)

@bot.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(title="🎨 Bot Avatar Discord - Aide Complète", color=discord.Color.green())
    
    embed.add_field(
        name="!pfp <recherche>",
        value="Menu avec 10 avatars + sélection multiple\n`!pfp anime`, `!pfp cat`",
        inline=False
    )
    
    embed.add_field(
        name="!pfp <recherche> --color <couleur>",
        value="Recherche par couleur\n`!pfp boy --color blue`",
        inline=False
    )
    
    embed.add_field(
        name="!match [recherche]",
        value="PFP matchées pour couples/amis\n`!match anime`",
        inline=False
    )
    
    embed.add_field(
        name="!collection <theme>",
        value="Collections: anime, gamer, aesthetic, dark, cute, nature\n`!collection anime`",
        inline=False
    )
    
    embed.add_field(
        name="!trending",
        value="Top 10 des recherches populaires",
        inline=False
    )
    
    embed.add_field(
        name="✨ Fonctionnalités",
        value="👁️ Preview profil Discord\n✂️ Auto-crop 512x512\n🎨 Recherche par couleur\n💑 PFP matchées\n📦 Collections\n🔥 Tendances",
        inline=False
    )
    
    await ctx.send(embed=embed)

# ======================================== 
# ÉVÉNEMENTS BOT
# ========================================
@bot.event
async def on_ready():
    logger.info(f"✅ Bot connecté: {bot.user.name}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="!help | 6 nouvelles fonctionnalités"))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Commande inconnue. Utilise `!help`")
    else:
        logger.error(f"❌ Erreur: {error}")

@bot.event
async def on_disconnect():
    global _session
    if _session and not _session.closed:
        await _session.close()

# ======================================== 
# DÉMARRAGE
# ========================================
if __name__ == "__main__":
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN manquant !")
        sys.exit(1)
    
    logger.info("🚀 Démarrage Flask...")
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("🤖 Démarrage bot Discord avec 6 nouvelles fonctionnalités...")
    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("⏹️ Arrêt...")
    except Exception as e:
        logger.error(f"❌ Erreur: {e}")
        sys.exit(1)
