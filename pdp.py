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

# Statistiques utilisateur (en mémoire)
user_stats = {}

# Salon de destination pour les images sélectionnées
destination_channel_id = None

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
# CATÉGORIES MASSIVES
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
        "tags": ["neko", "kitsune", "waifu", "husbando"]
    },
    "✨ Waifu": {
        "api": "waifu.im",
        "tags": ["waifu", "maid", "marin-kitagawa", "raiden-shogun", "selfies", "uniform"]
    },
    "🎮 Gaming": {
        "api": "waifu.pics",
        "tags": ["neko", "waifu", "shinobu", "megumin", "smile", "happy", "dance"]
    },
    "💖 Kawaii": {
        "api": "nekos.best",
        "tags": ["neko", "kitsune", "waifu"]
    },
    "🔥 Action": {
        "api": "waifu.pics",
        "tags": ["bonk", "yeet", "bully", "slap", "kill", "kick"]
    },
    "💕 Romance": {
        "api": "waifu.pics",
        "tags": ["cuddle", "hug", "kiss", "pat", "handhold", "smile", "blush"]
    },
    "😹 Drôle": {
        "api": "waifu.pics",
        "tags": ["smug", "dance", "cringe", "nom", "poke", "wave", "wink"]
    },
    "🌸 Cute": {
        "api": "waifu.pics",
        "tags": ["awoo", "neko", "waifu", "pat", "cuddle", "smile"]
    },
    "⚔️ Combattant": {
        "api": "waifu.im",
        "tags": ["waifu", "uniform", "maid"]
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
        logger.error(f"❌ Waifu.pics ({tag}): {e}")
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
        logger.error(f"❌ Nekos.best ({tag}): {e}")
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
        logger.error(f"❌ Waifu.im ({tag}): {e}")
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
# STATS UTILISATEUR
# ========================================
def track_user_request(user_id: int, category: str):
    if user_id not in user_stats:
        user_stats[user_id] = {
            'total': 0,
            'categories': {},
            'favorites': [],
            'last_used': None
        }
    
    user_stats[user_id]['total'] += 1
    user_stats[user_id]['last_used'] = datetime.now()
    
    if category not in user_stats[user_id]['categories']:
        user_stats[user_id]['categories'][category] = 0
    user_stats[user_id]['categories'][category] += 1

def add_favorite(user_id: int, image_url: str, category: str, tag: str):
    if user_id not in user_stats:
        user_stats[user_id] = {'favorites': []}
    
    fav = {
        'url': image_url,
        'category': category,
        'tag': tag,
        'added': datetime.now()
    }
    
    user_stats[user_id].setdefault('favorites', []).append(fav)
    
    if len(user_stats[user_id]['favorites']) > 20:
        user_stats[user_id]['favorites'].pop(0)

# ========================================
# VUES DISCORD
# ========================================
class ImageSelectionView(discord.ui.View):
    def __init__(self, images: list, category: str, tag: str, ctx):
        super().__init__(timeout=600)  # 10 minutes
        self.images = images
        self.category = category
        self.tag = tag
        self.ctx = ctx
        self.selected_images = []
        
        # Ajouter des boutons pour chaque image (max 25)
        for i, img_url in enumerate(images[:10], 1):
            button = discord.ui.Button(
                label=f"#{i}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"img_{i}",
                row=i // 5  # 5 boutons par ligne
            )
            button.callback = self.create_callback(i - 1, img_url)
            self.add_item(button)
        
        # Bouton pour envoyer les sélectionnées
        send_btn = discord.ui.Button(
            label="✅ Envoyer Sélection",
            style=discord.ButtonStyle.success,
            custom_id="send_selected",
            row=2
        )
        send_btn.callback = self.send_selected
        self.add_item(send_btn)
        
        # Bouton pour tout sélectionner
        all_btn = discord.ui.Button(
            label="📌 Tout Sélectionner",
            style=discord.ButtonStyle.primary,
            custom_id="select_all",
            row=2
        )
        all_btn.callback = self.select_all
        self.add_item(all_btn)
    
    def create_callback(self, index: int, img_url: str):
        async def callback(interaction: discord.Interaction):
            # Trouver le bouton
            button = None
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.custom_id == f"img_{index + 1}":
                    button = item
                    break
            
            if button:
                if index in self.selected_images:
                    # Désélectionner
                    self.selected_images.remove(index)
                    button.style = discord.ButtonStyle.secondary
                    button.label = f"#{index + 1}"
                else:
                    # Sélectionner
                    self.selected_images.append(index)
                    button.style = discord.ButtonStyle.success
                    button.label = f"✅ #{index + 1}"
                
                await interaction.response.edit_message(view=self)
        
        return callback
    
    async def select_all(self, interaction: discord.Interaction):
        self.selected_images = list(range(len(self.images)))
        
        # Mettre à jour tous les boutons
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id and item.custom_id.startswith("img_"):
                item.style = discord.ButtonStyle.success
                item.label = "✅ " + item.label.replace("✅ ", "")
        
        await interaction.response.edit_message(
            content=f"✅ **{len(self.selected_images)} images** sélectionnées!",
            view=self
        )
    
    async def send_selected(self, interaction: discord.Interaction):
        global destination_channel_id
        
        if not self.selected_images:
            await interaction.response.send_message(
                "❌ Aucune image sélectionnée! Clique sur les numéros pour sélectionner.",
                ephemeral=True
            )
            return
        
        # Vérifier si un salon de destination est défini
        if not destination_channel_id:
            await interaction.response.send_message(
                "❌ Aucun salon configuré! Utilise `!setsalon #salon` d'abord.",
                ephemeral=True
            )
            return
        
        channel = bot.get_channel(destination_channel_id)
        if not channel:
            await interaction.response.send_message(
                "❌ Salon introuvable! Utilise `!setsalon #salon` pour en définir un.",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            f"📤 Envoi de **{len(self.selected_images)} images** vers {channel.mention}...",
            ephemeral=True
        )
        
        # Envoyer les images sélectionnées
        for idx in self.selected_images:
            img_url = self.images[idx]
            embed = discord.Embed(
                title=f"📸 {self.tag.title()} - Image #{idx + 1}",
                description=f"**Catégorie:** {self.category}\n**Tag:** `{self.tag}`",
                color=discord.Color.random()
            )
            embed.set_image(url=img_url)
            embed.set_footer(text=f"Envoyé par {interaction.user.name}")
            
            await channel.send(embed=embed)
        
        # Message de confirmation
        await channel.send(
            f"✅ **{len(self.selected_images)} images** envoyées par {interaction.user.mention}!"
        )

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
        
        view = TagView(selected, tags, interaction.user.id, interaction)
        embed = discord.Embed(
            title=f"{selected}",
            description=f"**{len(tags)}** styles disponibles !\n\n"
                       f"Sélectionne un style.",
            color=discord.Color.purple()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class CategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(CategorySelect())
    
    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Recherche annulée!", embed=None, view=None)

class TagSelect(discord.ui.Select):
    def __init__(self, category: str, tags: list, user_id: int, original_interaction):
        self.category = category
        self.user_id = user_id
        self.original_interaction = original_interaction
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
        
        # Charger 10 images
        images = []
        for _ in range(10):
            img_url = await get_image(self.category, tag)
            if img_url:
                images.append(img_url)
        
        if images:
            # Créer un message avec toutes les images
            message_content = f"📚 **10 Images - {tag.title()}**\n\n"
            
            # Créer les embeds pour afficher les images
            embeds = []
            for i, img_url in enumerate(images[:10], 1):
                embed = discord.Embed(
                    title=f"Image #{i}",
                    color=discord.Color.random()
                )
                embed.set_image(url=img_url)
                embeds.append(embed)
            
            # Discord permet max 10 embeds par message
            view = ImageSelectionView(images, self.category, tag, interaction)
            
            await interaction.edit_original_response(
                content=f"📚 **{len(images)} images de {tag.title()}**\n\n"
                       f"👇 Clique sur les numéros pour sélectionner les images à envoyer!\n"
                       f"Puis clique sur **✅ Envoyer Sélection**",
                embeds=embeds[:10],
                view=view
            )
        else:
            await interaction.edit_original_response(
                content=f"❌ Impossible de charger les images"
            )

class TagView(discord.ui.View):
    def __init__(self, category: str, tags: list, user_id: int, original_interaction):
        super().__init__(timeout=300)
        self.category = category
        self.tags = tags
        self.user_id = user_id
        self.add_item(TagSelect(category, tags, user_id, original_interaction))
    
    @discord.ui.button(label="⬅️ Retour", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎨 Recherche Photo de Profil",
            description=f"**{len(CATEGORIES)}** catégories disponibles!",
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
    logger.info(f'🏷️ {total_tags} tags disponibles')
    logger.info('━' * 50)

@bot.command(name='setsalon')
@commands.has_permissions(administrator=True)
async def set_destination_channel(ctx, channel: discord.TextChannel):
    """Définit le salon où envoyer les images sélectionnées (Admin uniquement)"""
    global destination_channel_id
    destination_channel_id = channel.id
    
    embed = discord.Embed(
        title="✅ Salon Configuré!",
        description=f"Les images sélectionnées seront envoyées dans {channel.mention}",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name='pdp')
async def search_pfp(ctx):
    """Recherche interactive de 10 PFP à sélectionner"""
    global destination_channel_id
    
    embed = discord.Embed(
        title="🎨 Recherche Photo de Profil",
        description=f"**{len(CATEGORIES)} catégories** avec des centaines de styles!\n\n"
                    "**Comment ça marche:**\n"
                    "1️⃣ Choisis une catégorie\n"
                    "2️⃣ Choisis un style\n"
                    "3️⃣ **10 images** apparaissent\n"
                    "4️⃣ Clique sur les numéros pour sélectionner\n"
                    "5️⃣ Clique **✅ Envoyer Sélection**\n\n",
        color=discord.Color.red()
    )
    
    if destination_channel_id:
        channel = bot.get_channel(destination_channel_id)
        if channel:
            embed.add_field(
                name="📌 Salon configuré",
                value=f"Les images seront envoyées dans {channel.mention}",
                inline=False
            )
    else:
        embed.add_field(
            name="⚠️ Aucun salon configuré",
            value="Un admin doit utiliser `!setsalon #salon` d'abord!",
            inline=False
        )
    
    embed.set_footer(text=f"Demandé par {ctx.author.name}")
    await ctx.send(embed=embed, view=CategoryView())

@bot.command(name='recherche')
async def search_images_cmd(ctx, *, query: str):
    """Recherche 10 images par mot-clé avec sélection"""
    global destination_channel_id
    
    if not destination_channel_id:
        await ctx.send("❌ Configure d'abord un salon avec `!setsalon #salon` (admin requis)")
        return
    
    msg = await ctx.send(f"🔍 Recherche de 10 images **{query}**...")
    
    # Trouver les tags qui correspondent
    matching_tags = []
    for category, data in CATEGORIES.items():
        for tag in data['tags']:
            if query.lower() in tag.lower():
                matching_tags.append((category, tag))
    
    # Si pas de correspondance exacte, chercher dans les catégories
    if not matching_tags:
        for category in CATEGORIES.keys():
            if query.lower() in category.lower():
                tags = CATEGORIES[category]['tags']
                selected_tag = random.choice(tags)
                matching_tags = [(category, selected_tag)]
                break
    
    if not matching_tags:
        await msg.edit(content=f"❌ Aucun résultat pour **{query}**. Essaye: waifu, neko, cute, anime...")
        return
    
    # Prendre un tag au hasard parmi les correspondances
    category, tag = random.choice(matching_tags)
    
    track_user_request(ctx.author.id, category)
    
    # Charger 10 images
    images = []
    for _ in range(10):
        img_url = await get_image(category, tag)
        if img_url:
            images.append(img_url)
    
    if images:
        embeds = []
        for i, img_url in enumerate(images, 1):
            embed = discord.Embed(
                title=f"Image #{i}",
                color=discord.Color.random()
            )
            embed.set_image(url=img_url)
            embeds.append(embed)
        
        view = ImageSelectionView(images, category, tag, ctx)
        
        await msg.edit(
            content=f"🔍 **{len(images)} images trouvées pour '{query}'**\n"
                   f"📂 Catégorie: {category} | 🏷️ Tag: {tag}\n\n"
                   f"👇 Clique sur les numéros pour sélectionner!\n"
                   f"Puis clique sur **✅ Envoyer Sélection**",
            embeds=embeds[:10],
            view=view
        )
    else:
        await msg.edit(content=f"❌ Impossible de charger des images pour **{query}**")

@bot.command(name='batch')
async def batch_images(ctx, count: int = 10, *, category: str = None):
    """Génère plusieurs images d'un coup avec sélection"""
    global destination_channel_id
    
    if not destination_channel_id:
        await ctx.send("❌ Configure d'abord un salon avec `!setsalon #salon` (admin requis)")
        return
    
    count = min(max(count, 1), 10)  # Limité à 10 pour l'affichage
    
    if not category:
        category = random.choice(list(CATEGORIES.keys()))
    elif category not in CATEGORIES:
        cats = ", ".join(f"`{c}`" for c in list(CATEGORIES.keys())[:5])
        await ctx.send(f"❌ Catégories valides: {cats}...")
        return
    
    tags = CATEGORIES[category]['tags']
    tag = random.choice(tags)
    
    msg = await ctx.send(f"⏳ Chargement de **{count} images** de **{tag}**...")
    
    track_user_request(ctx.author.id, category)
    
    images = []
    for _ in range(count):
        img_url = await get_image(category, tag)
        if img_url:
            images.append(img_url)
    
    if images:
        embeds = []
        for i, img_url in enumerate(images, 1):
            embed = discord.Embed(
                title=f"Image #{i}",
                color=discord.Color.random()
            )
            embed.set_image(url=img_url)
            embeds.append(embed)
        
        view = ImageSelectionView(images, category, tag, ctx)
        
        await msg.edit(
            content=f"📚 **{len(images)} images de {tag.title()}**\n\n"
                   f"👇 Clique sur les numéros pour sélectionner!\n"
                   f"Puis clique sur **✅ Envoyer Sélection**",
            embeds=embeds[:10],
            view=view
        )

@bot.command(name='ping')
async def ping(ctx):
    """Test de latence"""
    latency = round(bot.latency * 1000)
    color = discord.Color.green() if latency < 100 else discord.Color.orange() if latency < 200 else discord.Color.red()
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latence: **{latency}ms**",
        color=color
    )
    await ctx.send(embed=embed)

@bot.command(name='aide')
async def help_cmd(ctx):
    """Affiche l'aide"""
    embed = discord.Embed(
        title="📚 Commandes du Bot",
        description="Voici toutes les commandes disponibles:",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="🎨 Recherche d'Images",
        value="**!pdp** - Menu interactif avec sélection\n"
              "**!recherche <mot>** - Cherche 10 images par mot-clé\n"
              "**!batch [nombre] [catégorie]** - 10 images rapides\n"
              "**!setsalon #salon** - Configure le salon (Admin)",
        inline=False
    )
    
    embed.add_field(
        name="📌 Comment ça marche?",
        value="1. Un admin fait `!setsalon #salon-images`\n"
              "2. Tu fais `!pdp` / `!recherche` / `!batch`\n"
              "3. 10 images apparaissent\n"
              "4. Tu cliques sur les numéros pour sélectionner\n"
              "5. Tu cliques **✅ Envoyer Sélection**\n"
              "6. Les images sont envoyées dans le salon!",
        inline=False
    )
    
    embed.add_field(
        name="💡 Exemples",
        value="`!recherche neko` - 10 images de neko\n"
              "`!recherche cute` - 10 images cute\n"
              "`!batch 10` - 10 images random",
        inline=False
    )
    
    embed.add_field(
        name="ℹ️ Infos",
        value="**!ping** - Latence du bot\n"
              "**!aide** - Ce message",
        inline=False
    )
    
    total_tags = sum(len(cat['tags']) for cat in CATEGORIES.values())
    embed.set_footer(text=f"{len(CATEGORIES)} catégories • {total_tags} styles")
    
    await ctx.send(embed=embed)

@bot.command(name='stats')
async def stats_cmd(ctx):
    """Statistiques globales du bot"""
    total_tags = sum(len(cat['tags']) for cat in CATEGORIES.values())
    total_users = len(user_stats)
    total_requests = sum(s.get('total', 0) for s in user_stats.values())
    
    embed = discord.Embed(
        title="📊 Statistiques Globales",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="Serveurs", value=f"🖥️ {len(bot.guilds)}", inline=True)
    embed.add_field(name="Catégories", value=f"📂 {len(CATEGORIES)}", inline=True)
    embed.add_field(name="Tags totaux", value=f"🏷️ {total_tags}", inline=True)
    embed.add_field(name="Utilisateurs", value=f"👥 {total_users}", inline=True)
    embed.add_field(name="Images générées", value=f"🖼️ {total_requests}", inline=True)
    embed.add_field(name="Latence", value=f"🏓 {round(bot.latency * 1000)}ms", inline=True)
    
    if destination_channel_id:
        channel = bot.get_channel(destination_channel_id)
        if channel:
            embed.add_field(name="Salon configuré", value=f"📌 {channel.mention}", inline=False)
    
    await ctx.send(embed=embed)

# ========================================
# CLEANUP
# ========================================
@bot.event
async def on_disconnect():
    global http_session
    if http_session and not http_session.closed:
        await http_session.close()
        logger.info("🔒 Session HTTP fermée")

# ========================================
# LANCEMENT
# ========================================
if __name__ == '__main__':
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN manquant!")
        sys.exit(1)
    
    logger.info("🚀 Démarrage du bot...")
    
    Thread(target=run_flask, daemon=True).start()
    
    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("⚠️ Arrêt demandé")
    except Exception as e:
        logger.critical(f"❌ Erreur: {e}")
        sys.exit(1)
    finally:
        if http_session and not http_session.closed:
            asyncio.run(http_session.close())
