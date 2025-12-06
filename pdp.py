import discord
from discord.ext import commands, tasks
import aiohttp
import os
import asyncio
import random
from aiohttp import web
import re

# ==============================================================================
# ⚙️ CONFIGURATION DOUBLE WEBHOOK
# ==============================================================================

# WEBHOOK 1 : Serveur privé pour UPLOAD (scraper Pinterest)
UPLOAD_WEBHOOK_URL = "https://discord.com/api/webhooks/1444170798222020690/7wp6evUDdI2rf2Y7Rgk3rPGcEAS9w86-Oynf2aINMgjoEMpSIqri-MQIgBYAhfoVmC-I"
UPLOAD_CHANNEL_ID = 1425082379768303649  # ID du salon privé

# WEBHOOK 2 : Serveur public pour DISTRIBUTION (bot envoie ici)
PUBLIC_WEBHOOK_URL = "https://discord.com/api/webhooks/1446667319148417138/NJMcPKmNNYek9jgVwZdawpq8WbcnNQjt1tjiD17YX_KuFOG71jIX9A6P542qEKlEn3gf"
PUBLIC_CHANNEL_ID = 1446667244036689963

# Choix : Surveiller quel webhook ?
MONITOR_MODE = "upload"  # ou "both"

# ==============================================================================
# 🤖 INITIALISATION DU BOT
# ==============================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Cache des images par catégorie
image_cache = {
    "boy": [],
    "girl": [],
    "anime": [],
    "aesthetic": [],
    "cute": [],
    "banner": [],
    "match": []
}

# Statistiques
stats = {
    "total_sent": 0,
    "requests_today": 0,
    "cache_refreshes": 0
}

# ==============================================================================
# 🌐 SERVEUR WEB POUR RENDER
# ==============================================================================

async def health_check(request):
    return web.Response(text="✅ Bot Discord PDP (Dual Webhook) en ligne !", status=200)

