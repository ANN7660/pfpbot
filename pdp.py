import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Select, SelectOption 
from datetime import datetime, timedelta
import asyncio
import re
from typing import Optional, Dict, Any
import os # Ajout pour la gestion du token (meilleure pratique)

# ==============================================================================
# ⚠️ Configuration et Variables Globales
# ==============================================================================

# Variable pour simuler votre base de données de configuration
config: Dict[int, Dict[str, Any]] = {}
CHRISTMAS_MODE = False # Mettez à True pour activer le mode Noël

# ==============================================================================
# 🛠️ Fonctions Utilitaires (Implémentations Simples pour l'Exemple)
# ==============================================================================

def get_gcfg(guild_id: int) -> Dict[str, Any]:
    """Simule la récupération de la configuration d'une guilde."""
    return config.setdefault(guild_id, {
        "openTickets": {},
        "roleReacts": {},
        "statsChannels": [],
        "ticketRoles": [],
        "ticketCategory": None,
        "logChannel": None,
        "tempVocChannels": []
    })

def save_config(cfg: Dict[int, Dict[str, Any]]):
    """Simule la sauvegarde de la configuration globale."""
    pass

async def send_log(guild: discord.Guild, embed: discord.Embed):
    """Simule l'envoi d'un journal de bord."""
    gcfg = get_gcfg(guild.id)
    log_ch_id = gcfg.get("logChannel")
    if log_ch_id:
        try:
            channel = guild.get_channel(int(log_ch_id))
            if channel:
                await channel.send(embed=embed)
        except Exception:
            pass

def _noel_title(text: str) -> str:
    """Ajoute un préfixe de Noël au titre si le mode est activé."""
    return f"🎄 {text}" if CHRISTMAS_MODE else text

def _noel_channel_prefix(text: str) -> str:
    """Ajoute un préfixe de Noël au nom de salon."""
    return f"❄️ {text}" if CHRISTMAS_MODE else text

def parse_duration(duration: str) -> Optional[int]:
    """Analyse une durée (ex: 10m, 1h) et retourne les secondes."""
    duration = duration.lower()
    match = re.fullmatch(r"(\d+)([smhd])", duration)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    
    if unit == 's':
        return amount
    elif unit == 'm':
        return amount * 60
    elif unit == 'h':
        return amount * 60 * 60
    elif unit == 'd':
        return amount * 60 * 60 * 24
    return None

# ==============================================================================
# 🤖 Définition du Bot
# ==============================================================================

intents = discord.Intents.default()
intents.message_content = True  
intents.members = True          
intents.presences = True        

# Initialisation du client Bot
bot = commands.Bot(command_prefix='!', intents=intents)

# ==============================================================================
# 🖼️ Définition des Vues (Views/Interactions)
# ==============================================================================

class HelpView(View):
    def __init__(self):
        super().__init__(timeout=None)

class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        # 🟢 CORRECTION: Utilise discord.ButtonStyle
        self.add_item(Button(label=_noel_title("Créer un Ticket"), custom_id="create_ticket", style=discord.ButtonStyle.primary, emoji="🎫"))

    @discord.ui.button(custom_id="create_ticket")
    async def create_ticket(self, button: Button, interaction: discord.Interaction):
        await interaction.response.send_message("Fonctionnalité de création de ticket non implémentée.", ephemeral=True)
        # TODO: Implémentez ici la logique de création de salon de ticket

