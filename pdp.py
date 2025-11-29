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
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
http_session = None

# ========================================
# FLASK
# ========================================
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot Web Scraper actif!"

@app.route('/health')
def health():
    return {"status": "alive"}

def run_flask():
    try:
        app.run(host='0.0.0.0', port=8080, use_reloader=False)
    except Exception as e:
        logger.error(f"❌ Flask: {e}")

# ========================================
# SESSION HTTP
# ========================================
async def get_session():
    global http_session
    if http_session is None or http_session.closed:
        timeout = aiohttp.ClientTimeout(total=30)
        http_session = aiohttp.ClientSession(timeout=timeout)
    return http_session

# ========================================
# MOTEUR DE RECHERCHE - GOOGLE IMAGES
# ========================================
async def search_google_images(query: str, count: int = 10) -> list:
    """Recherche d'images via Google Images"""
    try:
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        
        # URL de recherche Google Images
        url = f"https://www.google.com/search?q={encoded_query}&tbm=isch&safe=active"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Extraire les URLs d'images
                images = []
                img_tags = soup.find_all('img')
                
                for img in img_tags:
                    img_url = img.get('src') or img.get('data-src')
                    if img_url and img_url.startswith('http') and len(images) < count:
                        images.append(img_url)
                
                logger.info(f"✅ Google: {len(images)} images trouvées pour '{query}'")
                return images[:count]
    except Exception as e:
        logger.error(f"❌ Google Images: {e}")
    return []

# ========================================
# MOTEUR DE RECHERCHE - UNSPLASH API
# ========================================
async def search_unsplash(query: str, count: int = 10) -> list:
    """Recherche d'images via Unsplash API (gratuit)"""
    try:
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        
        # API Unsplash (pas besoin de clé pour le public)
        url = f"https://source.unsplash.com/1600x900/?{encoded_query}"
        
        images = []
        for i in range(count):
            # Chaque requête donne une image random
            img_url = f"https://source.unsplash.com/1600x900/?{encoded_query},{i}"
            images.append(img_url)
        
        logger.info(f"✅ Unsplash: {len(images)} images pour '{query}'")
        return images
    except Exception as e:
        logger.error(f"❌ Unsplash: {e}")
    return []

# ========================================
# MOTEUR DE RECHERCHE - PIXABAY API
# ========================================
async def search_pixabay(query: str, count: int = 10) -> list:
    """Recherche via Pixabay (nécessite API key)"""
    PIXABAY_KEY = os.getenv('PIXABAY_API_KEY', '')
    
    if not PIXABAY_KEY:
        return []
    
    try:
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        
        url = f"https://pixabay.com/api/?key={PIXABAY_KEY}&q={encoded_query}&image_type=photo&per_page={count}"
        
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                images = [hit['largeImageURL'] for hit in data.get('hits', [])]
                logger.info(f"✅ Pixabay: {len(images)} images pour '{query}'")
                return images[:count]
    except Exception as e:
        logger.error(f"❌ Pixabay: {e}")
    return []

# ========================================
# MOTEUR DE RECHERCHE - PEXELS API
# ========================================
async def search_pexels(query: str, count: int = 10) -> list:
    """Recherche via Pexels (nécessite API key)"""
    PEXELS_KEY = os.getenv('PEXELS_API_KEY', '')
    
    if not PEXELS_KEY:
        return []
    
    try:
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        
        url = f"https://api.pexels.com/v1/search?query={encoded_query}&per_page={count}"
        headers = {'Authorization': PEXELS_KEY}
        
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                images = [photo['src']['large'] for photo in data.get('photos', [])]
                logger.info(f"✅ Pexels: {len(images)} images pour '{query}'")
                return images[:count]
    except Exception as e:
        logger.error(f"❌ Pexels: {e}")
    return []