async def stats_endpoint(request):
    total_images = sum(len(imgs) for imgs in image_cache.values())
    return web.json_response({
        "status": "online",
        "bot": str(bot.user),
        "cached_images": total_images,
        "categories": {cat: len(imgs) for cat, imgs in image_cache.items()},
        "stats": stats,
        "latency": round(bot.latency * 1000, 2)
    })

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    app.router.add_get('/stats', stats_endpoint)
    
    port = int(os.getenv('PORT', 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Serveur web démarré sur le port {port}")

# ==============================================================================
# 📡 GESTION DOUBLE WEBHOOK - VERSION CORRIGÉE
# ==============================================================================

def detect_category(filename: str, content: str) -> str:
    """
    Détecte la catégorie depuis le nom ou contenu.
    VERSION AMÉLIORÉE avec patterns flexibles et catégorie par défaut.
    """
    text = (filename + " " + content).lower()
    
    # Patterns de détection plus flexibles
    patterns = {
        "boy": [r'\bboy\b', r'\bgarcon\b', r'\bboys\b', r'\bmale\b', r'\bman\b', r'\bhomme\b'],
        "girl": [r'\bgirl\b', r'\bfille\b', r'\bgirls\b', r'\bfemale\b', r'\bwoman\b', r'\bfemme\b'],
        "anime": [r'\banime\b', r'\bmanga\b', r'\botaku\b', r'\banimé\b'],
        "aesthetic": [r'\baesthetic\b', r'\baesthetics\b', r'\besthetique\b', r'\bvibe\b'],
        "cute": [r'\bcute\b', r'\bkawaii\b', r'\bmignon\b', r'\badorable\b'],
        "banner": [r'\bbanner\b', r'\bheader\b', r'\bcover\b', r'\bbanniere\b'],
        "match": [r'\bmatch\b', r'\bmatching\b', r'\bcouple\b', r'\bpair\b']
    }
    
    # Cherche dans les patterns
    for category, pattern_list in patterns.items():
        for pattern in pattern_list:
            if re.search(pattern, text):
                print(f"   ✓ Catégorie détectée: {category} (pattern: {pattern})")
                return category
    
    # NOUVEAU : Si aucune catégorie détectée, assigne à "aesthetic" par défaut
    print(f"   ⚠️ Aucune catégorie détectée pour: {filename}, assigné à 'aesthetic'")
    return "aesthetic"  # Catégorie par défaut au lieu de None

async def load_images_from_webhook(webhook_url: str, source_name: str):
    """Charge les images depuis un webhook spécifique - VERSION CORRIGÉE."""
    try:
        # Extraction sécurisée des IDs
        match = re.search(r'/webhooks/(\d+)/([A-Za-z0-9_-]+)', webhook_url)
        if not match:
            print(f"❌ URL webhook invalide pour {source_name}")
            return 0
        
        webhook_id = match.group(1)
        webhook_token = match.group(2)
        
        print(f"📡 Connexion au webhook {source_name} (ID: {webhook_id[:10]}...)")
        
        async with aiohttp.ClientSession() as session:
            api_url = f"https://discord.com/api/v10/webhooks/{webhook_id}/{webhook_token}/messages"
            
            # Charge PLUS de messages (jusqu'à 100)
            async with session.get(api_url, params={'limit': 100}) as response:
                if response.status == 200:
                    messages = await response.json()
                    loaded_count = 0
                    
                    print(f"   📥 {len(messages)} messages trouvés")
                    
                    for msg in messages:
                        if msg.get('attachments'):
                            for attachment in msg['attachments']:
                                url = attachment.get('url')
                                filename = attachment.get('filename', '')
                                content_type = attachment.get('content_type', '')
                                
                                # Vérifie que c'est une image
                                if 'image' not in content_type:
                                    continue
                                
                                print(f"   🖼️ Fichier trouvé: {filename}")
                                
                                category = detect_category(filename, msg.get('content', ''))
                                
                                if category and url:
                                    # Vérifie les doublons
                                    if not any(img['url'] == url for img in image_cache[category]):
                                        image_cache[category].append({
                                            'url': url,
                                            'filename': filename,
                                            'id': attachment.get('id'),
                                            'source': source_name
                                        })
                                        loaded_count += 1
                                        print(f"   ✅ Ajouté à {category}")
                    
                    print(f"✅ {loaded_count} images chargées depuis {source_name}")
                    return loaded_count
                else:
                    error_text = await response.text()
                    print(f"⚠️ Erreur webhook {source_name}: {response.status}")
                    print(f"   Détails: {error_text[:200]}")
                    return 0
                    
    except Exception as e:
        print(f"❌ Erreur load {source_name}: {e}")
        import traceback
        traceback.print_exc()
        return 0

async def load_all_images():
    """Charge les images depuis les webhooks configurés."""
    print("\n" + "="*60)
    print("🔄 CHARGEMENT DES IMAGES")
    print("="*60)
    
    total = 0
    
    # Webhook d'upload (obligatoire)
    print(f"📡 Source 1: Webhook UPLOAD")
    count1 = await load_images_from_webhook(UPLOAD_WEBHOOK_URL, "upload")
    total += count1
    
    # Webhook public (optionnel si MONITOR_MODE = "both")
    if MONITOR_MODE == "both" and "TON_WEBHOOK_PUBLIC_ICI" not in PUBLIC_WEBHOOK_URL:
        print(f"\n📡 Source 2: Webhook PUBLIC")
        count2 = await load_images_from_webhook(PUBLIC_WEBHOOK_URL, "public")
        total += count2
    
    stats["cache_refreshes"] += 1
    
    print("\n" + "="*60)
    print(f"✅ TOTAL : {total} images chargées")
    print("="*60)
    
    for cat, imgs in image_cache.items():
        if imgs:
            print(f"   📂 {cat.upper()}: {len(imgs)} images")
    
    if total == 0:
        print("\n⚠️ ATTENTION : Aucune image chargée !")
        print("   Vérifiez que :")
        print("   1. Le webhook contient des messages avec des images")
        print("   2. Les noms de fichiers contiennent les catégories (boy, girl, etc.)")
        print("   3. Les URLs des webhooks sont corrects")
    
    print("="*60 + "\n")

# ==============================================================================
# 🔄 TÂCHE AUTOMATIQUE - Refresh cache
# ==============================================================================

@tasks.loop(hours=1)
async def auto_refresh_cache():
    """Recharge le cache toutes les heures."""
    print("🔄 Refresh automatique du cache...")
    
    # Vide le cache
    for cat in image_cache:
        image_cache[cat] = []
    
    await load_all_images()

# ==============================================================================
# 🔔 ÉVÉNEMENTS
# ==============================================================================

@bot.event
async def on_ready():
    print("\n" + "="*60)
    print(f"✅ BOT CONNECTÉ : {bot.user.name} (ID: {bot.user.id})")
    print(f"📊 Serveurs : {len(bot.guilds)}")
    print("="*60 + "\n")
    
    asyncio.create_task(start_web_server())
    
    # Charge les images
    await load_all_images()
    
    # Démarre le refresh automatique
    auto_refresh_cache.start()
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="!help | Dual Webhook 🎄"
        )
    )
    
    print(f"✅ Bot prêt à répondre aux commandes !\n")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        await bot.process_commands(message)
        return
    
    # Surveille le webhook d'upload
    if message.channel.id == UPLOAD_CHANNEL_ID and message.attachments:
        print(f"📥 Nouveau message détecté sur webhook UPLOAD")
        for attachment in message.attachments:
            if attachment.content_type and 'image' in attachment.content_type:
                url = attachment.url
                filename = attachment.filename
                category = detect_category(filename, message.content)
                
                if category:
                    # Évite les doublons
                    if not any(img['url'] == url for img in image_cache[category]):
                        image_cache[category].append({
                            'url': url,
                            'filename': filename,
                            'id': attachment.id,
                            'source': 'upload'
                        })
                        print(f"➕ Image ajoutée en temps réel : {category} ({filename})")
    
    # Surveille le webhook public si activé
    if MONITOR_MODE == "both" and message.channel.id == PUBLIC_CHANNEL_ID and message.attachments:
        print(f"📥 Nouveau message détecté sur webhook PUBLIC")
        for attachment in message.attachments:
            if attachment.content_type and 'image' in attachment.content_type:
                url = attachment.url
                filename = attachment.filename
                category = detect_category(filename, message.content)
                
                if category:
                    if not any(img['url'] == url for img in image_cache[category]):
                        image_cache[category].append({
                            'url': url,
                            'filename': filename,
                            'id': attachment.id,
                            'source': 'public'
                        })
                        print(f"➕ Image ajoutée en temps réel (public) : {category}")
    
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Commande inconnue. Utilisez `!help`")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant. Utilisez `!help`")
    else:
        print(f"Erreur commande: {error}")