class AdminTicketView(View):
    # La logique interne pour la sélection et les boutons est préservée
    def __init__(self, gcfg, author_id):
        super().__init__(timeout=120)
        self.gcfg = gcfg
        self.author_id = author_id
        self.selected_channel: Optional[str] = None

        options = []
        for ch_id, info in (gcfg.get("openTickets") or {}).items():
            owner_id = info.get("owner")
            created_ts = info.get("created")
            label_time = datetime.utcfromtimestamp(created_ts).strftime('%Y-%m-%d %H:%M') if created_ts else "inconnu"
            label = f"#{ch_id} • {label_time}"
            desc = f"Owner: <@{owner_id}>" if owner_id else "Owner: inconnu"
            options.append(SelectOption(label=label[:100], value=str(ch_id), description=desc[:100]))
        if not options:
            options = [SelectOption(label="Aucun ticket ouvert", value="none", description="Il n'y a pas de tickets ouverts.")]

        self.select = Select(placeholder="Sélectionnez un ticket", min_values=1, max_values=1, options=options, custom_id="admin_ticket_select")
        self.select.callback = self.select_callback
        self.add_item(self.select)
    
    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'auteur peut utiliser ce panneau.", ephemeral=True)
            return
        self.selected_channel = self.select.values[0]
        await interaction.response.send_message(f"✅ Ticket sélectionné: {self.selected_channel}", ephemeral=True)
        
    # 🟢 CORRECTION: Utilise discord.ButtonStyle
    @discord.ui.button(label="❌ Fermer le Ticket Sélectionné", style=discord.ButtonStyle.danger, custom_id="admin_close_selected")
    async def close_selected(self, button: Button, interaction: discord.Interaction):
        await interaction.response.send_message("Fermeture non implémentée.", ephemeral=True)

    # 🟢 CORRECTION: Utilise discord.ButtonStyle
    @discord.ui.button(label="🧹 Fermer Tous les Tickets", style=discord.ButtonStyle.secondary, custom_id="admin_close_all")
    async def close_all(self, button: Button, interaction: discord.Interaction):
        await interaction.response.send_message("Fermeture de tous les tickets non implémentée.", ephemeral=True)

    # 🟢 CORRECTION: Utilise discord.ButtonStyle
    @discord.ui.button(label="🔄 Rafraîchir", style=discord.ButtonStyle.primary, custom_id="admin_refresh")
    async def refresh(self, button: Button, interaction: discord.Interaction):
        await interaction.response.send_message("Rafraîchissement non implémenté.", ephemeral=True)

# ==============================================================================
# ⚙️ Tâches en Arrière-plan
# ==============================================================================

@tasks.loop(minutes=1)
async def stats_updater_loop():
    """Mets à jour les salons de statistiques toutes les minutes."""
    for guild in bot.guilds:
        gcfg = get_gcfg(guild.id)
        chan_ids = gcfg.get("statsChannels") or []
        
        if len(chan_ids) < 4: continue
        
        # Récupération des statistiques
        members = guild.member_count
        bots = len([m for m in guild.members if m.bot])
        in_voice = len([m for m in guild.members if m.voice and m.voice.channel])
        total_channels = len(guild.channels)
        
        stats = [
            (chan_ids[0], "Membres", members, "👥"),
            (chan_ids[1], "Bots", bots, "🤖"),
            (chan_ids[2], "En vocal", in_voice, "🔊"),
            (chan_ids[3], "Salons", total_channels, "📁"),
        ]

        for cid, label, count, emoji in stats:
            try:
                channel = guild.get_channel(int(cid))
                if channel:
                    prefix = f"🎄 {label}" if CHRISTMAS_MODE else f"{emoji} {label}"
                    new_name = f"{prefix} : {count}"
                    await channel.edit(name=new_name)
            except Exception:
                pass

# ==============================================================================
# 🔔 Événements (Events)
# ==============================================================================

@bot.event
async def on_ready():
    """S'exécute lorsque le bot est prêt."""
    print(f"✅ Bot connecté en tant que {bot.user} (id: {bot.user.id})")
    try:
        bot.add_view(HelpView())
        bot.add_view(TicketView())
    except Exception as e:
        print("Erreur add_view:", e)

    if not stats_updater_loop.is_running():
        stats_updater_loop.start()

@bot.event
async def on_interaction(interaction: discord.Interaction):
    """Gère les interactions, y compris la fermeture des tickets."""
    if interaction.type != discord.InteractionType.component:
        return
    cid = ""
    if interaction.data:
        cid = interaction.data.get("custom_id", "") or interaction.data.get("customId", "")

    if cid.startswith("close_ticket_"):
        await interaction.response.send_message("Fonctionnalité de fermeture non implémentée.", ephemeral=True)
    elif cid.startswith("confirm_close_"):
        await interaction.response.edit_message(content="🔒 Fermeture du ticket...", embed=None, view=None)
    elif cid == "cancel_close":
        await interaction.response.edit_message(content="✅ Fermeture annulée.", embed=None, view=None)
    
    await bot.process_application_commands(interaction)