# ========================================
# MOTEUR DE RECHERCHE - GIPHY (GIFs)
# ========================================
async def search_giphy(query: str, count: int = 10) -> list:
    """Recherche de GIFs via Giphy"""
    try:
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        
        # API publique Giphy
        url = f"https://api.giphy.com/v1/gifs/search?api_key=dc6zaTOxFJmzC&q={encoded_query}&limit={count}"
        
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                images = [gif['images']['original']['url'] for gif in data.get('data', [])]
                logger.info(f"✅ Giphy: {len(images)} GIFs pour '{query}'")
                return images[:count]
    except Exception as e:
        logger.error(f"❌ Giphy: {e}")
    return []

# ========================================
# AGRÉGATEUR - RECHERCHE MULTI-SOURCES
# ========================================
async def search_all_sources(query: str, count: int = 10) -> dict:
    """Recherche sur TOUTES les sources disponibles"""
    
    results = {
        'google': [],
        'unsplash': [],
        'pixabay': [],
        'pexels': [],
        'giphy': [],
        'total': 0
    }
    
    # Lancer toutes les recherches en parallèle
    tasks = [
        search_google_images(query, count),
        search_unsplash(query, count),
        search_pixabay(query, count),
        search_pexels(query, count),
        search_giphy(query, count)
    ]
    
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    results['google'] = responses[0] if not isinstance(responses[0], Exception) else []
    results['unsplash'] = responses[1] if not isinstance(responses[1], Exception) else []
    results['pixabay'] = responses[2] if not isinstance(responses[2], Exception) else []
    results['pexels'] = responses[3] if not isinstance(responses[3], Exception) else []
    results['giphy'] = responses[4] if not isinstance(responses[4], Exception) else []
    
    # Calculer total
    results['total'] = sum([
        len(results['google']),
        len(results['unsplash']),
        len(results['pixabay']),
        len(results['pexels']),
        len(results['giphy'])
    ])
    
    return results

# ========================================
# VUES DISCORD
# ========================================
class SourceSelectView(discord.ui.View):
    def __init__(self, results: dict, query: str, user, guild):
        super().__init__(timeout=300)
        self.results = results
        self.query = query
        self.user = user
        self.guild = guild
        
        # Créer les boutons pour chaque source
        if results['google']:
            btn = discord.ui.Button(
                label=f"🔍 Google ({len(results['google'])})",
                style=discord.ButtonStyle.primary
            )
            btn.callback = lambda i: self.show_source(i, 'google')
            self.add_item(btn)
        
        if results['unsplash']:
            btn = discord.ui.Button(
                label=f"📸 Unsplash ({len(results['unsplash'])})",
                style=discord.ButtonStyle.primary
            )
            btn.callback = lambda i: self.show_source(i, 'unsplash')
            self.add_item(btn)
        
        if results['pixabay']:
            btn = discord.ui.Button(
                label=f"🖼️ Pixabay ({len(results['pixabay'])})",
                style=discord.ButtonStyle.primary
            )
            btn.callback = lambda i: self.show_source(i, 'pixabay')
            self.add_item(btn)
        
        if results['pexels']:
            btn = discord.ui.Button(
                label=f"📷 Pexels ({len(results['pexels'])})",
                style=discord.ButtonStyle.primary
            )
            btn.callback = lambda i: self.show_source(i, 'pexels')
            self.add_item(btn)
        
        if results['giphy']:
            btn = discord.ui.Button(
                label=f"🎬 Giphy ({len(results['giphy'])})",
                style=discord.ButtonStyle.success
            )
            btn.callback = lambda i: self.show_source(i, 'giphy')
            self.add_item(btn)
        
        # Bouton "Tout afficher"
        all_btn = discord.ui.Button(
            label=f"🌐 Tout ({results['total']})",
            style=discord.ButtonStyle.danger,
            row=1
        )
        all_btn.callback = self.show_all
        self.add_item(all_btn)
    
    async def show_source(self, interaction: discord.Interaction, source: str):
        images = self.results[source]
        embeds = []
        
        for i, img_url in enumerate(images[:10], 1):
            embed = discord.Embed(
                title=f"#{i} - {source.title()}",
                color=discord.Color.blue()
            )
            embed.set_image(url=img_url)
            embeds.append(embed)
        
        view = ImageSelectionView(images, self.query, source, self.user, self.guild)
        
        await interaction.response.edit_message(
            content=f"🔍 **{len(images)} images de {source.title()}** pour '{self.query}'",
            embeds=embeds[:10],
            view=view
        )
    
    async def show_all(self, interaction: discord.Interaction):
        all_images = []
        for source_images in self.results.values():
            if isinstance(source_images, list):
                all_images.extend(source_images)
        
        embeds = []
        for i, img_url in enumerate(all_images[:10], 1):
            embed = discord.Embed(
                title=f"#{i}",
                color=discord.Color.random()
            )
            embed.set_image(url=img_url)
            embeds.append(embed)
        
        view = ImageSelectionView(all_images, self.query, "Toutes sources", self.user, self.guild)
        
        await interaction.response.edit_message(
            content=f"🌐 **{len(all_images)} images totales** pour '{self.query}'",
            embeds=embeds[:10],
            view=view
        )

