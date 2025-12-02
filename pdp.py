# Ajoutez ces imports en haut de votre fichier Flask
import requests
import re
import json
import time
import random
from bs4 import BeautifulSoup

# ===== CLASSE SCRAPER (Copiez la classe PinterestScraper complète ici) =====

class PinterestScraper:
    """Scraper Pinterest sans API"""
    
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def scrape(self, url, max_images=50):
        """Méthode combinée avec les 3 techniques"""
        try:
            time.sleep(random.uniform(1, 2))
            
            response = self.session.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            images = set()
            
            # 1. Chercher le JSON embarqué
            pattern = r'<script id="__PWS_DATA__" type="application/json">({.*?})</script>'
            match = re.search(pattern, response.text, re.DOTALL)
            
            if match:
                try:
                    data = json.loads(match.group(1))
                    self._extract_images_recursive(data, images)
                except:
                    pass
            
            # 2. Regex agressif sur URLs
            patterns = [
                r'https://i\.pinimg\.com/originals/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9a-zA-Z_-]+\.(?:jpg|jpeg|png)',
                r'https://i\.pinimg\.com/736x/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9a-zA-Z_-]+\.(?:jpg|jpeg|png)',
            ]
            
            for p in patterns:
                matches = re.findall(p, response.text)
                images.update(matches)
            
            # Convertir en haute qualité
            hq_images = []
            for img in images:
                if '/originals/' in img:
                    hq_images.append(img.split('?')[0])
                else:
                    converted = re.sub(r'/(736x|564x|474x|236x)/', '/originals/', img)
                    hq_images.append(converted.split('?')[0])
            
            result = list(set(hq_images))[:max_images]
            logging.info(f"✅ {len(result)} images extraites de Pinterest")
            return result
            
        except Exception as e:
            logging.error(f"❌ Erreur scraping Pinterest: {e}")
            return []
    
    def _extract_images_recursive(self, obj, images, depth=0):
        """Extraction récursive des URLs d'images"""
        if depth > 8:
            return
        
        if isinstance(obj, dict):
            for key in ['url', 'src', 'image']:
                if key in obj:
                    value = obj[key]
                    if isinstance(value, str) and 'pinimg.com' in value:
                        images.add(value.split('?')[0])
            
            for value in obj.values():
                self._extract_images_recursive(value, images, depth + 1)
                
        elif isinstance(obj, list):
            for item in obj:
                self._extract_images_recursive(item, images, depth + 1)


# ===== ENDPOINT FLASK MODIFIÉ =====

@app.route("/api/import", methods=["POST"])
@require_api_key
@limiter.limit("5 per hour")  # Limite stricte pour éviter les bans
def import_photos():
    """Endpoint d'import avec scraping Pinterest SANS API"""
    conn = db_connect()
    if not conn:
        return jsonify({"error": "Erreur DB"}), 500
    
    try:
        data = request.get_json()
        pinterest_url = data.get('pinterest_url', '')
        category = data.get('category', 'uncategorized')
        max_photos = min(100, data.get('max_photos', 50))
        
        # Validation de l'URL
        if not pinterest_url:
            return jsonify({"error": "URL Pinterest manquante"}), 400
        
        if 'pinterest.com' not in pinterest_url:
            return jsonify({"error": "L'URL doit être un lien Pinterest"}), 400
        
        # SCRAPING RÉEL
        logging.info(f"🔍 Scraping Pinterest: {pinterest_url}")
        scraper = PinterestScraper()
        urls = scraper.scrape(pinterest_url, max_photos)
        
        if not urls:
            return jsonify({
                "error": "Aucune image trouvée",
                "suggestion": "Essayez une autre URL ou vérifiez que la page contient des images"
            }), 404
        
        # Insertion en base de données
        cur = conn.cursor()
        inserted = 0
        duplicates = 0
        errors = 0
        
        for url in urls:
            # Validation finale de l'URL
            if not url.startswith('https://i.pinimg.com/'):
                errors += 1
                continue
            
            try:
                cur.execute(
                    "INSERT INTO images (url, category, used) VALUES (%s, %s, FALSE) RETURNING id",
                    (url, category)
                )
                result = cur.fetchone()
                if result:
                    inserted += 1
                    logging.info(f"✅ Image ajoutée: {url[:50]}...")
                conn.commit()
                
            except psycopg2.IntegrityError:
                duplicates += 1
                conn.rollback()
            except Exception as e:
                errors += 1
                logging.error(f"❌ Erreur insertion: {e}")
                conn.rollback()
        
        cur.close()
        conn.close()
        
        # Invalider le cache
        cache.clear()
        
        # Log final
        logging.info(f"""
        📊 RÉSULTAT IMPORT:
        - Détectées: {len(urls)}
        - Insérées: {inserted}
        - Doublons: {duplicates}
        - Erreurs: {errors}
        """)
        
        return jsonify({
            "success": True,
            "detected": len(urls),
            "inserted": inserted,
            "duplicates": duplicates,
            "errors": errors,
            "category": category,
            "message": f"✅ {inserted} photos importées avec succès !"
        })
        
    except Exception as e:
        logging.error(f"❌ Erreur import: {e}")
        return jsonify({"error": f"Erreur serveur: {str(e)}"}), 500


# ===== ENDPOINT BONUS : Import par recherche =====

@app.route("/api/import/search", methods=["POST"])
@require_api_key
@limiter.limit("5 per hour")
def import_by_search():
    """Import direct depuis une recherche Pinterest"""
    try:
        data = request.get_json()
        query = data.get('query', '')
        category = data.get('category', 'uncategorized')
        max_photos = min(100, data.get('max_photos', 50))
        
        if not query:
            return jsonify({"error": "Requête de recherche manquante"}), 400
        
        # Construire l'URL de recherche Pinterest
        search_url = f"https://www.pinterest.com/search/pins/?q={query.replace(' ', '%20')}"
        
        logging.info(f"🔍 Recherche Pinterest: {query}")
        scraper = PinterestScraper()
        urls = scraper.scrape(search_url, max_photos)
        
        if not urls:
            return jsonify({
                "error": "Aucune image trouvée pour cette recherche",
                "query": query
            }), 404
        
        # Insertion (même logique que import_photos)
        conn = db_connect()
        if not conn:
            return jsonify({"error": "Erreur DB"}), 500
        
        cur = conn.cursor()
        inserted = 0
        duplicates = 0
        
        for url in urls:
            try:
                cur.execute(
                    "INSERT INTO images (url, category, used) VALUES (%s, %s, FALSE)",
                    (url, category)
                )
                inserted += 1
                conn.commit()
            except psycopg2.IntegrityError:
                duplicates += 1
                conn.rollback()
        
        cur.close()
        conn.close()
        cache.clear()
        
        return jsonify({
            "success": True,
            "query": query,
            "detected": len(urls),
            "inserted": inserted,
            "duplicates": duplicates,
            "category": category
        })
        
    except Exception as e:
        logging.error(f"❌ Erreur import search: {e}")
        return jsonify({"error": str(e)}), 500
