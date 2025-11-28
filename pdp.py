import discord
from discord.ext import commands
import os
import aiohttp
import random
import logging
import sys
from threading import Thread
from flask import Flask
import asyncio
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
# CONFIGURATION
# ========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
http_session = None

# Stats
user_stats = {}

# ========================================
# FLASK
# ========================================
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot actif!"

@app.route('/health')
def health():
    return {"status": "alive"}

def run_flask():
    try:
        app.run(host='0.0.0.0', port=8080, use_reloader=False)
    except Exception as e:
        logger.error(f"❌ Flask: {e}")

# ========================================
# CATÉGORIES MASSIVES - TOUT POSSIBLE
# ========================================
CATEGORIES = {
    "😎 Anime": {
        "api": "waifu.pics",
        "tags": ["waifu", "neko", "shinobu", "megumin", "bully", "cuddle", "cry", "hug", 
                 "awoo", "kiss", "lick", "pat", "smug", "bonk", "yeet", "blush", "smile", 
                 "wave", "highfive", "handhold", "nom", "bite", "glomp", "slap", "kill", 
                 "kick", "happy", "wink", "poke", "dance", "cringe"]
    },
    "😺 Nekos": {
        "api": "nekos.best",
        "tags": ["neko", "kitsune", "waifu", "husbando", "neko", "kitsune"]
    },
    "✨ Waifu": {
        "api": "waifu.im",
        "tags": ["waifu", "maid", "marin-kitagawa", "raiden-shogun", "selfies", "uniform",
                 "waifu", "maid", "uniform", "oppai", "ero", "selfies", "ass"]
    },
    "🎮 Gaming": {
        "api": "waifu.pics",
        "tags": ["neko", "waifu", "shinobu", "megumin", "smile", "happy", "dance", "highfive", "pat"]
    },
    "💖 Kawaii": {
        "api": "nekos.best",
        "tags": ["neko", "kitsune", "waifu", "husbando", "neko"]
    },
    "🔥 Action": {
        "api": "waifu.pics",
        "tags": ["bonk", "yeet", "bully", "slap", "kill", "kick", "bite", "glomp", "bully"]
    },
    "💕 Romance": {
        "api": "waifu.pics",
        "tags": ["cuddle", "hug", "kiss", "pat", "handhold", "smile", "blush", "nom", "lick"]
    },
    "😹 Drôle": {
        "api": "waifu.pics",
        "tags": ["smug", "dance", "cringe", "nom", "poke", "wave", "wink", "yeet", "bonk"]
    },
    "🌸 Cute": {
        "api": "waifu.pics",
        "tags": ["awoo", "neko", "waifu", "pat", "cuddle", "smile", "blush", "happy"]
    },
    "⚔️ Combattant": {
        "api": "waifu.im",
        "tags": ["waifu", "uniform", "maid", "waifu"]
    },
    "🎭 Expression": {
        "api": "waifu.pics",
        "tags": ["smile", "happy", "cry", "blush", "smug", "wink", "cringe"]
    },
    "👫 Social": {
        "api": "waifu.pics",
        "tags": ["hug", "kiss", "pat", "cuddle", "handhold", "wave", "highfive"]
    },
    "😈 Troll": {
        "api": "waifu.pics",
        "tags": ["bully", "bonk", "slap", "kick", "kill", "yeet", "smug"]
    },
    "🌟 Popular": {
        "api": "waifu.pics",
        "tags": ["waifu", "neko", "shinobu", "megumin", "smile", "pat"]
    },
    "🎨 Artistique": {
        "api": "waifu.im",
        "tags": ["waifu", "maid", "uniform", "selfies"]
    }
}

# ========================================
# SESSION HTTP
# ========================================
async def get_session():
    global http_session
    if http_session is None or http_session.closed:
        http_session = aiohttp.ClientSession()
    return http_session

# ========================================
# APIS
# ========================================
async def fetch_waifu_pics(tag: str) -> str:
    url = f"https://api.waifu.pics/sfw/{tag}"
    try:
        session = await get_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('url')
    except Exception as e:
        logger.error(f"❌ Waifu.pics: {e}")
    return None