class ChannelSelectView(discord.ui.View):
    def __init__(self, images: list, query: str, user, guild):
        super().__init__(timeout=300)
        self.images = images
        self.query = query
        self.user = user
        self.guild = guild
        
        options = []
        for channel in guild.text_channels[:25]:
            options.append(
                discord.SelectOption(
                    label=f"#{channel.name}",
                    value=str(channel.id),
                    description=f"Envoyer dans {channel.name}"
                )
            )
        
        if options:
            select = discord.ui.Select(
                placeholder="📌 Choisis le salon...",
                options=options
            )
            select.callback = self.channel_selected
            self.add_item(select)
    
    async def channel_selected(self, interaction: discord.Interaction):
        channel_id = int(interaction.data['values'][0])
        channel = self.guild.get_channel(channel_id)
        
        if not channel:
            await interaction.response.send_message("❌ Salon introuvable!", ephemeral=True)
            return
        
        await interaction.response.edit_message(
            content=f"📤 Envoi de **{len(self.images)} images**...",
            view=None
        )
        
        # Envoyer JUSTE les URLs, sans texte
        message_content = "\n".join(self.images)
        
        # Envoyer en 1 seul message (limite 2000 caractères)
        if len(message_content) < 2000:
            await channel.send(message_content)
        else:
            # Si trop long, envoyer par paquets de 5 images
            for i in range(0, len(self.images), 5):
                batch = self.images[i:i+5]
                await channel.send("\n".join(batch))
        
        await interaction.followup.send(
            f"✅ {len(self.images)} images envoyées dans {channel.mention}!",
            ephemeral=True
        )