# ==============================================================================
# 📜 COMMANDES
# ==============================================================================

@bot.command(name="help", aliases=["aide", "h"])
async def cmd_help(ctx):
    embed = discord.Embed(
        title="🎨 Bot PDP - Double Webhook",
        description="Bot avec système de double webhook (upload privé + distribution publique)",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📸 !pdp <catégorie> [nombre]",
        value="Envoie des photos depuis le cache\n"
              "**Catégories :** `boy`, `girl`, `anime`, `aesthetic`, `cute`, `banner`, `match`\n"
              "**Exemple :** `!pdp boy 5`",
        inline=False
    )
    
    embed.add_field(
        name="📊 !stock",
        value="Affiche le stock d'images en cache",
        inline=False
    )
    
    embed.add_field(
        name="🔄 !refresh",
        value="Recharge le cache depuis les webhooks (admin)",
        inline=False
    )
    
    embed.add_field(
        name="📈 !stats",
        value="Statistiques du bot",
        inline=False
    )
    
    embed.add_field(
        name="🔍 !debug",
        value="Affiche les derniers messages du webhook (admin)",
        inline=False
    )
    
    embed.set_footer(text="Double Webhook System 🎄")
    embed.timestamp = discord.utils.utcnow()
    
    await ctx.send(embed=embed)

