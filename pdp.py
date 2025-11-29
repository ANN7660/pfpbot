import discord
from discord.ext import commands
from discord import app_commands
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import random

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

# Intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Connexion à la base de données
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# Categories disponibles
CATEGORIES = {
    'anime': 'anime_pdp',
    'boy': 'boy_pdp',
    'girl': 'girl_pdp',
    'banner': 'banner',
    'aesthetic': 'aesthetic',
    'cute': 'cute_pdp'
}

@bot.event
async def on_ready():
    print(f'{bot.user} est connecté!')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Erreur sync: {e}")

@bot.tree.command(name="pdp", description="Obtenir une photo de profil aléatoire")
@app_commands.describe(category="Catégorie de l'image (anime, boy, girl, aesthetic, cute)")
async def pdp(interaction: discord.Interaction, category: str):
    await interaction.response.defer()
    
    category = category.lower()
    
    if category not in CATEGORIES:
        categories_list = ', '.join(CATEGORIES.keys())
        await interaction.followup.send(f"❌ Catégorie invalide! Catégories disponibles: {categories_list}")
        return
    
    db_category = CATEGORIES[category]
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Récupérer une image aléatoire en attente
        cursor.execute(
            "SELECT id, image_url, category FROM images WHERE category = %s AND status = 'pending' ORDER BY RANDOM() LIMIT 1",
            (db_category,)
        )
        
        image = cursor.fetchone()
        
        if not image:
            await interaction.followup.send(f"❌ Aucune image disponible dans la catégorie **{category}**!")
            cursor.close()
            conn.close()
            return
        
        # Marquer l'image comme envoyée (ou la supprimer)
        cursor.execute(
            "DELETE FROM images WHERE id = %s",
            (image['id'],)
        )
        conn.commit()
        
        # Compter les images restantes
        cursor.execute(
            "SELECT COUNT(*) as count FROM images WHERE category = %s AND status = 'pending'",
            (db_category,)
        )
        remaining = cursor.fetchone()['count']
        
        cursor.close()
        conn.close()
        
        # Créer l'embed
        embed = discord.Embed(
            title=f"📸 {category.capitalize()} PDP",
            description=f"Images restantes dans cette catégorie: **{remaining}**",
            color=discord.Color.purple()
        )
        embed.set_image(url=image['image_url'])
        embed.set_footer(text="Cette image ne sera plus jamais envoyée ✨")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        print(f"Erreur: {e}")
        await interaction.followup.send("❌ Une erreur est survenue!")

@bot.tree.command(name="banner", description="Obtenir un banner aléatoire")
async def banner(interaction: discord.Interaction):
    await interaction.response.defer()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, image_url FROM images WHERE category = 'banner' AND status = 'pending' ORDER BY RANDOM() LIMIT 1"
        )
        
        image = cursor.fetchone()
        
        if not image:
            await interaction.followup.send("❌ Aucun banner disponible!")
            cursor.close()
            conn.close()
            return
        
        cursor.execute("DELETE FROM images WHERE id = %s", (image['id'],))
        conn.commit()
        
        cursor.execute(
            "SELECT COUNT(*) as count FROM images WHERE category = 'banner' AND status = 'pending'"
        )
        remaining = cursor.fetchone()['count']
        
        cursor.close()
        conn.close()
        
        embed = discord.Embed(
            title="🖼️ Banner Discord",
            description=f"Banners restants: **{remaining}**",
            color=discord.Color.blue()
        )
        embed.set_image(url=image['image_url'])
        embed.set_footer(text="Cette image ne sera plus jamais envoyée ✨")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        print(f"Erreur: {e}")
        await interaction.followup.send("❌ Une erreur est survenue!")

@bot.tree.command(name="stock", description="Voir le nombre d'images disponibles par catégorie")
async def stock(interaction: discord.Interaction):
    await interaction.response.defer()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT category, COUNT(*) as count FROM images WHERE status = 'pending' GROUP BY category"
        )
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not results:
            await interaction.followup.send("❌ Aucune image dans la base de données!")
            return
        
        embed = discord.Embed(
            title="📊 Stock d'images disponibles",
            color=discord.Color.green()
        )
        
        total = 0
        for row in results:
            category_display = row['category'].replace('_', ' ').title()
            embed.add_field(
                name=f"📁 {category_display}",
                value=f"**{row['count']}** images",
                inline=True
            )
            total += row['count']
        
        embed.set_footer(text=f"Total: {total} images disponibles")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        print(f"Erreur: {e}")
        await interaction.followup.send("❌ Une erreur est survenue!")

# Lancer le bot
if __name__ == "__main__":
    bot.run(TOKEN)