async def fetch_nekos_best(tag: str) -> str:
    url = f"https://nekos.best/api/v2/{tag}"
    try:
        session = await get_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 200:
                data = await response.json()
                return data['results'][0]['url']
    except Exception as e:
        logger.error(f"❌ Nekos.best: {e}")
    return None

async def fetch_waifu_im(tag: str) -> str:
    url = "https://api.waifu.im/search"
    params = {"included_tags": tag, "is_nsfw": "false"}
    try:
        session = await get_session()
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('images'):
                    return data['images'][0]['url']
    except Exception as e:
        logger.error(f"❌ Waifu.im: {e}")
    return None

async def get_image(category: str, tag: str, retry: int = 2) -> str:
    cat_data = CATEGORIES.get(category)
    if not cat_data:
        return None
    
    api_type = cat_data["api"]
    
    for attempt in range(retry):
        try:
            if api_type == "waifu.pics":
                result = await fetch_waifu_pics(tag)
            elif api_type == "nekos.best":
                result = await fetch_nekos_best(tag)
            elif api_type == "waifu.im":
                result = await fetch_waifu_im(tag)
            else:
                return None
            
            if result:
                return result
        except Exception as e:
            if attempt < retry - 1:
                await asyncio.sleep(1)
    
    return None

# ========================================
# STATS
# ========================================
def track_user_request(user_id: int, category: str):
    if user_id not in user_stats:
        user_stats[user_id] = {'total': 0, 'categories': {}}
    user_stats[user_id]['total'] += 1
    if category not in user_stats[user_id]['categories']:
        user_stats[user_id]['categories'][category] = 0
    user_stats[user_id]['categories'][category] += 1

# ========================================
# VUE SÉLECTION SALON
# ========================================
class ChannelSelectView(discord.ui.View):
    def __init__(self, images: list, category: str, tag: str, user, guild):
        super().__init__(timeout=300)
        self.images = images
        self.category = category
        self.tag = tag
        self.user = user
        self.guild = guild
        self.selected_channel = None
        
        # Créer le menu déroulant avec les salons
        options = []
        for channel in guild.text_channels[:25]:  # Max 25
            options.append(
                discord.SelectOption(
                    label=f"#{channel.name}",
                    value=str(channel.id),
                    description=f"Envoyer dans {channel.name}"
                )
            )
        
        if options:
            select = discord.ui.Select(
                placeholder="📌 Choisis le salon où envoyer les images...",
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
            content=f"📤 Envoi de **{len(self.images)} images** vers {channel.mention}...",
            view=None
        )
        
        # Envoyer les images SANS embed, juste les URLs
        for img_url in self.images:
            await channel.send(img_url)
        
        # Message de confirmation
        await channel.send(f"✅ **{len(self.images)} images** envoyées par {self.user.mention}!")
        
        await interaction.followup.send(
            f"✅ {len(self.images)} images envoyées dans {channel.mention}!",
            ephemeral=True
        )

# ========================================
# VUE SÉLECTION D'IMAGES
# ========================================
class ImageSelectionView(discord.ui.View):
    def __init__(self, images: list, category: str, tag: str, user, guild):
        super().__init__(timeout=600)
        self.images = images
        self.category = category
        self.tag = tag
        self.user = user
        self.guild = guild
        self.selected_images = []
        
        # Boutons pour chaque image
        for i in range(min(len(images), 10)):
            button = discord.ui.Button(
                label=f"#{i+1}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"img_{i}",
                row=i // 5
            )
            button.callback = self.create_callback(i)
            self.add_item(button)
        
        # Bouton tout sélectionner
        all_btn = discord.ui.Button(
            label="📌 Tout",
            style=discord.ButtonStyle.primary,
            custom_id="select_all",
            row=2
        )
        all_btn.callback = self.select_all
        self.add_item(all_btn)
        
        # Bouton envoyer
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
        
        # Récupérer les images sélectionnées
        selected = [self.images[i] for i in self.selected_images]
        
        # Afficher le menu de sélection de salon
        view = ChannelSelectView(selected, self.category, self.tag, self.user, self.guild)
        
        await interaction.response.edit_message(
            content=f"📌 **{len(selected)} images** sélectionnées!\n\n"
                   f"👇 Choisis maintenant le salon où les envoyer:",
            embeds=[],
            view=view
        )

