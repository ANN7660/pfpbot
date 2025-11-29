# 🤖 Bot Discord PFP

Bot Discord pour distribuer des photos de profil et banners depuis une base PostgreSQL.

## 🎯 Fonctionnalités

- 📥 Distribution automatique de 15 images par commande
- 🎨 6 catégories : anime, boy, girl, aesthetic, cute, banner
- 📊 Système de statistiques en temps réel
- 🔄 Rotation automatique des images
- 🌐 API Flask intégrée pour monitoring

## 🚀 Commandes Discord

| Commande | Description |
|----------|-------------|
| `!help` | Affiche l'aide |
| `!pdp <catégorie>` | Envoie 15 images (anime, boy, girl, aesthetic, cute) |
| `!banner` | Envoie 15 banners Discord |
| `!stock` | Voir le stock disponible |
| `!trending` | Top 5 des catégories |
| `!stats` | Statistiques globales |
| `!ping` | Vérifier la latence |

## 📦 Installation locale
```bash
# Cloner le repo
git clone https://github.com/TON_USERNAME/ton-repo.git
cd ton-repo

# Créer un environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Installer les dépendances
pip install -r requirements.txt

# Créer un fichier .env
cp .env.example .env
# Éditer .env avec tes credentials

# Lancer le bot
python bot.py
```

## 🌐 Déploiement sur Render

1. Connecte ce repo à Render
2. Créer un PostgreSQL sur Render
3. Ajouter les variables d'environnement :
   - `DISCORD_TOKEN`
   - `DATABASE_URL`
   - `PORT` (10000)

4. Render va automatiquement :
   - Installer les dépendances (`requirements.txt`)
   - Lancer le bot (`python bot.py`)

## 🗄️ Structure de la base de données
```sql
CREATE TABLE images (
    id SERIAL PRIMARY KEY,
    image_url TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    sent_at TIMESTAMP
);
```

## 📊 API Endpoints

- `GET /` - Informations du bot
- `GET /health` - Health check
- `GET /stats` - Statistiques JSON

## 🛠️ Technologies

- **Discord.py** - Librairie Discord
- **PostgreSQL** - Base de données
- **Flask** - API web
- **psycopg2** - Driver PostgreSQL
- **Render** - Hébergement

## 📝 License

MIT License - Utilise comme tu veux !

## 👤 Auteur

Ton nom - [@ton_discord](https://discord.gg/ton_serveur)

## 🙏 Remerciements

- Discord.py community
- Render.com
