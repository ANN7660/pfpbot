import discord
from discord.ext import commands
import os
import aiohttp
import random
import logging
import sys
from threading import Thread
from flask import Flask

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

# ========================================
# FLASK (KEEP ALIVE)
# ========================================
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot Discord actif!"

@app.route('/health')
def health():
    return {"status": "alive", "bot": str(bot.user) if bot.user else "Starting..."}

def run_flask():
    logger.info("🌐 Flask sur port 8080...")
    try:
        app.run(host='0.0.0.0', port=8080, use_reloader=False)
    except Exception as e:
        logger.error(f"❌ Flask erreur: {e}")

# ========================================
# CATÉGORIES
# ========================================
CATEGORIES = {
    "😎 Anime": {
        "api": "waifu.pics",
        "tags": ["waifu", "neko", "shinobu", "megumin", "bully", "cuddle", "cry", "hug", "awoo", "kiss", "lick", "pat", "smug", "bonk", "yeet", "blush", "smile", "wave", "highfive", "handhold", "nom", "bite", "glomp", "slap", "kill", "kick", "happy", "wink", "poke", "dance", "cringe"]
    },
    "😺 Nekos": {
        "api": "nekos.best",
        "tags": ["neko", "kitsune", "waifu", "husbando"]
    },
    "✨ Waifu": {
        "api": "waifu.im",
        "tags": ["waifu", "maid", "marin-kitagawa", "raiden-shogun", "selfies", "uniform"]
    }
}

# ========================================
# APIS
# ========================================
async def fetch_waifu_pics(tag: str) -> str:
    """API Waifu.pics"""
    url = f"https://api.waifu.pics/sfw/{tag}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('url')
    except Exception as e:
        logger.error(f"❌ Waifu.pics: {e}")
    return None

async def fetch_nekos_best(tag: str) -> str:
    """API Nekos.best"""
    url = f"https://nekos.best/api/v2/{tag}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['results'][0]['url']
    except Exception as e:
        logger.error(f"❌ Nekos.best: {e}")
    return None