@bot.command(name="debug", aliases=["test"])
@commands.has_permissions(administrator=True)
async def cmd_debug(ctx):
    """Commande de debug pour voir ce qui se passe."""
    embed = discord.Embed(
        title="🔍 Debug Info",
        color=discord.Color.orange()
    )
    
    # Info sur le cache
    total = sum(len(imgs) for imgs in image_cache.values())
    embed.add_field(name="📦 Images en cache", value=str(total), inline=False)
    
    for cat, imgs in image_cache.items():
        if imgs:
            # Affiche les 3 premiers fichiers
            sample = imgs[:3]
            filenames = "\n".join([f"- {img['filename']}" for img in sample])
            embed.add_field(
                name=f"📂 {cat} ({len(imgs)})",
                value=filenames or "Aucun",
                inline=False
            )
    
    # Tente de charger 1 message
    try:
        match = re.search(r'/webhooks/(\d+)/([A-Za-z0-9_-]+)', UPLOAD_WEBHOOK_URL)
        if match:
            webhook_id = match.group(1)
            webhook_token = match.group(2)
            
            async with aiohttp.ClientSession() as session:
                api_url = f"https://discord.com/api/v10/webhooks/{webhook_id}/{webhook_token}/messages"
                async with session.get(api_url, params={'limit': 5}) as response:
                    if response.status == 200:
                        messages = await response.json()
                        embed.add_field(
                            name="✅ Test webhook",
                            value=f"{len(messages)} messages trouvés",
                            inline=False
                        )
                        
                        # Affiche le premier message
                        if messages:
                            msg = messages[0]
                            attachments = msg.get('attachments', [])
                            embed.add_field(
                                name="📝 Premier message",
                                value=f"Attachments: {len(attachments)}\n"
                                      f"Content: {msg.get('content', 'Vide')[:50]}",
                                inline=False
                            )
                    else:
                        embed.add_field(
                            name="❌ Test webhook",
                            value=f"Erreur {response.status}",
                            inline=False
                        )
    except Exception as e:
        embed.add_field(name="❌ Erreur test", value=str(e)[:100], inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="stock", aliases=["s"])
async def cmd_stock(ctx):
    total = sum(len(imgs) for imgs in image_cache.values())
    
    embed = discord.Embed(
        title="📊 Stock d'Images",
        description=f"**Total : {total} images en cache**\n"
                   f"*Mode : {MONITOR_MODE}*",
        color=discord.Color.green() if total > 0 else discord.Color.red()
    )
    
    category_emojis = {
        "boy": "👦",
        "girl": "👧",
        "anime": "🎌",
        "aesthetic": "✨",
        "cute": "🥰",
        "banner": "🎨",
        "match": "💕"
    }
    
    for category, emoji in category_emojis.items():
        count = len(image_cache[category])
        if count > 0:
            upload_count = sum(1 for img in image_cache[category] if img.get('source') == 'upload')
            public_count = sum(1 for img in image_cache[category] if img.get('source') == 'public')
            
            value = f"**{count}** images"
            if MONITOR_MODE == "both":
                value += f"\n└ Upload: {upload_count} | Public: {public_count}"
            
            embed.add_field(
                name=f"{emoji} {category.capitalize()}",
                value=value,
                inline=True
            )
    
    if total == 0:
        embed.add_field(
            name="⚠️ Cache vide",
            value="Utilisez `!refresh` ou `!debug` pour diagnostiquer",
            inline=False
        )
    
    embed.set_footer(text=f"Refresh: {stats['cache_refreshes']} fois • Envoyé: {stats['total_sent']} images")
    
    await ctx.send(embed=embed)

@bot.command(name="stats")
async def cmd_stats(ctx):
    embed = discord.Embed(
        title="📈 Statistiques du Bot",
        color=discord.Color.gold()
    )
    
    embed.add_field(name="📦 Images en cache", value=f"{sum(len(imgs) for imgs in image_cache.values())}", inline=True)
    embed.add_field(name="📤 Images envoyées", value=f"{stats['total_sent']}", inline=True)
    embed.add_field(name="🔄 Refresh effectués", value=f"{stats['cache_refreshes']}", inline=True)
    embed.add_field(name="📊 Serveurs", value=f"{len(bot.guilds)}", inline=True)
    embed.add_field(name="⚡ Latence", value=f"{round(bot.latency * 1000, 2)}ms", inline=True)
    embed.add_field(name="🔧 Mode", value=f"{MONITOR_MODE}", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name="refresh", aliases=["reload"])