# SUITE DANS PARTIE 2...
# ========================================
# VUES DISCORD - MENUS
# ========================================
class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=cat,
                emoji=cat.split()[0],
                description=f"{len(CATEGORIES[cat]['tags'])} styles"
            )
            for cat in list(CATEGORIES.keys())[:25]
        ]
        super().__init__(placeholder="🎨 Choisis une catégorie...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        tags = CATEGORIES[selected]['tags']
        track_user_request(interaction.user.id, selected)
        view = TagView(selected, tags, interaction.user, interaction.guild)
        embed = discord.Embed(
            title=f"{selected}",
            description=f"**{len(tags)}** styles disponibles!",
            color=discord.Color.purple()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class CategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(CategorySelect())
    
    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Annulé!", embed=None, view=None)

class TagSelect(discord.ui.Select):
    def __init__(self, category: str, tags: list, user, guild):
        self.category = category
        self.user = user
        self.guild = guild
        options = [
            discord.SelectOption(label=tag.title(), value=tag)
            for tag in tags[:25]
        ]
        super().__init__(placeholder="✨ Choisis un style...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        tag = self.values[0]
        await interaction.response.edit_message(
            content=f"⏳ Chargement de 10 images **{tag}**...",
            embed=None,
            view=None
        )
        
        images = []
        for _ in range(10):
            img_url = await get_image(self.category, tag)
            if img_url:
                images.append(img_url)
        
        if images:
            embeds = []
            for i, img_url in enumerate(images, 1):
                embed = discord.Embed(title=f"#{i}", color=discord.Color.random())
                embed.set_image(url=img_url)
                embeds.append(embed)
            
            view = ImageSelectionView(images, self.category, tag, self.user, self.guild)
            await interaction.edit_original_response(
                content=f"📚 **{len(images)} images de {tag.title()}**\n"
                       f"👇 Sélectionne celles que tu veux!",
                embeds=embeds[:10],
                view=view
            )

class TagView(discord.ui.View):
    def __init__(self, category: str, tags: list, user, guild):
        super().__init__(timeout=300)
        self.add_item(TagSelect(category, tags, user, guild))
    
    @discord.ui.button(label="⬅️ Retour", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎨 Recherche PFP",
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
    total_tags = sum(len(cat['tags']) for cat in CATEGORIES.values())
    logger.info(f'🏷️ {total_tags} tags')
    logger.info('━' * 50)

@bot.command(name='pdp')
async def search_pfp(ctx):
    """Menu interactif avec 10 images"""
    embed = discord.Embed(
        title="🎨 Recherche Photo de Profil",
        description=f"**{len(CATEGORIES)} catégories** disponibles!\n\n"
                    "**Comment ça marche:**\n"
                    "1️⃣ Choisis une catégorie\n"
                    "2️⃣ Choisis un style\n"
                    "3️⃣ 10 images apparaissent\n"
                    "4️⃣ Sélectionne celles que tu veux\n"
                    "5️⃣ Choisis le salon où envoyer\n"
                    "6️⃣ Les images sont envoyées!",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed, view=CategoryView())

@bot.command(name='recherche')
async def search_cmd(ctx, *, query: str):
    """Recherche 10 images par mot-clé"""
    msg = await ctx.send(f"🔍 Recherche **{query}**...")
    
    matching = []
    for category, data in CATEGORIES.items():
        for tag in data['tags']:
            if query.lower() in tag.lower():
                matching.append((category, tag))
    
    if not matching:
        for category in CATEGORIES.keys():
            if query.lower() in category.lower():
                tags = CATEGORIES[category]['tags']
                matching = [(category, random.choice(tags))]
                break
    
    if not matching:
        await msg.edit(content=f"❌ Aucun résultat pour **{query}**")
        return
    
    category, tag = random.choice(matching)
    track_user_request(ctx.author.id, category)
    
    images = []
    for _ in range(10):
        img_url = await get_image(category, tag)
        if img_url:
            images.append(img_url)
    
    if images:
        embeds = []
        for i, img_url in enumerate(images, 1):
            embed = discord.Embed(title=f"#{i}", color=discord.Color.random())
            embed.set_image(url=img_url)
            embeds.append(embed)
        
        view = ImageSelectionView(images, category, tag, ctx.author, ctx.guild)
        await msg.edit(
            content=f"🔍 **{len(images)} images** trouvées pour **{query}**!\n"
                   f"👇 Sélectionne celles que tu veux!",
            embeds=embeds[:10],
            view=view
        )

@bot.command(name='batch')
async def batch_cmd(ctx, count: int = 10):
    """Génère 10 images random"""
    count = min(max(count, 1), 10)
    category = random.choice(list(CATEGORIES.keys()))
    tags = CATEGORIES[category]['tags']
    tag = random.choice(tags)
    
    msg = await ctx.send(f"⏳ Chargement de {count} images...")
    track_user_request(ctx.author.id, category)
    
    images = []
    for _ in range(count):
        img_url = await get_image(category, tag)
        if img_url:
            images.append(img_url)
    
    if images:
        embeds = []
        for i, img_url in enumerate(images, 1):
            embed = discord.Embed(title=f"#{i}", color=discord.Color.random())
            embed.set_image(url=img_url)
            embeds.append(embed)
        
        view = ImageSelectionView(images, category, tag, ctx.author, ctx.guild)
        await msg.edit(
            content=f"📚 **{len(images)} images de {tag.title()}**\n"
                   f"👇 Sélectionne celles que tu veux!",
            embeds=embeds[:10],
            view=view
        )

@bot.command(name='aide')
async def help_cmd(ctx):
    """Aide complète avec embed"""
    embed = discord.Embed(
        title="📚 Aide - Bot PFP",
        description="Voici toutes les commandes disponibles:",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="🎨 Commandes Principales",
        value=(
            "**!pdp** - Menu interactif complet\n"
            "**!recherche <mot>** - Recherche par mot-clé\n"
            "**!batch [nombre]** - Génère 10 images random"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📌 Comment ça fonctionne?",
        value=(
            "1. Lance une commande (!pdp, !recherche, !batch)\n"
            "2. 10 images apparaissent avec des embeds\n"
            "3. Clique sur #1, #2... pour sélectionner\n"
            "4. Clique sur ✅ Envoyer\n"
            "5. Choisis le salon dans le menu déroulant\n"
            "6. Les images sont envoyées SANS embed!"
        ),
        inline=False
    )
    
    embed.add_field(
        name="💡 Exemples",
        value=(
            "`!pdp` - Menu complet\n"
            "`!recherche neko` - 10 images neko\n"
            "`!recherche cute waifu` - Recherche avancée\n"
            "`!batch 10` - 10 images random"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎯 Catégories disponibles",
        value=", ".join([cat.split()[1] if len(cat.split()) > 1 else cat for cat in list(CATEGORIES.keys())[:10]]) + "...",
        inline=False
    )
    
    embed.add_field(
        name="ℹ️ Autres commandes",
        value="**!ping** - Latence\n**!stats** - Statistiques",
        inline=False
    )
    
    total_tags = sum(len(cat['tags']) for cat in CATEGORIES.values())
    embed.set_footer(text=f"✨ {len(CATEGORIES)} catégories • {total_tags} styles disponibles")
    
    await ctx.send(embed=embed)

@bot.command(name='ping')
async def ping(ctx):
    """Latence"""
    latency = round(bot.latency * 1000)
    await ctx.send(f'🏓 Pong! **{latency}ms**')

@bot.command(name='stats')
async def stats_cmd(ctx):
    """Stats globales"""
    total_tags = sum(len(cat['tags']) for cat in CATEGORIES.values())
    embed = discord.Embed(title="📊 Statistiques", color=discord.Color.blue())
    embed.add_field(name="Serveurs", value=f"🖥️ {len(bot.guilds)}", inline=True)
    embed.add_field(name="Catégories", value=f"📂 {len(CATEGORIES)}", inline=True)
    embed.add_field(name="Tags", value=f"🏷️ {total_tags}", inline=True)
    await ctx.send(embed=embed)

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
    
    logger.info("🚀 Démarrage...")
    Thread(target=run_flask, daemon=True).start()
    
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.critical(f"❌ Erreur: {e}")
        sys.exit(1)
