import discord
from discord.ext import commands
import os

# ==============================================================================
# 🤖 INITIALISATION DU BOT
# ==============================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ==============================================================================
# 🔔 ÉVÉNEMENTS
# ==============================================================================

@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user.name}")
    print(f"📊 Serveurs : {len(bot.guilds)}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="!lock | !unlock 🔒"
        )
    )

# ==============================================================================
# 📜 COMMANDES
# ==============================================================================

@bot.command(name="lock", aliases=["verrouiller", "fermer"])
@commands.has_permissions(manage_channels=True)
async def cmd_lock(ctx, channel: discord.TextChannel = None):
    """
    Verrouille un salon (empêche @everyone d'écrire).
    Usage: !lock [#salon]
    Si aucun salon n'est spécifié, verrouille le salon actuel.
    """
    # Si aucun salon spécifié, utilise le salon actuel
    if channel is None:
        channel = ctx.channel
    
    # Vérifie si le salon est déjà verrouillé
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    if overwrite.send_messages == False:
        await ctx.send(f"🔒 {channel.mention} est déjà verrouillé.")
        return
    
    try:
        # Empêche @everyone d'envoyer des messages
        await channel.set_permissions(
            ctx.guild.default_role,
            send_messages=False,
            add_reactions=False,
            create_public_threads=False,
            create_private_threads=False,
            send_messages_in_threads=False,
            reason=f"Salon verrouillé par {ctx.author}"
        )
        
        embed = discord.Embed(
            title="🔒 Salon Verrouillé",
            description=f"{channel.mention} a été verrouillé.\n"
                       f"Seuls les modérateurs peuvent écrire.",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Verrouillé par {ctx.author.name}")
        
        await ctx.send(embed=embed)
        
    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions nécessaires pour verrouiller ce salon.")
    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")

@bot.command(name="unlock", aliases=["deverrouiller", "ouvrir"])
@commands.has_permissions(manage_channels=True)
async def cmd_unlock(ctx, channel: discord.TextChannel = None):
    """
    Déverrouille un salon (autorise @everyone à écrire).
    Usage: !unlock [#salon]
    Si aucun salon n'est spécifié, déverrouille le salon actuel.
    """
    # Si aucun salon spécifié, utilise le salon actuel
    if channel is None:
        channel = ctx.channel
    
    # Vérifie si le salon est déjà déverrouillé
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    if overwrite.send_messages != False:
        await ctx.send(f"🔓 {channel.mention} est déjà déverrouillé.")
        return
    
    try:
        # Autorise @everyone à envoyer des messages
        await channel.set_permissions(
            ctx.guild.default_role,
            send_messages=True,
            add_reactions=True,
            create_public_threads=True,
            create_private_threads=True,
            send_messages_in_threads=True,
            reason=f"Salon déverrouillé par {ctx.author}"
        )
        
        embed = discord.Embed(
            title="🔓 Salon Déverrouillé",
            description=f"{channel.mention} a été déverrouillé.\n"
                       f"Tout le monde peut à nouveau écrire.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Déverrouillé par {ctx.author.name}")
        
        await ctx.send(embed=embed)
        
    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas les permissions nécessaires pour déverrouiller ce salon.")
    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")

@bot.command(name="lockall", aliases=["verrouillertout"])
@commands.has_permissions(administrator=True)
async def cmd_lockall(ctx):
    """
    Verrouille TOUS les salons textuels du serveur.
    ⚠️ Réservé aux administrateurs.
    """
    # Demande confirmation
    confirm_msg = await ctx.send("⚠️ Êtes-vous sûr de vouloir verrouiller **TOUS** les salons ?\n"
                                 "Réagissez avec ✅ pour confirmer (30 secondes).")
    await confirm_msg.add_reaction("✅")
    
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id
    
    try:
        await bot.wait_for('reaction_add', timeout=30.0, check=check)
    except:
        await ctx.send("❌ Commande annulée (pas de confirmation).")
        return
    
    # Verrouille tous les salons
    locked_count = 0
    msg = await ctx.send("🔄 Verrouillage en cours...")
    
    for channel in ctx.guild.text_channels:
        try:
            await channel.set_permissions(
                ctx.guild.default_role,
                send_messages=False,
                add_reactions=False,
                create_public_threads=False,
                create_private_threads=False,
                send_messages_in_threads=False,
                reason=f"Verrouillage massif par {ctx.author}"
            )
            locked_count += 1
        except:
            pass
    
    embed = discord.Embed(
        title="🔒 Verrouillage Massif",
        description=f"**{locked_count}** salons ont été verrouillés.",
        color=discord.Color.red()
    )
    embed.set_footer(text=f"Par {ctx.author.name}")
    
    await msg.edit(content=None, embed=embed)

@bot.command(name="unlockall", aliases=["deverrouillertout"])
@commands.has_permissions(administrator=True)
async def cmd_unlockall(ctx):
    """
    Déverrouille TOUS les salons textuels du serveur.
    ⚠️ Réservé aux administrateurs.
    """
    # Demande confirmation
    confirm_msg = await ctx.send("⚠️ Êtes-vous sûr de vouloir déverrouiller **TOUS** les salons ?\n"
                                 "Réagissez avec ✅ pour confirmer (30 secondes).")
    await confirm_msg.add_reaction("✅")
    
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id
    
    try:
        await bot.wait_for('reaction_add', timeout=30.0, check=check)
    except:
        await ctx.send("❌ Commande annulée (pas de confirmation).")
        return
    
    # Déverrouille tous les salons
    unlocked_count = 0
    msg = await ctx.send("🔄 Déverrouillage en cours...")
    
    for channel in ctx.guild.text_channels:
        try:
            await channel.set_permissions(
                ctx.guild.default_role,
                send_messages=True,
                add_reactions=True,
                create_public_threads=True,
                create_private_threads=True,
                send_messages_in_threads=True,
                reason=f"Déverrouillage massif par {ctx.author}"
            )
            unlocked_count += 1
        except:
            pass
    
    embed = discord.Embed(
        title="🔓 Déverrouillage Massif",
        description=f"**{unlocked_count}** salons ont été déverrouillés.",
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Par {ctx.author.name}")
    
    await msg.edit(content=None, embed=embed)

@bot.command(name="help", aliases=["aide"])
async def cmd_help(ctx):
    """Affiche l'aide."""
    embed = discord.Embed(
        title="🔒 Bot Lock/Unlock - Commandes",
        description="Gestion du verrouillage des salons",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="🔒 !lock [#salon]",
        value="Verrouille un salon (empêche @everyone d'écrire)\n"
              "Si aucun salon n'est mentionné, verrouille le salon actuel.",
        inline=False
    )
    
    embed.add_field(
        name="🔓 !unlock [#salon]",
        value="Déverrouille un salon (autorise @everyone à écrire)\n"
              "Si aucun salon n'est mentionné, déverrouille le salon actuel.",
        inline=False
    )
    
    embed.add_field(
        name="🔒 !lockall",
        value="Verrouille TOUS les salons du serveur (admin uniquement)\n"
              "⚠️ Demande confirmation",
        inline=False
    )
    
    embed.add_field(
        name="🔓 !unlockall",
        value="Déverrouille TOUS les salons du serveur (admin uniquement)\n"
              "⚠️ Demande confirmation",
        inline=False
    )
    
    embed.set_footer(text="💡 Vous devez avoir la permission 'Gérer les salons' pour utiliser ces commandes")
    
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    """Gestion des erreurs."""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Vous n'avez pas les permissions nécessaires pour utiliser cette commande.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignore les commandes inconnues
    else:
        print(f"Erreur : {error}")

# ==============================================================================
# 🟢 DÉMARRAGE
# ==============================================================================

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    
    if not TOKEN:
        print("❌ ERREUR : DISCORD_TOKEN manquant !")
        exit(1)
    
    print("="*60)
    print("🚀 DÉMARRAGE DU BOT LOCK/UNLOCK")
    print("="*60)
    print("Commandes disponibles :")
    print("  - !lock [#salon]    : Verrouille un salon")
    print("  - !unlock [#salon]  : Déverrouille un salon")
    print("  - !lockall          : Verrouille tous les salons")
    print("  - !unlockall        : Déverrouille tous les salons")
    print("="*60 + "\n")
    
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Erreur : {e}")
        exit(1)
