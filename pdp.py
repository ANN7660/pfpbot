import discord
from discord.ext import commands
import os
import aiohttp
import random
import re
from bs4 import BeautifulSoup
from threading import Thread
from flask import Flask
import asyncio
import sys
import logging
import json 

# ========================================
# CONFIGURATION DU LOGGING
# ========================================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

logger = logging.getLogger(__name__)

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Récupération du token
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# 🌐 SERVEUR WEB FLASK
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot Discord Pinterest actif !"

@app.route('/health')
def health():
    return {"status": "alive", "bot": str(bot.user) if bot.user else "Initialisation..."}

# 🛠️ CORRECTION: Fonction run_flask simplifiée pour éviter le crash de Gunicorn/Signal
def run_flask():
    """Lance le serveur Flask simple dans un thread séparé."""
    # use_reloader=False est important pour éviter des démarrages multiples dans un contexte de thread
    logger.info("🌐 Démarrage du serveur Flask simple sur 0.0.0.0:8080...")
    try:
        app.run(host='0.0.0.0', port=8080, use_reloader=False)
    except Exception as e:
        logger.error(f"❌ ERREUR LORS DU LANCEMENT DE FLASK: {e}")

# 🎨 Dictionnaire des CATÉGORIES (omis pour la concision mais supposé être présent)
CATEGORIES = {
    "🎨 Aesthetic": ["aesthetic pink", "aesthetic blue", "aesthetic purple", "aesthetic dark", "aesthetic light", "aesthetic vintage"],
    "😎 Anime": ["anime boy", "anime girl", "anime aesthetic", "anime dark", "manga", "anime pfp", "anime cool", "anime kawaii"],
    "🌙 Dark": ["dark aesthetic", "dark grunge", "dark angel", "dark red", "dark blue", "dark purple", "gothic dark"],
    "✨ Cute": ["cute aesthetic", "cute anime", "cute pastel", "kawaii", "soft aesthetic", "adorable", "cute cat"],
    "🎮 Gaming": ["gaming setup", "gaming aesthetic", "cyberpunk", "gamer", "gaming neon", "esports", "gaming rgb"],
    "🔥 Grunge": ["grunge aesthetic", "grunge dark", "grunge y2k", "grunge red", "grunge indie", "grunge vintage"],
    "💜 Y2K": ["y2k aesthetic", "y2k cyber", "y2k pink", "y2k purple", "y2k star", "y2k butterfly", "y2k sparkle"],
    "🌸 Pastel": ["pastel pink", "pastel blue", "pastel aesthetic", "soft pastel", "pastel kawaii", "pastel rainbow"],
    "⚫ Monochrome": ["black aesthetic", "white aesthetic", "grey aesthetic", "monochrome art", "black and white"],
    "🌈 Colorful": ["colorful aesthetic", "rainbow aesthetic", "neon aesthetic", "vibrant colors", "bright colors"],
    "🎭 Alternative": ["alt aesthetic", "goth aesthetic", "emo aesthetic", "punk aesthetic", "scene aesthetic"],
    "🌟 Space": ["space aesthetic", "galaxy aesthetic", "stars aesthetic", "cosmic aesthetic", "nebula", "astronaut"],
    "🏙️ Urban": ["city aesthetic", "urban aesthetic", "street aesthetic", "tokyo aesthetic", "cyberpunk city"],
    "🌺 Nature": ["nature aesthetic", "flower aesthetic", "sunset aesthetic", "beach aesthetic", "forest aesthetic"],
    "👑 Luxury": ["luxury aesthetic", "gold aesthetic", "elegant aesthetic", "classy aesthetic", "designer"],
    "💀 Edgy": ["edgy aesthetic", "skeleton", "skull aesthetic", "badass", "rebel aesthetic", "chains aesthetic"],
    "🎵 Music": ["music aesthetic", "singer", "band aesthetic", "rock aesthetic", "rap aesthetic", "headphones"],
    "⚡ Neon": ["neon aesthetic", "neon lights", "neon pink", "neon blue", "cyberpunk neon", "neon city"],
    "🌸 Cottagecore": ["cottagecore aesthetic", "cottage", "fairycore", "forest cottage", "mushroom aesthetic"],
    "🦋 Indie": ["indie aesthetic", "indie kid", "indie grunge", "indie vintage", "indie bedroom"],
    "💎 Baddie": ["baddie aesthetic", "bad girl", "hot aesthetic", "confident aesthetic", "boss aesthetic"],
    "🌊 Ocean": ["ocean aesthetic", "sea aesthetic", "beach waves", "mermaid", "underwater aesthetic"],
    "🔮 Witchy": ["witchy aesthetic", "witch", "magic aesthetic", "crystals", "mystical aesthetic"],
    "👾 Retro": ["retro aesthetic", "90s aesthetic", "80s aesthetic", "vintage retro", "arcade aesthetic"],
    "🎬 Cinema": ["cinema aesthetic", "movie aesthetic", "film aesthetic", "director", "vintage film"],
    "🌙 Dreamy": ["dreamy aesthetic", "cloud aesthetic", "soft dreamy", "ethereal", "fantasy dreamy"],
    "🍓 Kawaii": ["kawaii aesthetic", "sanrio", "hello kitty", "cute kawaii", "japanese kawaii"],
    "⛓️ Chains": ["chains aesthetic", "chain grunge", "chain jewelry", "metal chains", "silver chains"],
    "🌹 Romance": ["romance aesthetic", "love aesthetic", "romantic", "valentine", "couple aesthetic"],
    "🎪 Circus": ["circus aesthetic", "carnival", "clown aesthetic", "vintage circus", "fairground"],
    "🏍️ Biker": ["biker aesthetic", "motorcycle", "leather jacket", "rebel biker", "harley aesthetic"],
    "📚 Academia": ["dark academia", "light academia", "library aesthetic", "bookish", "vintage academia"],
    "🌃 Nightcore": ["nightcore aesthetic", "night aesthetic", "midnight", "night city", "late night"],
    "🎀 Coquette": ["coquette aesthetic", "bow aesthetic", "pink coquette", "soft coquette", "ribbon aesthetic"],
    "🔥 Sigma": ["sigma male", "sigma aesthetic", "lone wolf", "alpha aesthetic", "motivation aesthetic"]
}

