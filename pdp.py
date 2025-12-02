import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import os
from typing import Optional

# ==============================================================================
# ⚙️ CONFIGURATION
# ==============================================================================

# URL de votre API backend
API_URL = "https://pfpbot-8e9l.onrender.com"
API_KEY = "Nono1912"

# ==============================================================================
# 🤖 INITIALISATION DU BOT
# ==============================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ==============================================================================
# 📊 FONCTIONS UTILITAIRES
# ==============================================================================

async def get_api_stats():
    """Récupère les statistiques depuis l'API."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/api/stats",
                headers={"X-API-Key": API_KEY}
            ) as response:
                if response.status == 200:
                    return await response.json()
                return None
    except Exception as e:
        print(f"Erreur API stats: {e}")
        return None

async def get_random_photos(category: str, count: int):
    """Récupère des photos aléatoires depuis l'API."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/api/photos/random?category={category}&count={count}",
                headers={"X-API-Key": API_KEY}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("photos", [])
                return None
    except Exception as e:
        print(f"Erreur API photos: {e}")
        return None

# ==============================================================================
# 🔔 ÉVÉNEMENTS
# ==============================================================================

@bot.event
async def on_ready():
    """Événement déclenché quand le bot est prêt."""
    print(f"✅ Bot connecté : {bot.user.name} (ID: {bot.user.id})")
    print(f"📊 Connecté sur {len(bot.guilds)} serveur(s)")
    
    # Synchroniser les slash commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur sync: {e}")

# ==============================================================================
# 📜 COMMANDES
# ==============================================================================

@bot.command(name="help")
async def cmd_help(ctx):
    """Affiche le menu d'aide."""
    embed = discord.Embed(
        title="🎨 Bot PDP - Menu d'aide",
        description="Voici toutes les commandes disponibles :",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📸 !pdp <catégorie> <nombre>",
        value="Envoie des photos de profil aléatoires\n"
              "Catégories : `boy`, `girl`, `anime`, `aesthetic`, `cute`, `banner`, `match`\n"
              "Exemple : `!pdp boy 5`",
        inline=False
    )
    
    embed.add_field(
        name="📊 !stock",
        value="Affiche le nombre de photos disponibles par catégorie",
        inline=False
    )
    
    embed.add_field(
        name="❓ !help",
        value="Affiche ce menu d'aide",
        inline=False
    )
    
    embed.set_footer(text="Bot créé avec ❤️ | Mode Noël 🎄")
    embed.timestamp = discord.utils.utcnow()
    
    await ctx.send(embed=embed)

@bot.command(name="stock")
async def cmd_stock(ctx):
    """Affiche le stock de photos par catégorie."""
    # Message de chargement
    loading_msg = await ctx.send("⏳ Chargement des statistiques...")
    
    # Récupération des stats
    stats = await get_api_stats()
    
    if not stats:
        await loading_msg.edit(content="❌ Impossible de récupérer les statistiques. L'API ne répond pas.")
        return
    
    # Création de l'embed
    embed = discord.Embed(
        title="📊 Stock de Photos Disponibles",
        description=f"**Total : {stats.get('total_photos', 0):,} photos**",
        color=discord.Color.green()
    )
    
    # Mapping des catégories avec emojis
    category_emojis = {
        "boy": "👦",
        "girl": "👧",
        "anime": "🎌",
        "aesthetic": "✨",
        "cute": "🥰",
        "banner": "🎨",
        "match": "💕"
    }
    
    # Ajout des catégories
    categories = stats.get("categories", [])
    if categories:
        for cat_data in categories:
            category = cat_data.get("category", "inconnu")
            count = cat_data.get("count", 0)
            emoji = category_emojis.get(category, "📷")
            
            embed.add_field(
                name=f"{emoji} {category.capitalize()}",
                value=f"**{count:,}** photos",
                inline=True
            )
    else:
        embed.add_field(
            name="⚠️ Aucune donnée",
            value="Le stock est vide ou l'API n'a pas retourné de catégories.",
            inline=False
        )
    
    # Infos supplémentaires
    embed.add_field(
        name="📤 Imports ce mois",
        value=f"**{stats.get('recent_imports', 0)}** imports",
        inline=True
    )
    
    embed.add_field(
        name="📁 Sur Discord",
        value=f"**{stats.get('available_photos', 0):,}** photos",
        inline=True
    )
    
    embed.set_footer(text="Utilisez !pdp <catégorie> <nombre> pour récupérer des photos")
    embed.timestamp = discord.utils.utcnow()
    
    await loading_msg.edit(content=None, embed=embed)