async def fetch_waifu_im(tag: str) -> str:
    """API Waifu.im"""
    url = "https://api.waifu.im/search"
    params = {"included_tags": tag, "is_nsfw": "false"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('images'):
                        return data['images'][0]['url']
    except Exception as e:
        logger.error(f"❌ Waifu.im: {e}")
    return None

async def get_image(category: str, tag: str) -> str:
    """Récupère une image selon la catégorie"""
    cat_data = CATEGORIES.get(category)
    if not cat_data:
        return None
    
    api_type = cat_data["api"]
    
    if api_type == "waifu.pics":
        return await fetch_waifu_pics(tag)
    elif api_type == "nekos.best":
        return await fetch_nekos_best(tag)
    elif api_type == "waifu.im":
        return await fetch_waifu_im(tag)
    
    return None

# ========================================
# EMBEDS
# ========================================
def create_embed(title: str, image_url: str, category: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"📸 {title}",
        description=f"Catégorie: {category}",
        color=discord.Color.random()
    )
    embed.set_image(url=image_url)
    embed.set_footer(text="🎨 API Anime")
    return embed

# ========================================
# VUES DISCORD
# ========================================
class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=cat,
                emoji=cat.split()[0],
                description=f"{len(CATEGORIES[cat]['tags'])} styles"
            )
            for cat in CATEGORIES.keys()
        ]
        super().__init__(placeholder="🎨 Choisis une catégorie...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        tags = CATEGORIES[selected]['tags']
        
        view = TagView(selected, tags)
        embed = discord.Embed(
            title=f"{selected}",
            description=f"**{len(tags)}** styles disponibles !",
            color=discord.Color.purple()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class CategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(CategorySelect())
    
    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Annulé!", embed=None, view=None)

class TagSelect(discord.ui.Select):
    def __init__(self, category: str, tags: list):
        self.category = category
        options = [
            discord.SelectOption(label=tag.title(), value=tag)
            for tag in tags[:25]  # Max 25 options
        ]
        super().__init__(placeholder="✨ Choisis un style...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        tag = self.values[0]
        logger.info(f"🎯 {tag} par {interaction.user}")
        
        await interaction.response.edit_message(
            content=f"📌 Chargement...",
            embed=None,
            view=None
        )
        
        image_url = await get_image(self.category, tag)
        
        if image_url:
            embed = create_embed(tag.title(), image_url, self.category)
            view = RefreshView(self.category, tag)
            await interaction.edit_original_response(content=None, embed=embed, view=view)
        else:
            await interaction.edit_original_response(content=f"❌ Erreur")

class TagView(discord.ui.View):
    def __init__(self, category: str, tags: list):
        super().__init__(timeout=180)
        self.category = category
        self.tags = tags
        self.add_item(TagSelect(category, tags))
    
    @discord.ui.button(label="⬅️ Retour", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎨 Recherche Photo de Profil",
            description=f"**{len(CATEGORIES)}** catégories disponibles!",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=CategoryView())
    
    @discord.ui.button(label="🎲 Aléatoire", style=discord.ButtonStyle.success, row=1)
    async def random_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        tag = random.choice(self.tags)
        
        await interaction.response.edit_message(
            content=f"📌 Chargement...",
            embed=None,
            view=None
        )
        
        image_url = await get_image(self.category, tag)
        
        if image_url:
            embed = create_embed(tag.title(), image_url, self.category)
            view = RefreshView(self.category, tag)
            await interaction.edit_original_response(content=None, embed=embed, view=view)

class RefreshView(discord.ui.View):
    def __init__(self, category: str, tag: str):
        super().__init__(timeout=180)
        self.category = category
        self.tag = tag
    
    @discord.ui.button(label="🔄 Autre", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="📌 Nouvelle image...", embed=None, view=None)
        
        image_url = await get_image(self.category, self.tag)
        
        if image_url:
            embed = create_embed(self.tag.title(), image_url, self.category)
            await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(label="⬅️ Menu", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎨 Recherche Photo de Profil",
            description=f"**{len(CATEGORIES)}** catégories!",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=CategoryView())

# ========================================
# COMMANDES
# ========================================
@bot.event
async def on_ready():
    logger.info(f'✅ {bot.user} connecté!')
    logger.info(f'📊 {len(bot.guilds)} serveurs')
    logger.info(f'🎨 {len(CATEGORIES)} catégories')
    logger.info('━' * 50)

@bot.command(name='pdp')
async def search_pfp(ctx):
    """Commande principale"""
    embed = discord.Embed(
        title="🎨 Recherche Photo de Profil",
        description=f"**{len(CATEGORIES)} catégories** disponibles!\n\n"
                    "**APIs utilisées:**\n"
                    "• Waifu.pics (30+ tags anime)\n"
                    "• Nekos.best (Haute qualité)\n"
                    "• Waifu.im (Grande collection)",
        color=discord.Color.red()
    )
    embed.set_footer(text="Menu ci-dessous 👇")
    await ctx.send(embed=embed, view=CategoryView())

@bot.command(name='random')
async def random_image(ctx, category: str = None):
    """Image aléatoire"""
    if not category or category not in CATEGORIES:
        cats = ", ".join(CATEGORIES.keys())
        await ctx.send(f"❌ Catégories: {cats}")
        return
    
    tags = CATEGORIES[category]['tags']
    tag = random.choice(tags)
    msg = await ctx.send(f"📌 Chargement...")
    
    image_url = await get_image(category, tag)
    
    if image_url:
        embed = create_embed(tag.title(), image_url, category)
        view = RefreshView(category, tag)
        await msg.edit(content=None, embed=embed, view=view)
    else:
        await msg.edit(content="❌ Erreur")

@bot.command(name='ping')
async def ping(ctx):
    """Test de latence"""
    latency = round(bot.latency * 1000)
    await ctx.send(f'🏓 Pong! Latence: {latency}ms')

@bot.command(name='aide')
async def help_cmd(ctx):
    """Aide"""
    embed = discord.Embed(title="📚 Aide", color=discord.Color.green())
    embed.add_field(name="!pdp", value="🎨 Recherche interactive", inline=False)
    embed.add_field(name="!random <catégorie>", value="🎲 Image aléatoire", inline=False)
    embed.add_field(name="!ping", value="🏓 Test latence", inline=False)
    embed.add_field(
        name="Catégories",
        value="\n".join([f"• {c}" for c in CATEGORIES.keys()]),
        inline=False
    )
    await ctx.send(embed=embed)

# ========================================
# LANCEMENT
# ========================================
if __name__ == '__main__':
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN manquant!")
        sys.exit(1)
    
    logger.info("🚀 Démarrage du bot...")
    
    # Lancer Flask en arrière-plan
    Thread(target=run_flask, daemon=True).start()
    
    # Lancer le bot Discord
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.critical(f"❌ Erreur: {e}")
        sys.exit(1)