# Headers pour éviter la détection (Inclut Brotli)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br', # 'br' est clé pour Brotli
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

async def search_pinterest(query: str, max_results: int = 20):
    """
    Scraper Pinterest avec double-méthode d'analyse pour la robustesse (Structured + Regex Fallback).
    """
    logger.info(f"🔍 DÉBUT de la recherche pour: '{query}'")
    
    try:
        search_query = query.replace(' ', '%20')
        url = f"https://www.pinterest.com/search/pins/?q={search_query}"
        
        logger.info(f"📌 URL générée: {url}")
        logger.info(f"⏳ Délai de 2 secondes avant la requête...")
        await asyncio.sleep(2)
        logger.info(f"🌐 Envoi de la requête HTTP vers Pinterest...")
        
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, timeout=20) as response:
                logger.info(f"📥 Réponse reçue - Status Code: {response.status}")
                
                if response.status != 200:
                    logger.error(f"❌ Erreur HTTP {response.status} pour la requête: {query}")
                    return None
                
                html = await response.text()
                logger.info(f"📄 HTML reçu - Taille: {len(html)} caractères")
                
                soup = BeautifulSoup(html, 'html.parser')
                image_urls = []
                
                # Méthode 1: Chercher dans les balises img (Gardée mais inefficace)
                logger.info(f"🔎 Méthode 1: Recherche dans les balises <img>...")
                img_tags = soup.find_all('img')
                
                for img in img_tags:
                    src = img.get('src')
                    if src and 'pinimg.com' in src:
                        high_res = src.replace('236x', '736x').replace('474x', '736x')
                        if high_res not in image_urls:
                            image_urls.append(high_res)
                
                logger.info(f"    ✅ {len(image_urls)} URLs trouvées via <img>")


                # 🛑 Méthode 2: Parsing structuré (CORRIGÉ pour gérer les changements de clé)
                logger.info(f"🔎 Méthode 2: Recherche dans le JSON embarqué (Parsing structuré + Fallback)...")
                scripts = soup.find_all('script', {'id': '__PWS_DATA__'})
                logger.info(f"    Trouvé {len(scripts)} scripts avec id='__PWS_DATA__'")
                
                if scripts:
                    content = scripts[0].string
                    
                    # Tentative 1: Parsing structuré du JSON (méthode préférée)
                    try:
                        data = json.loads(content.strip())
                        results = []
                        results_data = {}
                        
                        # Accès Conditionnel 1 : Chemin ResourceResponses (Ancien chemin stable, qui a craché)
                        if 'resourceResponses' in data and len(data['resourceResponses']) > 0:
                            results_data = data['resourceResponses'][0]['response']['data']
                        
                        # Accès Conditionnel 2 : Chemin ReduxState (Souvent utilisé comme alternative)
                        elif 'initialReduxState' in data and 'pins' in data['initialReduxState']:
                            results_data = data['initialReduxState']['pins']
                        
                        
                        # Tenter d'extraire la liste de pins de l'objet de données trouvé
                        if results_data and 'data' in results_data:
                            results = results_data['data']
                        elif results_data and 'results' in results_data:
                            results = results_data['results']
                        
                        
                        count = 0
                        for pin in results:
                            if isinstance(pin, dict) and 'images' in pin:
                                # Tenter d'extraire l'URL originale ou 736x
                                if 'orig' in pin['images']:
                                    high_res_url = pin['images']['orig']['url']
                                elif '736x' in pin['images']:
                                    high_res_url = pin['images']['736x']['url']
                                else:
                                    continue
                                    
                                if high_res_url not in image_urls:
                                    image_urls.append(high_res_url)
                                    count += 1

                        logger.info(f"    ✅ {count} URLs trouvées via le JSON structuré.")

                    except json.JSONDecodeError:
                        logger.error("❌ ERREUR JSON: Impossible de décoder le contenu de __PWS_DATA__.")
                    except Exception as e:
                        logger.warning(f"⚠️ ERREUR PARSING JSON: {e.__class__.__name__}: {e}. Tentative de fallback Regex...")

                    # Tentative 2 (Fallback): Regex de sécurité si l'analyse structurée a trouvé trop peu d'images
                    if len(image_urls) < 5: 
                        logger.info("🔎 Fallback Regex: Recherche des URLs brutes...")
                        urls_from_regex = re.findall(r'https://i\.pinimg\.com/[^"\']+\.jpg', content)
                        
                        count_regex = 0
                        for url_brute in urls_from_regex:
                            high_res = url_brute.replace('236x', '736x').replace('474x', '736x')
                            if high_res not in image_urls:
                                image_urls.append(high_res)
                                count_regex += 1
                        
                        logger.info(f"    ✅ {count_regex} URLs trouvées via Regex.")
                
                
                logger.info(f"    ✅ Total: {len(image_urls)} URLs uniques")
                
                # Filtrer pour avoir que des images de bonne qualité
                quality_urls = [url for url in image_urls if '736x' in url or 'originals' in url]
                
                if not quality_urls and image_urls:
                    quality_urls = image_urls[:max_results]
                
                if quality_urls:
                    logger.info(f"✅ SUCCÈS: {len(quality_urls)} images de qualité trouvées pour '{query}'")
                    return quality_urls[:max_results]
                else:
                    logger.warning(f"⚠️ ÉCHEC: Aucune image trouvée après analyse pour '{query}'")
                    return None
                    
    except asyncio.TimeoutError:
        logger.error(f"❌ TIMEOUT: Délai d'attente dépassé (>20s) pour '{query}'")
        return None
    except Exception as e:
        logger.error(f"❌ ERREUR GÉNÉRALE pour '{query}': {e.__class__.__name__}: {e}")
        return None


