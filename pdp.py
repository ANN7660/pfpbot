# ======================================== 
# SCRAPING AMÉLIORÉ AVEC ROTATION
# ========================================

import random
from typing import List, Optional

# User-Agents multiples pour éviter la détection
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

def get_random_headers():
    """Génère des headers aléatoires pour éviter la détection"""
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,fr;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
    }

# ======================================== 
# RECHERCHE GOOGLE IMAGES (AMÉLIORÉE)
# ========================================

async def search_google_images(query: str, count: int = 10) -> List[str]:
    """Recherche Google Images avec scraping amélioré"""
    cache_key = f"google_{hashlib.md5(query.encode()).hexdigest()}"
    cached = image_cache.get(cache_key)
    if cached:
        logger.info(f"✅ Google cache hit")
        return cached
    
    try:
        await rate_limiter.acquire()
        await asyncio.sleep(random.uniform(0.5, 1.5))  # Délai aléatoire
        
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        
        # URL avec paramètres pour images de qualité
        url = f"https://www.google.com/search?q={encoded_query}&tbm=isch&tbs=isz:m&safe=active"
        
        headers = get_random_headers()
        headers['Referer'] = 'https://www.google.com/'
        
        async with session.get(url, headers=headers, timeout=Config.REQUEST_TIMEOUT) as response:
            if response.status == 200:
                html = await response.text()
                images = []
                
                # Plusieurs patterns pour plus de robustesse
                patterns = [
                    r'"ou":"(https?://[^"]+)"',
                    r'"url":"(https?://[^"]+)"',
                    r'\["(https?://[^"]+\.(?:jpg|jpeg|png|webp|gif))',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    for match in matches:
                        if len(images) >= count:
                            break
                        
                        clean_url = match.split('&')[0].replace('\\/', '/')
                        
                        if is_valid_image_url(clean_url) and clean_url not in images:
                            images.append(clean_url)
                    
                    if images:
                        break
                
                logger.info(f"✅ Google: {len(images)} images")
                if images:
                    image_cache.set(cache_key, images)
                return images[:count]
            else:
                logger.warning(f"⚠️ Google status: {response.status}")
                
    except asyncio.TimeoutError:
        logger.error(f"⏱️ Google timeout")
    except Exception as e:
        logger.error(f"❌ Google error: {e}")
    
    return []

# ======================================== 
# RECHERCHE PINTEREST (AMÉLIORÉE)
# ========================================

async def search_pinterest(query: str, count: int = 10) -> List[str]:
    """Recherche Pinterest avec scraping amélioré"""
    cache_key = f"pinterest_{hashlib.md5(query.encode()).hexdigest()}"
    cached = image_cache.get(cache_key)
    if cached:
        logger.info(f"✅ Pinterest cache hit")
        return cached
    
    try:
        await rate_limiter.acquire()
        await asyncio.sleep(random.uniform(0.5, 1.5))  # Délai aléatoire
        
        session = await get_session()
        search_query = f"{query} avatar profile picture"
        encoded_query = urllib.parse.quote(search_query)
        
        url = f"https://www.pinterest.com/search/pins/?q={encoded_query}"
        
        headers = get_random_headers()
        headers['Referer'] = 'https://www.pinterest.com/'
        
        async with session.get(url, headers=headers, timeout=Config.REQUEST_TIMEOUT) as response:
            if response.status == 200:
                html = await response.text()
                images = []
                
                # Patterns multiples pour Pinterest
                patterns = [
                    r'"url":"(https://i\.pinimg\.com/[^"]+)"',
                    r'"src":"(https://i\.pinimg\.com/[^"]+)"',
                    r'srcset="(https://i\.pinimg\.com/[^"]+)"',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, html)
                    for match in matches:
                        if len(images) >= count:
                            break
                        
                        clean_url = match.replace('\\/', '/').replace('\u002F', '/').split('?')[0]
                        
                        # Préférer les images de meilleure qualité
                        if any(size in clean_url for size in ['/736x/', '/originals/', '/564x/']):
                            if is_valid_image_url(clean_url) and clean_url not in images:
                                images.append(clean_url)
                    
                    if images:
                        break
                
                logger.info(f"✅ Pinterest: {len(images)} images")
                if images:
                    image_cache.set(cache_key, images)
                return images[:count]
            else:
                logger.warning(f"⚠️ Pinterest status: {response.status}")
                
    except asyncio.TimeoutError:
        logger.error(f"⏱️ Pinterest timeout")
    except Exception as e:
        logger.error(f"❌ Pinterest error: {e}")
    
    return []

# ======================================== 
# RECHERCHE UNSPLASH (NOUVELLE SOURCE)
# ========================================

async def search_unsplash(query: str, count: int = 10) -> List[str]:
    """Recherche sur Unsplash (images libres de droits)"""
    api_key = os.getenv('UNSPLASH_ACCESS_KEY')
    
    # Fallback vers scraping si pas d'API key
    if not api_key:
        return await search_unsplash_scraping(query, count)
    
    try:
        await rate_limiter.acquire()
        
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.unsplash.com/search/photos?query={encoded_query}&per_page={count}&orientation=squarish"
        
        headers = {
            'Authorization': f'Client-ID {api_key}',
            'Accept-Version': 'v1'
        }
        
        async with session.get(url, headers=headers, timeout=Config.REQUEST_TIMEOUT) as response:
            if response.status == 200:
                data = await response.json()
                images = [photo['urls']['regular'] for photo in data.get('results', [])]
                logger.info(f"✅ Unsplash API: {len(images)} images")
                return images
    except Exception as e:
        logger.error(f"❌ Unsplash API: {e}")
    
    return []

async def search_unsplash_scraping(query: str, count: int = 10) -> List[str]:
    """Scraping Unsplash sans API key"""
    try:
        await rate_limiter.acquire()
        await asyncio.sleep(random.uniform(0.3, 0.8))
        
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        url = f"https://unsplash.com/s/photos/{encoded_query}"
        
        headers = get_random_headers()
        
        async with session.get(url, headers=headers, timeout=Config.REQUEST_TIMEOUT) as response:
            if response.status == 200:
                html = await response.text()
                images = []
                
                pattern = r'srcSet="(https://images\.unsplash\.com/[^"]+)"'
                matches = re.findall(pattern, html)
                
                for match in matches[:count]:
                    clean_url = match.split('?')[0] + '?w=800&q=80'
                    if is_valid_image_url(clean_url):
                        images.append(clean_url)
                
                logger.info(f"✅ Unsplash scraping: {len(images)} images")
                return images
    except Exception as e:
        logger.error(f"❌ Unsplash scraping: {e}")
    
    return []

# ======================================== 
# RECHERCHE BING IMAGES (ALTERNATIVE)
# ========================================

async def search_bing_images(query: str, count: int = 10) -> List[str]:
    """Recherche sur Bing Images (souvent moins restrictif que Google)"""
    cache_key = f"bing_{hashlib.md5(query.encode()).hexdigest()}"
    cached = image_cache.get(cache_key)
    if cached:
        logger.info(f"✅ Bing cache hit")
        return cached
    
    try:
        await rate_limiter.acquire()
        await asyncio.sleep(random.uniform(0.3, 0.8))
        
        session = await get_session()
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.bing.com/images/search?q={encoded_query}&qft=+filterui:imagesize-medium&FORM=IRFLTR"
        
        headers = get_random_headers()
        headers['Referer'] = 'https://www.bing.com/'
        
        async with session.get(url, headers=headers, timeout=Config.REQUEST_TIMEOUT) as response:
            if response.status == 200:
                html = await response.text()
                images = []
                
                # Bing utilise un format JSON dans le HTML
                patterns = [
                    r'"murl":"(https?://[^"]+)"',
                    r'"turl":"(https?://[^"]+)"',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, html)
                    for match in matches:
                        if len(images) >= count:
                            break
                        
                        clean_url = match.replace('\\/', '/')
                        if is_valid_image_url(clean_url) and clean_url not in images:
                            images.append(clean_url)
                    
                    if len(images) >= count:
                        break
                
                logger.info(f"✅ Bing: {len(images)} images")
                if images:
                    image_cache.set(cache_key, images)
                return images[:count]
            else:
                logger.warning(f"⚠️ Bing status: {response.status}")
                
    except Exception as e:
        logger.error(f"❌ Bing: {e}")
    
    return []

# ======================================== 
# RECHERCHE AGRÉGÉE AMÉLIORÉE
# ========================================

async def search_images(query: str, count: int = 10) -> List[str]:
    """
    Recherche d'images agrégée avec multiples sources et fallback
    Priorité: Bing > Unsplash > Pinterest > Google
    """
    all_images = []
    
    # Lancer toutes les recherches en parallèle
    tasks = [
        search_bing_images(query, count),
        search_unsplash(query, count),
        search_pinterest(query, count),
        search_google_images(query, count),
    ]
    
    # Si APIs disponibles, les utiliser aussi
    if os.getenv('PEXELS_API_KEY'):
        tasks.append(search_pexels(query, count))
    if os.getenv('PIXABAY_API_KEY'):
        tasks.append(search_pixabay(query, count))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Collecter toutes les images valides
    for result in results:
        if isinstance(result, list):
            all_images.extend(result)
        elif isinstance(result, Exception):
            logger.warning(f"⚠️ Une source a échoué: {result}")
    
    # Dédupliquer et mélanger
    unique_images = []
    seen_urls = set()
    
    for img in all_images:
        if img not in seen_urls and is_valid_image_url(img):
            unique_images.append(img)
            seen_urls.add(img)
    
    random.shuffle(unique_images)
    final_images = unique_images[:count]
    
    logger.info(f"🎯 Total final: {len(final_images)} images uniques pour '{query}'")
    
    # Si toujours pas d'images, essayer avec une requête simplifiée
    if not final_images:
        logger.warning(f"⚠️ Aucun résultat, tentative avec requête simplifiée...")
        simplified_query = query.split()[0]  # Prendre juste le premier mot
        return await search_images_fallback(simplified_query, count)
    
    return final_images

async def search_images_fallback(query: str, count: int = 10) -> List[str]:
    """Recherche de secours avec requête simplifiée"""
    try:
        # Essayer Bing en priorité (généralement plus permissif)
        images = await search_bing_images(query, count)
        
        if not images:
            # Fallback vers Unsplash
            images = await search_unsplash(query, count)
        
        return images
    except Exception as e:
        logger.error(f"❌ Fallback échoué: {e}")
        return []

# ======================================== 
# FONCTION DE DIAGNOSTIC
# ========================================

@bot.command(name='test_search')
@commands.is_owner()  # Réservé au propriétaire du bot
async def test_search_command(ctx, *, query: str = "anime"):
    """Teste toutes les sources de recherche individuellement"""
    embed = discord.Embed(title="🔍 Test des sources de recherche", color=discord.Color.blue())
    embed.description = f"Requête: **{query}**"
    
    msg = await ctx.send(embed=embed)
    
    sources = {
        'Bing': search_bing_images,
        'Google': search_google_images,
        'Pinterest': search_pinterest,
        'Unsplash': search_unsplash,
    }
    
    for name, func in sources.items():
        try:
            results = await func(query, count=5)
            status = f"✅ {len(results)} images" if results else "❌ 0 images"
            embed.add_field(name=name, value=status, inline=True)
        except Exception as e:
            embed.add_field(name=name, value=f"❌ Erreur: {str(e)[:50]}", inline=True)
        
        await msg.edit(embed=embed)
        await asyncio.sleep(1)
    
    embed.set_footer(text="Test terminé")
    await msg.edit(embed=embed)