@bot.command(name="pdp")
async def cmd_pdp(ctx, category: str = None, count: int = 1):
    """Envoie des photos de profil aléatoires."""
    
    # Vérifications
    if not category:
        await ctx.send("❌ **Utilisation :** `!pdp <catégorie> <nombre>`\n"
                      "📚 **Catégories :** boy, girl, anime, aesthetic, cute, banner, match\n"
                      "💡 **Exemple :** `!pdp boy 5`")
        return
    
    valid_categories = ["boy", "girl", "anime", "aesthetic", "cute", "banner", "match"]
    if category.lower() not in valid_categories:
        await ctx.send(f"❌ Catégorie invalide : `{category}`\n"
                      f"📚 **Catégories disponibles :** {', '.join(valid_categories)}")
        return
    
    if count < 1 or count > 10:
        await ctx.send("❌ Le nombre doit être entre **1** et **10** photos.")
        return
    
    # Message de chargement
    loading_msg = await ctx.send(f"⏳ Recherche de **{count}** photo(s) dans la catégorie `{category}`...")
    
    # Récupération des photos
    photos = await get_random_photos(category.lower(), count)
    
    if not photos:
        await loading_msg.edit(content=f"❌ Aucune photo trouvée pour la catégorie `{category}` ou l'API ne répond pas.")
        return
    
    # Suppression du message de chargement
    await loading_msg.delete()
    
    # Envoi des photos
    category_emojis = {
        "boy": "👦",
        "girl": "👧",
        "anime": "🎌",
        "aesthetic": "✨",
        "cute": "🥰",
        "banner": "🎨",
        "match": "💕"
    }
    
    emoji = category_emojis.get(category.lower(), "📷")
    
    embed = discord.Embed(
        title=f"{emoji} Photos - {category.capitalize()}",
        description=f"Voici **{len(photos)}** photo(s) aléatoire(s) !",
        color=discord.Color.purple()
    )
    
    embed.set_footer(text=f"Demandé par {ctx.author.name}")
    embed.timestamp = discord.utils.utcnow()
    
    await ctx.send(embed=embed)
    
    # Envoi de chaque photo
    for i, photo in enumerate(photos, 1):
        try:
            embed_photo = discord.Embed(color=discord.Color.random())
            embed_photo.set_image(url=photo.get("url"))
            embed_photo.set_footer(text=f"Photo {i}/{len(photos)} • ID: {photo.get('id')}")
            await ctx.send(embed=embed_photo)
        except Exception as e:
            print(f"Erreur envoi photo {i}: {e}")
            await ctx.send(f"❌ Erreur lors de l'envoi de la photo {i}")

# ==============================================================================
# 🚀 SLASH COMMANDS (Commandes modernes Discord)
# ==============================================================================

@bot.tree.command(name="help", description="Affiche le menu d'aide")
async def slash_help(interaction: discord.Interaction):
    """Slash command pour l'aide."""
    embed = discord.Embed(
        title="🎨 Bot PDP - Menu d'aide",
        description="Voici toutes les commandes disponibles :",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="/pdp <catégorie> <nombre>",
        value="Envoie des photos de profil aléatoires",
        inline=False
    )
    
    embed.add_field(
        name="/stock",
        value="Affiche le nombre de photos disponibles par catégorie",
        inline=False
    )
    
    embed.set_footer(text="Bot PDP • Mode Noël 🎄")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stock", description="Affiche le stock de photos par catégorie")
async def slash_stock(interaction: discord.Interaction):
    """Slash command pour le stock."""
    await interaction.response.defer()
    
    stats = await get_api_stats()
    
    if not stats:
        await interaction.followup.send("❌ Impossible de récupérer les statistiques.")
        return
    
    embed = discord.Embed(
        title="📊 Stock de Photos",
        description=f"**Total : {stats.get('total_photos', 0):,} photos**",
        color=discord.Color.green()
    )
    
    category_emojis = {
        "boy": "👦", "girl": "👧", "anime": "🎌",
        "aesthetic": "✨", "cute": "🥰", "banner": "🎨", "match": "💕"
    }
    
    for cat_data in stats.get("categories", []):
        category = cat_data.get("category", "inconnu")
        count = cat_data.get("count", 0)
        emoji = category_emojis.get(category, "📷")
        embed.add_field(name=f"{emoji} {category.capitalize()}", value=f"**{count:,}** photos", inline=True)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="pdp", description="Récupère des photos de profil")
@app_commands.describe(
    category="Catégorie de photos (boy, girl, anime, etc.)",
    count="Nombre de photos (1-10)"
)
@app_commands.choices(category=[
    app_commands.Choice(name="👦 Boy", value="boy"),
    app_commands.Choice(name="👧 Girl", value="girl"),
    app_commands.Choice(name="🎌 Anime", value="anime"),
    app_commands.Choice(name="✨ Aesthetic", value="aesthetic"),
    app_commands.Choice(name="🥰 Cute", value="cute"),
    app_commands.Choice(name="🎨 Banner", value="banner"),
    app_commands.Choice(name="💕 Match", value="match"),
])
async def slash_pdp(interaction: discord.Interaction, category: str, count: int = 1):
    """Slash command pour récupérer des photos."""
    if count < 1 or count > 10:
        await interaction.response.send_message("❌ Le nombre doit être entre 1 et 10.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    photos = await get_random_photos(category, count)
    
    if not photos:
        await interaction.followup.send(f"❌ Aucune photo trouvée pour `{category}`.")
        return
    
    # Premier message avec info
    embed = discord.Embed(
        title=f"📷 {len(photos)} photo(s) - {category.capitalize()}",
        description="Chargement des images...",
        color=discord.Color.purple()
    )
    await interaction.followup.send(embed=embed)
    
    # Envoi des photos
    for photo in photos:
        try:
            embed_photo = discord.Embed(color=discord.Color.random())
            embed_photo.set_image(url=photo.get("url"))
            await interaction.channel.send(embed=embed_photo)
        except Exception as e:
            print(f"Erreur: {e}")

# ==============================================================================
# 🟢 DÉMARRAGE DU BOT
# ==============================================================================

if __name__ == "__main__":
    # Pour Render : Le token sera dans les variables d'environnement
    TOKEN = os.getenv("DISCORD_TOKEN")
    
    if not TOKEN:
        print("❌ ERREUR : Variable d'environnement DISCORD_TOKEN manquante !")
        print("📝 Sur Render : Ajoutez DISCORD_TOKEN dans Environment Variables")
        exit(1)
    
    print("🚀 Démarrage du bot sur Render...")
    print(f"🌐 API URL : {API_URL}")
    
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("❌ Token Discord invalide !")
        exit(1)
    except Exception as e:
        print(f"❌ Erreur critique : {e}")
        exit(1)