class ImageSelectionView(discord.ui.View):
    def __init__(self, images: list, query: str, source: str, user, guild):
        super().__init__(timeout=600)
        self.images = images
        self.query = query
        self.source = source
        self.user = user
        self.guild = guild
        self.selected_images = []
        
        for i in range(min(len(images), 10)):
            button = discord.ui.Button(
                label=f"#{i+1}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"img_{i}",
                row=i // 5
            )
            button.callback = self.create_callback(i)
            self.add_item(button)
        
        all_btn = discord.ui.Button(
            label="📌 Tout",
            style=discord.ButtonStyle.primary,
            custom_id="select_all",
            row=2
        )
        all_btn.callback = self.select_all
        self.add_item(all_btn)
        
        send_btn = discord.ui.Button(
            label="✅ Envoyer",
            style=discord.ButtonStyle.success,
            custom_id="send",
            row=2
        )
        send_btn.callback = self.send_images
        self.add_item(send_btn)
    
    def create_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            button = None
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.custom_id == f"img_{index}":
                    button = item
                    break
            
            if button:
                if index in self.selected_images:
                    self.selected_images.remove(index)
                    button.style = discord.ButtonStyle.secondary
                    button.label = f"#{index + 1}"
                else:
                    self.selected_images.append(index)
                    button.style = discord.ButtonStyle.success
                    button.label = f"✅ #{index + 1}"
                
                await interaction.response.edit_message(view=self)
        return callback
    
    async def select_all(self, interaction: discord.Interaction):
        self.selected_images = list(range(len(self.images)))
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id and item.custom_id.startswith("img_"):
                item.style = discord.ButtonStyle.success
                item.label = "✅ " + item.label.replace("✅ ", "")
        await interaction.response.edit_message(
            content=f"✅ **{len(self.selected_images)} images** sélectionnées!",
            view=self
        )
    
    async def send_images(self, interaction: discord.Interaction):
        if not self.selected_images:
            await interaction.response.send_message(
                "❌ Sélectionne au moins une image!",
                ephemeral=True
            )
            return
        
        selected = [self.images[i] for i in self.selected_images]
        view = ChannelSelectView(selected, self.query, self.user, self.guild)
        
        await interaction.response.edit_message(
            content=f"📌 **{len(selected)} images** sélectionnées!\n\n"
                   f"👇 Choisis le salon:",
            embeds=[],
            view=view
        )

# ========================================
# COMMANDES
# ========================================
@bot.event
async def on_ready():
    logger.info(f'✅ {bot.user} connecté!')
    logger.info(f'📊 {len(bot.guilds)} serveurs')
    logger.info(f'🔍 Moteur de recherche WEB actif!')
    logger.info('━' * 50)

@bot.command(name='search')
async def search_web(ctx, *, query: str):
    """🔍 Recherche WEB d'images"""
    msg = await ctx.send(f"🔍 Recherche sur le web: **{query}**...")
    
    # Rechercher sur toutes les sources
    results = await search_all_sources(query, 10)
    
    if results['total'] == 0:
        await msg.edit(content=f"❌ Aucune image trouvée pour **{query}**")
        return
    
    # Créer l'embed récapitulatif
    embed = discord.Embed(
        title=f"🔍 Résultats pour: {query}",
        description=f"**{results['total']} images** trouvées!",
        color=discord.Color.green()
    )
    
    if results['google']:
        embed.add_field(name="🔍 Google", value=f"{len(results['google'])} images", inline=True)
    if results['unsplash']:
        embed.add_field(name="📸 Unsplash", value=f"{len(results['unsplash'])} images", inline=True)
    if results['pixabay']:
        embed.add_field(name="🖼️ Pixabay", value=f"{len(results['pixabay'])} images", inline=True)
    if results['pexels']:
        embed.add_field(name="📷 Pexels", value=f"{len(results['pexels'])} images", inline=True)
    if results['giphy']:
        embed.add_field(name="🎬 Giphy", value=f"{len(results['giphy'])} GIFs", inline=True)
    
    embed.set_footer(text="Clique sur une source pour voir les images!")
    
    view = SourceSelectView(results, query, ctx.author, ctx.guild)
    await msg.edit(content=None, embed=embed, view=view)

@bot.command(name='google')
async def google_search(ctx, *, query: str):
    """🔍 Recherche Google Images uniquement"""
    msg = await ctx.send(f"🔍 Google: **{query}**...")
    
    images = await search_google_images(query, 10)
    
    if not images:
        await msg.edit(content=f"❌ Aucune image trouvée sur Google pour **{query}**")
        return
    
    embeds = []
    for i, img_url in enumerate(images[:10], 1):
        embed = discord.Embed(title=f"#{i} - Google", color=discord.Color.blue())
        embed.set_image(url=img_url)
        embeds.append(embed)
    
    view = ImageSelectionView(images, query, "Google", ctx.author, ctx.guild)
    await msg.edit(
        content=f"🔍 **{len(images)} images Google** pour '{query}'",
        embeds=embeds[:10],
        view=view
    )