@commands.has_permissions(administrator=True)
async def cmd_refresh(ctx):
    msg = await ctx.send("🔄 Rechargement du cache...")
    
    for cat in image_cache:
        image_cache[cat] = []
    
    await load_all_images()
    
    total = sum(len(imgs) for imgs in image_cache.values())
    await msg.edit(content=f"✅ {total} images rechargées !")

@bot.command(name="pdp", aliases=["pfp", "photo", "p"])
async def cmd_pdp(ctx, category: str = None, count: int = 1):
    if not category:
        embed = discord.Embed(
            title="❌ Utilisation incorrecte",
            description="**Format :** `!pdp <catégorie> [nombre]`",
            color=discord.Color.red()
        )
        embed.add_field(
            name="📚 Catégories",
            value="`boy`, `girl`, `anime`, `aesthetic`, `cute`, `banner`, `match`",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    category = category.lower()
    if category not in image_cache:
        await ctx.send(f"❌ Catégorie invalide : `{category}`")
        return
    
    if count < 1 or count > 50:
        await ctx.send("❌ Le nombre doit être entre **1** et **50**.")
        return
    
    available = len(image_cache[category])
    if available == 0:
        await ctx.send(f"❌ Aucune image en cache pour `{category}`. Utilisez `!refresh` pour recharger.")
        return
    
    count = min(count, available)
    
    loading_msg = await ctx.send(f"⏳ Récupération de **{count}** image(s) `{category}`...")
    
    selected_images = random.sample(image_cache[category], count)
    
    await loading_msg.delete()
    
    category_emojis = {
        "boy": "👦",
        "girl": "👧",
        "anime": "🎌",
        "aesthetic": "✨",
        "cute": "🥰",
        "banner": "🎨",
        "match": "💕"
    }
    
    emoji = category_emojis.get(category, "📷")
    
    embed_intro = discord.Embed(
        title=f"{emoji} Photos - {category.capitalize()}",
        description=f"Voici **{count}** photo(s) !",
        color=discord.Color.purple()
    )
    embed_intro.set_footer(text=f"Demandé par {ctx.author.name}")
    
    await ctx.send(embed=embed_intro)
    
    # Envoie les images
    for i, img in enumerate(selected_images, 1):
        try:
            await ctx.send(img['url'])
            stats["total_sent"] += 1
            
            if i < count:
                await asyncio.sleep(1.2)
                
        except discord.errors.HTTPException as e:
            if e.status == 429:
                print(f"⚠️ Rate limit atteint, pause...")
                await ctx.send(f"⚠️ Trop rapide ! Pause... ({i}/{count})")
                await asyncio.sleep(5)
                await ctx.send(img['url'])
            else:
                print(f"Erreur HTTP envoi photo {i}: {e}")
        except Exception as e:
            print(f"Erreur envoi photo {i}: {e}")

@bot.command(name="ping", hidden=True)
@commands.has_permissions(administrator=True)
async def cmd_ping(ctx):
    latency = round(bot.latency * 1000, 2)
    embed = discord.Embed(
        title="🏓 Pong !",
        description=f"Latence : **{latency}ms**",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

# ==============================================================================
# 🟢 DÉMARRAGE
# ==============================================================================

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    
    if not TOKEN:
        print("❌ ERREUR : DISCORD_TOKEN manquant !")
        exit(1)
    
    print("="*60)
    print("🚀 DÉMARRAGE DU BOT (DUAL WEBHOOK SYSTEM)")
    print("="*60)
    print(f"📡 Webhook UPLOAD surveillé : {UPLOAD_CHANNEL_ID}")
    if MONITOR_MODE == "both":
        print(f"📡 Webhook PUBLIC surveillé : {PUBLIC_CHANNEL_ID}")
    print("="*60 + "\n")
    
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Erreur : {e}")
        import traceback
        traceback.print_exc()
        exit(1)
