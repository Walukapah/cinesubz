#!/usr/bin/env python3
"""
CineSubz.lk Episode Info Extractor - CLI Version
Usage: python index.py <episode_url>
"""

import sys
import re
import json
import os
import urllib.request
from urllib.parse import urlparse, urlencode


def fetch_html(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Referer': 'https://cinesubz.lk/',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching HTML: {e}", file=sys.stderr)
        return None


def call_player_api(base_url, page_url, post_id, data_type, nume):
    api_url = base_url + "wp-admin/admin-ajax.php"
    post_data = {
        'action': 'zeta_player_ajax',
        'post': post_id,
        'nume': nume,
        'type': data_type
    }
    data = urlencode(post_data).encode('utf-8')
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
        'Origin': base_url.rstrip('/'),
        'Referer': page_url,
        'Connection': 'keep-alive',
    }
    req = urllib.request.Request(api_url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error calling player API: {e}", file=sys.stderr)
        return None


def download_page(url, output_path):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://cinesubz.lk/',
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as response:
            content = response.read()
            with open(output_path, 'wb') as f:
                f.write(content)
            return True
    except Exception as e:
        print(f"Error downloading page: {e}", file=sys.stderr)
        return False


def extract_video_from_embed(html_content):
    """Extract direct video URL from embed/player page HTML."""
    # Try ALL_QUALITIES array
    patterns = [
        r'const\s+ALL_QUALITIES\s*=\s*(\[.*?\]);',
        r'var\s+ALL_QUALITIES\s*=\s*(\[.*?\]);',
        r'let\s+ALL_QUALITIES\s*=\s*(\[.*?\]);',
    ]

    for pattern in patterns:
        match = re.search(pattern, html_content, re.DOTALL)
        if match:
            json_str = match.group(1)
            try:
                qualities = json.loads(json_str)
            except:
                json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                try:
                    qualities = json.loads(json_str)
                except:
                    qualities = None

            if qualities:
                results = []
                for q in qualities:
                    if isinstance(q, dict) and 'url' in q:
                        results.append({
                            'quality': q.get('html', q.get('name', 'Unknown')),
                            'url': q['url'],
                            'default': q.get('default', False)
                        })
                if results:
                    return results

    # Fallback: find mp4 URLs
    mp4_pattern = r'(https?://[^\s"\'<>]+\.mp4(?:\?[^\s"\'<>]*)?)'
    mp4_matches = re.findall(mp4_pattern, html_content)
    seen = set()
    results = []
    for url in mp4_matches:
        if url not in seen:
            seen.add(url)
            # Extract quality from URL
            q_match = re.search(r'-(480P|720P|1080P|1440P|2160P)', url, re.I)
            quality = q_match.group(1).upper() if q_match else 'Unknown'
            results.append({
                'quality': quality,
                'url': url,
                'default': False
            })

    if results:
        return results

    # Fallback: url: "..." pattern
    url_pattern = r'url:\s*[\'](https?://[^\s"\'<>]+)[\']'
    url_matches = re.findall(url_pattern, html_content)
    seen = set()
    for url in url_matches:
        if url not in seen:
            seen.add(url)
            results.append({
                'quality': 'Unknown',
                'url': url,
                'default': True
            })

    return results


def generate_quality_variants(video_url):
    """Generate 480P, 720P, 1080P variants from a single URL."""
    if not video_url:
        return []

    quality_list = ['480P', '720P', '1080P']
    quality_pattern = r'-(480P|720P|1080P|1440P|2160P|4320P)(\.mp4)'

    match = re.search(quality_pattern, video_url, re.IGNORECASE)
    if not match:
        return [{'quality': 'Original', 'url': video_url, 'default': True}]

    found_quality = match.group(1).upper()
    extension = match.group(2)

    variants = []
    for q in quality_list:
        new_url = re.sub(quality_pattern, '-' + q + extension, video_url, flags=re.IGNORECASE)
        variants.append({
            'quality': q,
            'url': new_url,
            'default': q == found_quality
        })

    return variants


def extract_episode_info(html, url):
    """Extract all episode information from HTML."""
    info = {}

    # Base URL
    parsed = urlparse(url)
    base_url = parsed.scheme + "://" + parsed.netloc + "/"
    info['source_url'] = url
    info['base_url'] = base_url.rstrip('/')

    # Title from <title>
    title_match = re.search(r'<title>([^<]+?)\s*-\s*CineSubz', html, re.I)
    info['title'] = title_match.group(1).strip() if title_match else None

    # Episode Title
    ep_title_match = re.search(r'<strong>Episode Title:</strong><a>([^<]+)</a>', html)
    info['episode_title'] = ep_title_match.group(1).strip() if ep_title_match else None

    # Series Name
    series_match = re.search(r'<strong>Serie:</strong><a[^>]*>([^<]+)</a>', html)
    info['series'] = series_match.group(1).strip() if series_match else None

    # Year
    year_match = re.search(r'<strong>Year:</strong><a[^>]*>(\d{4})</a>', html)
    info['year'] = year_match.group(1) if year_match else None

    # Season & Episode from title or URL
    se_match = re.search(r'[Ss]?(\d+)[x×\-]?[Ee]?(\d+)', info.get('title', '') + ' ' + url)
    if se_match:
        info['season'] = int(se_match.group(1))
        info['episode'] = int(se_match.group(2))
    else:
        info['season'] = None
        info['episode'] = None

    # Post ID
    post_id_match = re.search(r'data-post=["\'](\d+)["\']', html)
    info['post_id'] = post_id_match.group(1) if post_id_match else None

    # Data Type
    type_match = re.search(r'data-type=["\']([^"\']+)["\']', html)
    info['data_type'] = type_match.group(1) if type_match else 'ep'

    # Description
    desc_match = re.search(r'<div class="details-desc">\s*<p>(.*?)</p>\s*</div>', html, re.DOTALL)
    if desc_match:
        desc = re.sub(r'<[^>]+>', '', desc_match.group(1))
        desc = re.sub(r'\s+', ' ', desc).strip()
        info['description'] = desc if desc else None
    else:
        info['description'] = None

    # Rating
    rating_match = re.search(r'ratingValue["\'][^>]*content=["\']([\d.]+)["\']', html)
    if not rating_match:
        rating_match = re.search(r'zt_rating_vgs["\'][^>]*>([\d.]+)<', html)
    info['rating'] = rating_match.group(1) if rating_match else None

    # Rating count
    count_match = re.search(r'ratingCount["\'][^>]*content=["\'](\d+)["\']', html)
    if not count_match:
        count_match = re.search(r'(\d+)\s*vote', html)
    info['rating_count'] = count_match.group(1) if count_match else None

    # Poster / Backdrop
    poster_match = re.search(r'<meta property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html)
    info['poster'] = poster_match.group(1) if poster_match else None

    # Backdrop from splash
    backdrop_match = re.search(r'<div class=[\']splash-bg[\']>.*?<img src=[\']([^\'"]+)[\']', html, re.DOTALL)
    if backdrop_match and 'zt_backdrop' not in backdrop_match.group(1):
        info['backdrop'] = backdrop_match.group(1)
    else:
        info['backdrop'] = info.get('poster')

    # Gallery images
    gallery = []
    gallery_matches = re.findall(r'<div class=[\']gall-item[\']>.*?<a href=[\']([^\'"]+)[\'].*?<img src=[\']([^\'"]+)[\']\s*alt=[\']([^\'"]*)[\']', html, re.DOTALL)
    for full, thumb, alt in gallery_matches:
        gallery.append({
            'full_url': full.strip(),
            'thumbnail_url': thumb.strip(),
            'alt': alt.strip()
        })
    info['gallery'] = gallery if gallery else None

    # Keywords/Tags
    keywords = []
    kw_matches = re.findall(r'<a href="https://cinesubz\.lk/keywords/[^"]+"[^>]*>([^<]+)</a>', html)
    for kw in kw_matches:
        k = kw.strip()
        if k and k not in keywords:
            keywords.append(k)
    info['keywords'] = keywords if keywords else None

    # Player Options
    players = []
    player_matches = re.findall(r'<li[^>]*data-post=["\'](\d+)["\'][^>]*data-nume=["\'](\d+)["\'][^>]*>.*?<span class=["\']opt-name["\']>([^<]+)</span>', html, re.DOTALL)
    for post, nume, name in player_matches:
        players.append({
            'post_id': post,
            'nume': nume,
            'name': name.strip(),
            'type': info.get('data_type', 'ep')
        })
    info['players'] = players if players else None

    # Download Links
    downloads = []
    dl_matches = re.findall(
        r'<div class=["\']download-link-item["\'][^>]*>.*?'
        r'<a href=["\']([^"\']+)["\'][^>]*>.*?'
        r'<span class=["\']download-type["\']>([^<]+)</span>.*?'
        r'<span class=["\']download-meta["\']>([^<]+)</span>',
        html, re.DOTALL
    )
    for link, dl_type, meta in dl_matches:
        meta_parts = [p.strip() for p in meta.split('•')]
        quality = meta_parts[0] if len(meta_parts) > 0 else 'Unknown'
        size = meta_parts[1] if len(meta_parts) > 1 else 'Unknown'
        language = meta_parts[2] if len(meta_parts) > 2 else 'Unknown'

        downloads.append({
            'url': link.strip(),
            'type': dl_type.strip(),
            'quality': quality,
            'size': size,
            'language': language
        })
    info['downloads'] = downloads if downloads else None

    # Episode Navigation
    nav = {}
    prev_match = re.search(r'<a href=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*nav-prev[^"\']*["\']', html)
    if prev_match and 'disabled' not in prev_match.group(0):
        nav['prev'] = prev_match.group(1)
    else:
        nav['prev'] = None

    next_match = re.search(r'<a href=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*nav-next[^"\']*["\']', html)
    if next_match:
        nav['next'] = next_match.group(1)
    else:
        nav['next'] = None

    all_match = re.search(r'<a href=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*nav-all[^"\']*["\']', html)
    if all_match:
        nav['all_episodes'] = all_match.group(1)
    else:
        nav['all_episodes'] = None

    info['navigation'] = nav

    # Episode List (Season episodes)
    episode_list = []
    ep_matches = re.findall(
        r'<li class=["\']ep-(\d+)[^"\']*["\']>.*?'
        r'<a href=["\']([^"\']+)["\']>.*?'
        r'<span class=["\']ep-title["\']>([^<]+)</span>.*?'
        r'<span class=["\']ep-date["\']>([^<]+)</span>',
        html, re.DOTALL
    )
    for ep_num, ep_url, ep_title, ep_date in ep_matches:
        episode_list.append({
            'episode_number': int(ep_num),
            'url': ep_url.strip(),
            'title': ep_title.strip(),
            'date': ep_date.strip(),
            'active': 'active' in ep_url or False
        })
    info['episode_list'] = episode_list if episode_list else None

    return info


def get_streaming_urls(base_url, page_url, players_info):
    """Get streaming URLs by calling player APIs and parsing embed pages."""
    streaming_urls = []
    temp_files = []

    for player in players_info:
        post_id = player.get('post_id')
        nume = player.get('nume')
        ptype = player.get('type', 'ep')
        name = player.get('name', 'Unknown')

        print(f"  Calling player API: {name}...", file=sys.stderr)
        response = call_player_api(base_url, page_url, post_id, ptype, nume)
        if not response:
            continue

        try:
            data = json.loads(response)
        except:
            continue

        embed_url = data.get('embed_url')
        video_type = data.get('type', 'unknown')

        if not embed_url:
            continue

        if video_type in ('iframe', 'trailer'):
            continue

        if video_type in ('mp4', 'ztshcode') and str(embed_url).startswith('http'):
            # Download embed page to extract video URL
            temp_file = f"/tmp/embed_{post_id}_{nume}.html"
            temp_files.append(temp_file)

            print(f"  Downloading embed page...", file=sys.stderr)
            success = download_page(str(embed_url), temp_file)
            if success and os.path.exists(temp_file):
                try:
                    with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
                        embed_html = f.read()

                    videos = extract_video_from_embed(embed_html)
                    if videos:
                        for v in videos:
                            v['player'] = name
                            streaming_urls.append(v)
                    else:
                        streaming_urls.append({
                            'quality': 'Direct',
                            'url': str(embed_url),
                            'default': True,
                            'player': name
                        })
                except:
                    streaming_urls.append({
                        'quality': 'Direct',
                        'url': str(embed_url),
                        'default': True,
                        'player': name
                    })
            else:
                streaming_urls.append({
                    'quality': 'Direct',
                    'url': str(embed_url),
                    'default': True,
                    'player': name
                })

    # Clean up temp files
    for tf in temp_files:
        try:
            if os.path.exists(tf):
                os.remove(tf)
        except:
            pass

    # Deduplicate and generate quality variants
    seen = set()
    unique_urls = []
    for v in streaming_urls:
        if v['url'] not in seen:
            seen.add(v['url'])
            unique_urls.append(v)

    # Generate multi-quality variants for each unique URL
    final_streams = []
    seen_final = set()
    for v in unique_urls:
        variants = generate_quality_variants(v['url'])
        for variant in variants:
            variant['player'] = v.get('player', 'Unknown')
            if variant['url'] not in seen_final:
                seen_final.add(variant['url'])
                final_streams.append(variant)

    return final_streams


def normalize_quality(q_str):
    """Normalize quality string to 480P, 720P, or 1080P."""
    q_str = q_str.upper()
    if '480' in q_str or 'SD' in q_str:
        return '480P'
    elif '720' in q_str or 'HD' in q_str:
        return '720P'
    elif '1080' in q_str or 'FHD' in q_str:
        return '1080P'
    return q_str


def build_combined_downloads(streaming_urls, downloads):
    """
    Build combined downloads array:
    - URLs from streaming_urls (480P, 720P, 1080P variants)
    - size and language from downloads matching by quality
    - default flag from streaming_urls
    - player from streaming_urls
    """
    if not streaming_urls:
        return None

    # Map download info by normalized quality
    dl_info_map = {}
    if downloads:
        for dl in downloads:
            norm_q = normalize_quality(dl.get('quality', ''))
            dl_info_map[norm_q] = {
                'size': dl.get('size', 'Unknown'),
                'language': dl.get('language', 'Unknown')
            }

    combined = []
    for stream in streaming_urls:
        norm_q = normalize_quality(stream.get('quality', ''))

        # Get size and language from downloads matching quality
        dl_info = dl_info_map.get(norm_q, {})

        combined.append({
            'url': stream['url'],
            'quality': stream['quality'],
            'size': dl_info.get('size', 'Unknown'),
            'language': dl_info.get('language', 'Unknown'),
            'default': stream.get('default', False),
            'player': stream.get('player', 'Unknown')
        })

    # Sort by quality: 480P, 720P, 1080P
    quality_order = {'480P': 1, '720P': 2, '1080P': 3}
    combined.sort(key=lambda x: quality_order.get(x['quality'].upper(), 99))

    return combined


def run_extractor(url):
    """Run the extractor logic"""
    if not url.startswith(('http://', 'https://')):
        return {
            "success": False,
            "error": "Invalid URL. Must start with http:// or https://"
        }

    print(f"Fetching page: {url}", file=sys.stderr)
    
    # Fetch page HTML
    html = fetch_html(url)
    if not html:
        return {
            "success": False,
            "error": "Failed to fetch page HTML"
        }

    print("Extracting episode info...", file=sys.stderr)
    
    # Extract all info from HTML
    info = extract_episode_info(html, url)

    # Get streaming URLs from player APIs
    parsed = urlparse(url)
    base_url = parsed.scheme + "://" + parsed.netloc + "/"

    players = info.get('players', [])
    if players:
        print(f"Found {len(players)} players, getting streaming URLs...", file=sys.stderr)
        streaming = get_streaming_urls(base_url, url, players)
        info['streaming_urls'] = streaming if streaming else None
    else:
        info['streaming_urls'] = None

    # Build combined downloads from streaming_urls + downloads metadata
    downloads_raw = info.get('downloads', [])
    if info.get('streaming_urls'):
        print("Building combined downloads...", file=sys.stderr)
        info['downloads'] = build_combined_downloads(info['streaming_urls'], downloads_raw)

    # Build final output
    return {
        "success": True,
        "data": info
    }


def main():
    """Main CLI entry point"""
    if len(sys.argv) < 2:
        print("Usage: python index.py <episode_url>", file=sys.stderr)
        print("Example: python index.py https://cinesubz.lk/episodes/from-2x1/", file=sys.stderr)
        sys.exit(1)
    
    url = sys.argv[1]
    
    # Run extractor
    result = run_extractor(url)
    
    # Print JSON result to stdout
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Exit with appropriate code
    sys.exit(0 if result.get('success') else 1)


if __name__ == '__main__':
    main()