@bot.command(name='unsplash')
async def unsplash_search(ctx, *, query: str):
    """📸 Recherche Unsplash uniquement"""
    msg = await ctx.send(f"📸 Unsplash: **{query}**...")
    
    images = await search_unsplash(query, 10)
    
    if not images:
        await msg.edit(content=f"❌ Aucune image trouvée sur Unsplash pour **{query}**")
        return
    
    embeds = []
    for i, img_url in enumerate(images[:10], 1):
        embed = discord.Embed(title=f"#{i} - Unsplash", color=discord.Color.green())
        embed.set_image(url=img_url)
        embeds.append(embed)
    
    view = ImageSelectionView(images, query, "Unsplash", ctx.author, ctx.guild)
    await msg.edit(
        content=f"📸 **{len(images)} images Unsplash** pour '{query}'",
        embeds=embeds[:10],
        view=view
    )

@bot.command(name='gif')
async def gif_search(ctx, *, query: str):
    """🎬 Recherche GIFs Giphy"""
    msg = await ctx.send(f"🎬 Giphy: **{query}**...")
    
    images = await search_giphy(query, 10)
    
    if not images:
        await msg.edit(content=f"❌ Aucun GIF trouvé sur Giphy pour **{query}**")
        return
    
    embeds = []
    for i, img_url in enumerate(images[:10], 1):
        embed = discord.Embed(title=f"#{i} - Giphy", color=discord.Color.purple())
        embed.set_image(url=img_url)
        embeds.append(embed)
    
    view = ImageSelectionView(images, query, "Giphy", ctx.author, ctx.guild)
    await msg.edit(
        content=f"🎬 **{len(images)} GIFs Giphy** pour '{query}'",
        embeds=embeds[:10],
        view=view
    )

@bot.command(name='aide')
async def help_cmd(ctx):
    """📚 Aide"""
    embed = discord.Embed(
        title="🔍 Bot Moteur de Recherche WEB",
        description="Recherche d'images sur INTERNET!",
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name="🌐 Commandes de recherche",
        value=(
            "**!search <recherche>** - Cherche sur TOUTES les sources\n"
            "**!google <recherche>** - Google Images uniquement\n"
            "**!unsplash <recherche>** - Unsplash uniquement\n"
            "**!gif <recherche>** - Giphy GIFs uniquement"
        ),
        inline=False
    )
    
    embed.add_field(
        name="💡 Exemples",
        value=(
            "`!search anime girl dark`\n"
            "`!google cute cat pfp`\n"
            "`!unsplash sunset landscape`\n"
            "`!gif funny cat`"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔍 Sources disponibles",
        value="🔍 Google Images\n📸 Unsplash\n🖼️ Pixabay\n📷 Pexels\n🎬 Giphy",
        inline=False
    )
    
    embed.add_field(
        name="⚙️ APIs optionnelles",
        value=(
            "Pour activer Pixabay: `PIXABAY_API_KEY`\n"
            "Pour activer Pexels: `PEXELS_API_KEY`"
        ),
        inline=False
    )
    
    embed.set_footer(text="Recherche TOUT sur le web!")
    
    await ctx.send(embed=embed)

@bot.command(name='ping')
async def ping(ctx):
    """🏓 Latence"""
    latency = round(bot.latency * 1000)
    await ctx.send(f'🏓 Pong! **{latency}ms**')

# ========================================
# CLEANUP
# ========================================
@bot.event
async def on_disconnect():
    global http_session
    if http_session and not http_session.closed:
        await http_session.close()

# ========================================
# LANCEMENT
# ========================================
if __name__ == '__main__':
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN manquant!")
        sys.exit(1)
    
    logger.info("🚀 Démarrage Moteur de Recherche WEB...")
    Thread(target=run_flask, daemon=True).start()
    
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.critical(f"❌ Erreur: {e}")
        sys.exit(1)