@bot.event
async def on_member_join(member: discord.Member):
    pass # Logique de join ici

@bot.event
async def on_member_remove(member: discord.Member):
    pass # Logique de leave ici

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    pass # Logique de rôle réactif ici

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    pass # Logique de rôle réactif ici

@bot.event
async def on_voice_state_update(member, before, after):
    pass # Logique de vocaux temporaires ici

# ==============================================================================
# 📜 Commandes (Commands)
# ==============================================================================

def admin_required():
    async def predicate(ctx):
        return ctx.author.guild_permissions.administrator
    return commands.check(predicate)

@bot.command(name="help")
async def cmd_help(ctx):
    embed = discord.Embed(title=_noel_title("Menu d'aide du Bot"), description="Sélectionnez une catégorie pour voir les commandes", color=0x3498db)
    await ctx.reply(embed=embed, view=HelpView())

@bot.command(name="ticketpanel")
@admin_required()
async def cmd_ticketpanel(ctx):
    embed = discord.Embed(title=_noel_title("Support Tickets"), description="Cliquez ci-dessous pour créer un ticket de support.", color=0x3498db)
    view = TicketView()
    await ctx.send(embed=embed, view=view)
    try:
        await ctx.message.delete()
    except Exception:
        pass

@bot.command(name="ticketadmin")
@admin_required()
async def cmd_ticketadmin(ctx):
    gcfg = get_gcfg(ctx.guild.id)
    view = AdminTicketView(gcfg, ctx.author.id)
    embed = discord.Embed(title=_noel_title("Panneau Admin - Tickets"), color=0x95a5a6)
    
    # Affichage sommaire des tickets
    entries = gcfg.get("openTickets", {})
    embed.description = f"**Tickets ouverts:** {len(entries)}"
    
    await ctx.reply(embed=embed, view=view, ephemeral=False)

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def cmd_ban(ctx, member: discord.Member, *, reason: str = "Aucune raison fournie"):
    await ctx.reply(f"Ban de {member.mention} simulé.")

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def cmd_mute(ctx, member: discord.Member, duration: str, *, reason: str = "Aucune raison fournie"):
    secs = parse_duration(duration)
    if secs is None:
        return await ctx.reply("❌ Durée invalide. Utilisez: 10s, 5m, 1h, 1d")
    await ctx.reply(f"Mute de {member.mention} pour {duration} ({secs}s) simulé.")

# (Autres commandes de modération et de configuration se trouveraient ici)

@bot.command(name="config")
@admin_required()
async def cmd_config(ctx):
    await ctx.reply("Menu de configuration simulé.")

# ==============================================================================
# 🟢 Exécution du Bot
# ==============================================================================

if __name__ == '__main__':
    # ⚠️ CHARGEMENT DU TOKEN: Utilisez une variable d'environnement pour la sécurité
    try:
        from dotenv import load_dotenv
        load_dotenv()
        TOKEN = os.getenv('DISCORD_TOKEN')
    except ImportError:
        # Si python-dotenv n'est pas installé ou si la ligne est commentée
        TOKEN = "VOTRE_TOKEN_ICI" # Remplacer par votre token si dotenv n'est pas utilisé

    if TOKEN and TOKEN != "VOTRE_TOKEN_ICI":
        print("Démarrage du bot...")
        try:
            bot.run(TOKEN)
        except discord.errors.LoginFailure:
            print("\n\nERREUR: Le token du bot est invalide. Veuillez le vérifier.\n")
        except Exception as e:
            print(f"\n\nUne erreur inattendue s'est produite lors du démarrage: {e}\n")
    else:
        print("\n\nERREUR: Le token du bot n'a pas été chargé. Vérifiez votre fichier .env ou la variable TOKEN.\n")