# ========================================
# CLASSES ET VUES INTERACTIVES (INCHANGÉES)
# ========================================

class CustomSearchModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="🔍 Recherche Personnalisée")
        
        self.search_input = discord.ui.TextInput(
            label="Que cherches-tu ?",
            placeholder="Ex: red anime girl, dark aesthetic, cute cat...",
            style=discord.TextStyle.short,
            required=True,
            max_length=100
        )
        self.add_item(self.search_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        query = self.search_input.value
        logger.info(f"🎯 Recherche personnalisée demandée par {interaction.user}: '{query}'")
        
        await interaction.response.edit_message(
            content=f"📌 Recherche Pinterest pour **{query}**...\n⏳ Cela peut prendre quelques secondes...",
            embed=None,
            view=None
        )
        
        images = await search_pinterest(query)
        
        if images:
            image_url = random.choice(images)
            embed = discord.Embed(
                title=f"📸 {query.title()}",
                description="🔍 Recherche personnalisée Pinterest",
                color=discord.Color.red()
            )
            embed.set_image(url=image_url)
            embed.set_footer(text="📌 Source: Pinterest")
            embed.add_field(
                name="🔗 Lien direct",
                value=f"[Voir l'image]({image_url})",
                inline=False
            )
            
            view = RefreshView(query, "Recherche personnalisée")
            await interaction.edit_original_response(content=None, embed=embed, view=view)
        else:
            await interaction.edit_original_response(
                content=f"❌ Aucune image trouvée pour **{query}**\n💡 Problème de scraping. Essaye avec d'autres mots-clés !",
                embed=None
            )

class CategorySelect(discord.ui.Select):
    def __init__(self):
        categories_list = list(CATEGORIES.items())[:25]
        options = [
            discord.SelectOption(label=category, emoji=category.split()[0], description=f"{len(subcats)} styles")
            for category, subcats in categories_list
        ]
        super().__init__(placeholder="🎨 Choisis une catégorie (Page 1/2)...", options=options, min_values=1, max_values=1)
    
    async def callback(self, interaction: discord.Interaction):
        selected_category = self.values[0]
        subcategories = CATEGORIES[selected_category]
        
        view = SubcategoryView(selected_category, subcategories)
        embed = discord.Embed(
            title=f"{selected_category}",
            description=f"Choisis un style spécifique parmi **{len(subcategories)}** options !",
            color=discord.Color.purple()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class CategorySelect2(discord.ui.Select):
    def __init__(self):
        categories_list = list(CATEGORIES.items())[25:]
        options = [
            discord.SelectOption(label=category, emoji=category.split()[0], description=f"{len(subcats)} styles")
            for category, subcats in categories_list
        ]
        super().__init__(placeholder="🎨 Choisis une catégorie (Page 2/2)...", options=options, min_values=1, max_values=1)
    
    async def callback(self, interaction: discord.Interaction):
        selected_category = self.values[0]
        subcategories = CATEGORIES[selected_category]
        
        view = SubcategoryView(selected_category, subcategories)
        embed = discord.Embed(
            title=f"{selected_category}",
            description=f"Choisis un style spécifique parmi **{len(subcategories)}** options !",
            color=discord.Color.purple()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class CategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(CategorySelect())
        self.add_item(CategorySelect2())
    
    @discord.ui.button(label="🔍 Recherche personnalisée", style=discord.ButtonStyle.success, row=2)
    async def custom_search_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CustomSearchModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.danger, row=2)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Recherche annulée !", embed=None, view=None)

class SubcategorySelect(discord.ui.Select):
    def __init__(self, category: str, subcategories: list):
        self.category = category
        options = [
            discord.SelectOption(label=subcat.title(), value=subcat, description=f"Style: {subcat}")
            for subcat in subcategories
        ]
        super().__init__(placeholder="✨ Choisis un style...", options=options, min_values=1, max_values=1)
    
    async def callback(self, interaction: discord.Interaction):
        selected_style = self.values[0]
        logger.info(f"🎯 Style sélectionné par {interaction.user}: '{selected_style}' (Catégorie: {self.category})")
        
        await interaction.response.edit_message(
            content=f"📌 Recherche Pinterest pour **{selected_style}**...\n⏳ Cela peut prendre quelques secondes...",
            embed=None,
            view=None
        )
        
        images = await search_pinterest(selected_style)
        
        if images:
            image_url = random.choice(images)
            embed = discord.Embed(
                title=f"📸 {selected_style.title()}",
                description=f"Catégorie: {self.category}",
                color=discord.Color.red()
            )
            embed.set_image(url=image_url)
            embed.set_footer(text="📌 Source: Pinterest")
            embed.add_field(
                name="🔗 Lien direct",
                value=f"[Voir l'image]({image_url})",
                inline=False
            )
            
            view = RefreshView(selected_style, self.category)
            await interaction.edit_original_response(content=None, embed=embed, view=view)
        else:
            await interaction.edit_original_response(
                content=f"❌ Aucune image trouvée pour **{selected_style}**",
                embed=None
            )

class SubcategoryView(discord.ui.View):
    def __init__(self, category: str, subcategories: list):
        super().__init__(timeout=180)
        self.add_item(SubcategorySelect(category, subcategories))
    
    @discord.ui.button(label="⬅️ Retour", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CategoryView()
        embed = discord.Embed(
            title="🎨 Recherche de Photo de Profil",
            description=f"**{len(CATEGORIES)} catégories** disponibles avec **200+ styles** !\n\n"
                        f"Tu peux aussi utiliser la **recherche personnalisée** 🔍",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Recherche annulée !", embed=None, view=None)

class RefreshView(discord.ui.View):
    def __init__(self, query: str, category: str):
        super().__init__(timeout=180)
        self.query = query
        self.category = category
    
    @discord.ui.button(label="🔄 Autre image", style=discord.ButtonStyle.primary, emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(f"🔄 Rafraîchissement demandé par {interaction.user} pour '{self.query}'")
        
        await interaction.response.edit_message(
            content=f"📌 Recherche d'une nouvelle image...",
            embed=None,
            view=None
        )
        
        images = await search_pinterest(self.query)
        
        if images:
            image_url = random.choice(images)
            embed = discord.Embed(
                title=f"📸 {self.query.title()}",
                description=f"Catégorie: {self.category}",
                color=discord.Color.red()
            )
            embed.set_image(url=image_url)
            embed.set_footer(text="📌 Source: Pinterest")
            embed.add_field(
                name="🔗 Lien direct",
                value=f"[Voir l'image]({image_url})",
                inline=False
            )
            
            await interaction.edit_original_response(content=None, embed=embed, view=self)
        else:
            await interaction.edit_original_response(
                content=f"❌ Aucune image trouvée",
                embed=None,
                view=None
            )
    
    @discord.ui.button(label="⬅️ Menu principal", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CategoryView()
        embed = discord.Embed(
            title="🎨 Recherche de Photo de Profil",
            description=f"**{len(CATEGORIES)} catégories** disponibles avec **200+ styles** !\n\n"
                        f"Tu peux aussi utiliser la **recherche personnalisée** 🔍",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

# ========================================
# COMMANDES DU BOT
# ========================================

@bot.event
async def on_ready():
    logger.info(f'✅ {bot.user} est connecté à Discord !')
    logger.info(f'📊 Serveurs: {len(bot.guilds)}')
    logger.info(f'🎨 Catégories disponibles: {len(CATEGORIES)}')
    total_styles = sum(len(styles) for styles in CATEGORIES.values())
    logger.info(f'✨ Total de styles: {total_styles}')
    logger.info('📌 Mode: Pinterest scraping (Optimisé)')
    logger.info('🌐 Serveur web Flask actif sur port 8080')
    logger.info('━' * 50)

@bot.command(name='pdp')
async def search_pfp(ctx):
    """Commande principale pour rechercher des photos de profil"""
    logger.info(f"📋 Commande !pdp utilisée par {ctx.author} dans #{ctx.channel}")
    
    view = CategoryView()
    embed = discord.Embed(
        title="🎨 Recherche de Photo de Profil Pinterest",
        description=f"**{len(CATEGORIES)} catégories** disponibles avec **200+ styles** !\n\n"
                    f"**Utilise le menu déroulant** pour choisir une catégorie\n"
                    f"**Ou clique sur 🔍 Recherche personnalisée** pour taper ce que tu veux !\n\n"
                    f"**Quelques catégories populaires:**\n"
                    f"• Aesthetic, Anime, Dark, Cute\n"
                    f"• Gaming, Grunge, Y2K, Sigma\n"
                    f"• Baddie, Kawaii, Indie, Edgy\n"
                    f"• Et 25 autres catégories...",
        color=discord.Color.red()
    )
    embed.set_footer(text="📌 Utilise les menus ci-dessous 👇")
    await ctx.send(embed=embed, view=view)

@bot.command(name='recherche')
async def quick_search(ctx, *, query: str):
    """Recherche rapide sans menu"""
    logger.info(f"🔍 Commande !recherche utilisée par {ctx.author}: '{query}'")
    
    msg = await ctx.send(f"📌 Recherche Pinterest pour **{query}**...")
    
    images = await search_pinterest(query)
    
    if images:
        image_url = random.choice(images)
        embed = discord.Embed(
            title=f"📸 {query.title()}",
            description="Recherche rapide Pinterest",
            color=discord.Color.red()
        )
        embed.set_image(url=image_url)
        embed.set_footer(text="📌 Source: Pinterest")
        embed.add_field(
            name="🔗 Lien direct",
            value=f"[Voir l'image]({image_url})",
            inline=False
        )
        
        view = RefreshView(query, "Recherche rapide")
        await msg.edit(content=None, embed=embed, view=view)
    else:
        await msg.edit(content=f"❌ Aucune image trouvée pour **{query}**")

@bot.command(name='categories')
async def list_categories(ctx):
    """Liste toutes les catégories disponibles"""
    logger.info(f"📋 Commande !categories utilisée par {ctx.author}")
    
    embed = discord.Embed(
        title=f"📋 Toutes les Catégories ({len(CATEGORIES)})",
        description="Voici toutes les catégories et styles disponibles:",
        color=discord.Color.gold()
    )
    
    categories_list = list(CATEGORIES.items())
    for i in range(0, len(categories_list), 10):
        chunk = categories_list[i:i+10]
        field_value = ""
        for category, subcats in chunk:
            styles = ", ".join(subcats[:3])
            if len(subcats) > 3:
                styles += f"... (+{len(subcats)-3})"
            field_value += f"**{category}**: {styles}\n"
        
        if field_value:
            embed.add_field(name=f"Page {i//10 + 1}", value=field_value, inline=False)
    
    total_styles = sum(len(styles) for styles in CATEGORIES.values())
    embed.set_footer(text=f"Total: {len(CATEGORIES)} catégories • {total_styles} styles")
    
    await ctx.send(embed=embed)

@bot.command(name='aide')
async def help_cmd(ctx):
    """Affiche l'aide"""
    logger.info(f"📚 Commande !aide utilisée par {ctx.author}")
    
    embed = discord.Embed(
        title="📚 Aide - Bot Photo de Profil Pinterest",
        description="Voici comment utiliser le bot:",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="!pdp",
        value="🎨 Lance la recherche interactive",
        inline=False
    )
    embed.add_field(
        name="!recherche <mots-clés>",
        value="🔍 Recherche rapide directe",
        inline=False
    )
    embed.add_field(
        name="!categories",
        value="📋 Affiche toutes les catégories",
        inline=False
    )
    embed.add_field(
        name="⚠️ Note",
        value="Ce bot utilise Pinterest. Les résultats peuvent parfois être limités.",
        inline=False
    )
    
    await ctx.send(embed=embed)

# 🚀 LANCEMENT DU BOT ET DU SERVEUR WEB (CORRIGÉ)
if __name__ == '__main__':
    if not DISCORD_TOKEN:
        logger.error("❌ ERREUR CRITIQUE: DISCORD_TOKEN manquant dans les variables d'environnement !")
    else:
        logger.info("🚀 Démarrage du bot Pinterest avec logging amélioré...")
        
        # 1. Lancer le serveur web simple (non Gunicorn) dans un thread séparé.
        # Ceci satisfait l'exigence de Render d'ouvrir un port web.
        Thread(target=run_flask, daemon=True).start()
        
        # 2. Lancer le bot Discord dans le thread principal.
        # Ceci évite le crash 'ValueError: signal' car le bot est désormais le processus principal.
        try:
            bot.run(DISCORD_TOKEN)
        except Exception as e:
            logger.critical(f"❌ ERREUR LORS DU LANCEMENT DE DISCORD: {e}")
            sys.exit(1)
