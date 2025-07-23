import os
import shutil
from jinja2 import Environment, FileSystemLoader
import markdown
import yaml
import re
from pathlib import Path
import hashlib
import base64
import json
import datetime
import argparse
# Lazy import for optional dependencies
EBOOKLIB_AVAILABLE = False

# Global flag for including drafts
INCLUDE_DRAFTS = False


def _check_ebooklib():
    global EBOOKLIB_AVAILABLE
    try:
        import ebooklib
        from ebooklib import epub
        EBOOKLIB_AVAILABLE = True
        return True
    except ImportError:
        EBOOKLIB_AVAILABLE = False
        return False

BUILD_DIR = "./build"
CONTENT_DIR = "./content"
TEMPLATES_DIR = "./templates"
STATIC_DIR = "./static"

env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

def encrypt_content_with_password(content, password):
    """Encrypt content using XOR with SHA256 hash of password"""
    # Create SHA256 hash of password for consistent key
    key = hashlib.sha256(password.encode('utf-8')).digest()
    
    # Convert content to bytes
    content_bytes = content.encode('utf-8')
    
    # XOR encrypt
    encrypted = bytearray()
    for i, byte in enumerate(content_bytes):
        encrypted.append(byte ^ key[i % len(key)])
    
    # Return base64 encoded encrypted content
    return base64.b64encode(encrypted).decode('utf-8')

def create_password_verification_hash(password):
    """Create a verification hash that can be checked client-side"""
    # Use a simple hash that can be reproduced in JavaScript
    return hashlib.sha256(password.encode('utf-8')).hexdigest()[:16]

def build_footer_content(site_config, novel_config=None, page_type='site'):
    """Build footer content based on site and story configurations"""
    footer_data = {}
    
    # Determine copyright text
    if novel_config and novel_config.get('footer', {}).get('custom_text'):
        footer_data['copyright'] = novel_config['footer']['custom_text']
    elif novel_config and novel_config.get('copyright'):
        footer_data['copyright'] = novel_config['copyright']
    else:
        site_name = site_config.get('site_name', 'Web Novel Collection')
        footer_data['copyright'] = f"© 2025 {site_name}"
    
    # Build footer links
    footer_links = []
    
    # Add story-specific links if available
    if novel_config and novel_config.get('footer', {}).get('links'):
        footer_links.extend(novel_config['footer']['links'])
    
    # Add site-wide footer links if available
    if site_config.get('footer', {}).get('links'):
        footer_links.extend(site_config['footer']['links'])
    
    footer_data['links'] = footer_links
    
    # Add additional footer text
    if site_config.get('footer', {}).get('additional_text'):
        footer_data['additional_text'] = site_config['footer']['additional_text']
    
    return footer_data

def generate_rss_feed(site_config, novels_data, novel_config=None, novel_slug=None):
    """Generate RSS feed for site or specific story"""
    from datetime import datetime
    
    site_url = site_config.get('site_url', '').rstrip('/')
    site_name = site_config.get('site_name', 'Web Novel Collection')
    
    if novel_config and novel_slug:
        # Story-specific RSS feed
        feed_title = novel_config.get('title', 'Web Novel')
        feed_description = novel_config.get('description', 'Web Novel RSS Feed')
        feed_link = f"{site_url}/{novel_slug}/"
        feed_items = []
        
        # Get chapters for this novel
        available_languages = get_available_languages(novel_slug)
        primary_lang = novel_config.get('primary_language', 'en')
        
        all_chapters = []
        for arc in novel_config.get("arcs", []):
            all_chapters.extend(arc.get("chapters", []))
        
        # Sort chapters by published date (most recent first)
        chapter_items = []
        for chapter in all_chapters:
            chapter_id = chapter["id"]
            try:
                chapter_content_md, chapter_metadata = load_chapter_content(novel_slug, chapter_id, primary_lang)
                
                # Skip draft chapters unless include_drafts is True
                if is_chapter_draft(chapter_metadata) and not INCLUDE_DRAFTS:
                    continue
                
                # Skip hidden chapters, password-protected, or non-indexed chapters
                if (is_chapter_hidden(chapter_metadata) or 
                    ('password' in chapter_metadata and chapter_metadata['password']) or
                    chapter_metadata.get('seo', {}).get('allow_indexing') is False):
                    continue
                
                published_date = chapter_metadata.get('published')
                if published_date:
                    try:
                        pub_datetime = datetime.strptime(published_date, '%Y-%m-%d')
                        chapter_items.append({
                            'id': chapter_id,
                            'title': chapter_metadata.get('title', chapter['title']),
                            'link': f"{site_url}/{novel_slug}/{primary_lang}/{chapter_id}/",
                            'description': chapter_metadata.get('social_embeds', {}).get('description', ''),
                            'pub_date': pub_datetime,
                            'content': convert_markdown_to_html(chapter_content_md[:500] + '...' if len(chapter_content_md) > 500 else chapter_content_md)
                        })
                    except:
                        pass  # Skip chapters with invalid dates
            except:
                continue
        
        # Sort by date (newest first) and take latest 20
        chapter_items.sort(key=lambda x: x['pub_date'], reverse=True)
        feed_items = chapter_items[:20]
        
    else:
        # Site-wide RSS feed
        feed_title = site_name
        feed_description = site_config.get('site_description', 'Web Novel Collection RSS Feed')
        feed_link = site_url
        feed_items = []
        
        # Collect recent chapters from all novels
        all_chapter_items = []
        for novel in novels_data:
            novel_slug = novel['slug']
            novel_config = load_novel_config(novel_slug)
            
            # Skip novels that don't allow indexing
            if novel_config.get('seo', {}).get('allow_indexing') is False:
                continue
            
            primary_lang = novel_config.get('primary_language', 'en')
            
            all_chapters = []
            for arc in novel.get("arcs", []):
                all_chapters.extend(arc.get("chapters", []))
            
            for chapter in all_chapters:
                chapter_id = chapter["id"]
                try:
                    chapter_content_md, chapter_metadata = load_chapter_content(novel_slug, chapter_id, primary_lang)
                    
                    # Skip draft chapters unless include_drafts is True
                    if is_chapter_draft(chapter_metadata) and not INCLUDE_DRAFTS:
                        continue
                    
                    # Skip hidden, password-protected, or non-indexed chapters
                    if (is_chapter_hidden(chapter_metadata) or 
                        ('password' in chapter_metadata and chapter_metadata['password']) or
                        chapter_metadata.get('seo', {}).get('allow_indexing') is False):
                        continue
                    
                    published_date = chapter_metadata.get('published')
                    if published_date:
                        try:
                            pub_datetime = datetime.strptime(published_date, '%Y-%m-%d')
                            all_chapter_items.append({
                                'id': chapter_id,
                                'title': f"{novel.get('title', '')}: {chapter_metadata.get('title', chapter['title'])}",
                                'link': f"{site_url}/{novel_slug}/{primary_lang}/{chapter_id}/",
                                'description': chapter_metadata.get('social_embeds', {}).get('description', ''),
                                'pub_date': pub_datetime,
                                'content': convert_markdown_to_html(chapter_content_md[:300] + '...' if len(chapter_content_md) > 300 else chapter_content_md)
                            })
                        except:
                            pass
                except:
                    continue
        
        # Sort by date (newest first) and take latest 50
        all_chapter_items.sort(key=lambda x: x['pub_date'], reverse=True)
        feed_items = all_chapter_items[:50]
    
    # Build RSS XML
    current_time = datetime.now()
    
    rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
    <title>{feed_title}</title>
    <link>{feed_link}</link>
    <description>{feed_description}</description>
    <language>en-us</language>
    <lastBuildDate>{current_time.strftime('%a, %d %b %Y %H:%M:%S %z')}</lastBuildDate>
    <generator>Web Novel Static Generator</generator>
"""
    
    for item in feed_items:
        pub_date_str = item['pub_date'].strftime('%a, %d %b %Y %H:%M:%S %z') if item['pub_date'] else ''
        
        rss_content += f"""    <item>
        <title>{item['title']}</title>
        <link>{item['link']}</link>
        <description><![CDATA[{item['description']}]]></description>
        <content:encoded><![CDATA[{item['content']}]]></content:encoded>
        <pubDate>{pub_date_str}</pubDate>
        <guid>{item['link']}</guid>
    </item>
"""
    
    rss_content += """</channel>
</rss>"""
    
    return rss_content

def generate_sitemap_xml(site_config, novels_data):
    """Generate sitemap.xml file for SEO"""
    from datetime import datetime
    
    sitemap_entries = []
    site_url = site_config.get('site_url', '').rstrip('/')
    
    if not site_url:
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n</urlset>"
    
    # Add front page
    sitemap_entries.append(f"""    <url>
        <loc>{site_url}/</loc>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>""")
    
    # Add novel pages
    for novel in novels_data:
        novel_slug = novel['slug']
        novel_config = load_novel_config(novel_slug)
        
        # Skip novels that don't allow indexing
        if novel_config.get('seo', {}).get('allow_indexing') is False:
            continue
            
        available_languages = get_available_languages(novel_slug)
        
        for lang in available_languages:
            # Add TOC pages
            sitemap_entries.append(f"""    <url>
        <loc>{site_url}/{novel_slug}/{lang}/toc/</loc>
        <changefreq>weekly</changefreq>
        <priority>0.8</priority>
    </url>""")
            
            # Add tag index pages
            sitemap_entries.append(f"""    <url>
        <loc>{site_url}/{novel_slug}/{lang}/tags/</loc>
        <changefreq>monthly</changefreq>
        <priority>0.6</priority>
    </url>""")
            
            # Add individual chapters
            all_chapters = []
            for arc in novel.get("arcs", []):
                all_chapters.extend(arc.get("chapters", []))
            
            for chapter in all_chapters:
                chapter_id = chapter["id"]
                try:
                    chapter_content_md, chapter_metadata = load_chapter_content(novel_slug, chapter_id, lang)
                    
                    # Skip draft chapters unless include_drafts is True
                    if is_chapter_draft(chapter_metadata) and not INCLUDE_DRAFTS:
                        continue
                    
                    # Skip chapters that don't allow indexing, are password-protected, or are hidden
                    chapter_allow_indexing = chapter_metadata.get('seo', {}).get('allow_indexing')
                    is_password_protected = 'password' in chapter_metadata and chapter_metadata['password']
                    is_hidden = is_chapter_hidden(chapter_metadata)
                    
                    if chapter_allow_indexing is False or is_password_protected or is_hidden:
                        continue
                    
                    # Get published date if available
                    lastmod = ""
                    if chapter_metadata.get('published'):
                        try:
                            # Try to parse the date
                            pub_date = datetime.strptime(chapter_metadata['published'], '%Y-%m-%d')
                            lastmod = f"\n        <lastmod>{pub_date.strftime('%Y-%m-%d')}</lastmod>"
                        except:
                            pass
                    
                    sitemap_entries.append(f"""    <url>
        <loc>{site_url}/{novel_slug}/{lang}/{chapter_id}/</loc>
        <changefreq>monthly</changefreq>
        <priority>0.7</priority>{lastmod}
    </url>""")
                    
                except:
                    # Skip chapters that don't exist for this language
                    continue
            
            # Add tag pages
            tags_data = collect_tags_for_novel(novel_slug, lang)
            for tag in tags_data.keys():
                tag_slug = slugify_tag(tag)
                sitemap_entries.append(f"""    <url>
        <loc>{site_url}/{novel_slug}/{lang}/tags/{tag_slug}/</loc>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>""")
    
    sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(sitemap_entries)}
</urlset>"""
    
    return sitemap_content

def generate_robots_txt(site_config, novels_data):
    """Generate robots.txt file based on site and story configurations"""
    robots_content = ["# Robots.txt for Web Novel Static Generator"]
    
    # Add sitemap reference
    site_url = site_config.get('site_url', '').rstrip('/')
    if site_url:
        robots_content.append(f"Sitemap: {site_url}/sitemap.xml")
        robots_content.append("")
    
    # Check site-wide indexing settings
    site_allow_indexing = site_config.get('seo', {}).get('allow_indexing', True)
    
    if not site_allow_indexing:
        # If site doesn't allow indexing, disallow all
        robots_content.extend([
            "User-agent: *",
            "Disallow: /",
            ""
        ])
    else:
        robots_content.extend([
            "User-agent: *",
            "Allow: /",
            ""
        ])
        
        # Add disallow rules for specific novels or chapters that don't allow indexing
        disallowed_paths = []
        
        for novel in novels_data:
            novel_slug = novel['slug']
            novel_config = load_novel_config(novel_slug)
            
            # Check novel-level indexing settings
            novel_allow_indexing = novel_config.get('seo', {}).get('allow_indexing')
            if novel_allow_indexing is False:
                disallowed_paths.append(f"Disallow: /{novel_slug}/")
                continue
            
            # Check individual chapters for indexing settings
            available_languages = get_available_languages(novel_slug)
            for lang in available_languages:
                all_chapters = []
                for arc in novel.get("arcs", []):
                    all_chapters.extend(arc.get("chapters", []))
                
                for chapter in all_chapters:
                    chapter_id = chapter["id"]
                    try:
                        chapter_content_md, chapter_metadata = load_chapter_content(novel_slug, chapter_id, lang)
                        
                        # Skip draft chapters unless include_drafts is True
                        if is_chapter_draft(chapter_metadata) and not INCLUDE_DRAFTS:
                            continue
                        
                        # Check chapter-level indexing
                        chapter_allow_indexing = chapter_metadata.get('seo', {}).get('allow_indexing')
                        if chapter_allow_indexing is False:
                            disallowed_paths.append(f"Disallow: /{novel_slug}/{lang}/{chapter_id}/")
                        
                        # Also disallow password-protected and hidden content
                        if 'password' in chapter_metadata and chapter_metadata['password']:
                            disallowed_paths.append(f"Disallow: /{novel_slug}/{lang}/{chapter_id}/")
                        
                        # Disallow hidden chapters
                        if is_chapter_hidden(chapter_metadata):
                            disallowed_paths.append(f"Disallow: /{novel_slug}/{lang}/{chapter_id}/")
                            
                    except:
                        # Skip chapters that don't exist for this language
                        continue
        
        # Add all disallow rules
        if disallowed_paths:
            robots_content.extend(disallowed_paths)
            robots_content.append("")
    
    robots_content.append("# Generated by Web Novel Static Generator")
    
    return "\n".join(robots_content)

def load_site_config():
    """Load global site configuration"""
    config_file = "site_config.yaml"
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}

def build_social_meta(site_config, novel_config, chapter_metadata, page_type, title, url):
    """Build social media metadata for a page"""
    social_meta = {}
    
    # Determine social title
    if 'social_embeds' in chapter_metadata and 'title' in chapter_metadata['social_embeds']:
        social_meta['title'] = chapter_metadata['social_embeds']['title']
    elif page_type == 'chapter':
        social_meta['title'] = title
    elif page_type == 'toc':
        social_meta['title'] = f"{novel_config.get('title', '')} - Table of Contents"
    else:
        social_meta['title'] = title
    
    # Apply title format if specified
    title_format = site_config.get('social_embeds', {}).get('title_format', '{title}')
    social_meta['title'] = title_format.format(title=social_meta['title'])
    
    # Determine social description
    if 'social_embeds' in chapter_metadata and 'description' in chapter_metadata['social_embeds']:
        social_meta['description'] = chapter_metadata['social_embeds']['description']
    elif novel_config.get('social_embeds', {}).get('description'):
        social_meta['description'] = novel_config['social_embeds']['description']
    else:
        social_meta['description'] = site_config.get('social_embeds', {}).get('default_description', site_config.get('site_description', ''))
    
    # Determine social image (absolute URL)
    site_url = site_config.get('site_url', '').rstrip('/')
    if 'social_embeds' in chapter_metadata and 'image' in chapter_metadata['social_embeds']:
        image_path = chapter_metadata['social_embeds']['image']
    elif novel_config.get('social_embeds', {}).get('image'):
        image_path = novel_config['social_embeds']['image']
    else:
        image_path = site_config.get('social_embeds', {}).get('default_image', '/static/images/default-social.jpg')
    
    # Convert to absolute URL if relative
    if image_path.startswith('/'):
        social_meta['image'] = site_url + image_path
    else:
        social_meta['image'] = image_path
    
    # Set URL
    social_meta['url'] = url
    
    # Build keywords
    keywords = []
    if 'social_embeds' in chapter_metadata and 'keywords' in chapter_metadata['social_embeds']:
        keywords.extend(chapter_metadata['social_embeds']['keywords'])
    elif novel_config.get('social_embeds', {}).get('keywords'):
        keywords.extend(novel_config['social_embeds']['keywords'])
    
    social_meta['keywords'] = ', '.join(keywords) if keywords else None
    
    return social_meta

def generate_image_hash(file_path, length=8):
    """Generate a partial hash of an image file for consistent naming"""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        # Read in chunks to handle large files efficiently
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:length]

def build_seo_meta(site_config, novel_config, chapter_metadata, page_type):
    """Build SEO metadata for a page"""
    seo_meta = {}
    
    # Determine if indexing is allowed (chapter > story > site)
    if 'seo' in chapter_metadata and 'allow_indexing' in chapter_metadata['seo']:
        seo_meta['allow_indexing'] = chapter_metadata['seo']['allow_indexing']
    elif novel_config.get('seo', {}).get('allow_indexing') is not None:
        seo_meta['allow_indexing'] = novel_config['seo']['allow_indexing']
    else:
        seo_meta['allow_indexing'] = site_config.get('seo', {}).get('allow_indexing', True)
    
    # Determine meta description
    if 'seo' in chapter_metadata and 'meta_description' in chapter_metadata['seo']:
        seo_meta['meta_description'] = chapter_metadata['seo']['meta_description']
    elif novel_config.get('seo', {}).get('meta_description'):
        seo_meta['meta_description'] = novel_config['seo']['meta_description']
    else:
        seo_meta['meta_description'] = site_config.get('site_description', '')
    
    return seo_meta

def process_cover_art(novel_slug, novel_config):
    """Process cover art images by copying them to static/images with hash-based filenames"""
    processed_images = {}
    
    # Ensure static/images directory exists
    images_dir = os.path.join(BUILD_DIR, "static", "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # Process story cover art
    if novel_config.get('front_page', {}).get('cover_art'):
        source_path = os.path.join(CONTENT_DIR, novel_slug, novel_config['front_page']['cover_art'])
        if os.path.exists(source_path):
            # Generate hash-based filename with original name
            original_filename = os.path.basename(source_path)
            file_name, file_extension = os.path.splitext(original_filename)
            file_hash = generate_image_hash(source_path)
            unique_filename = f"{file_hash}-{file_name}{file_extension}"
            dest_path = os.path.join(images_dir, unique_filename)
            
            # Copy the image
            shutil.copy2(source_path, dest_path)
            
            # Store the processed path
            processed_images['story_cover'] = f"static/images/{unique_filename}"
    
    # Process arc cover art
    if novel_config.get('arcs'):
        for i, arc in enumerate(novel_config['arcs']):
            if arc.get('cover_art'):
                source_path = os.path.join(CONTENT_DIR, novel_slug, arc['cover_art'])
                if os.path.exists(source_path):
                    # Generate hash-based filename with original name
                    original_filename = os.path.basename(source_path)
                    file_name, file_extension = os.path.splitext(original_filename)
                    file_hash = generate_image_hash(source_path)
                    unique_filename = f"{file_hash}-{file_name}{file_extension}"
                    dest_path = os.path.join(images_dir, unique_filename)
                    
                    # Copy the image
                    shutil.copy2(source_path, dest_path)
                    
                    # Store the processed path
                    processed_images[f'arc_{i}_cover'] = f"static/images/{unique_filename}"
    
    return processed_images

def load_authors_config():
    """Load authors configuration from authors.yaml"""
    authors_file = "authors.yaml"
    if os.path.exists(authors_file):
        with open(authors_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            return config.get('authors', {})
    return {}

def find_author_username(author_name, authors_config):
    """Find the username for an author by their display name"""
    for username, author_info in authors_config.items():
        if author_info.get('name') == author_name:
            return username
    return None

def collect_author_contributions(all_novels_data):
    """Collect all stories and chapters that each author contributed to"""
    author_contributions = {}
    
    for novel in all_novels_data:
        novel_slug = novel['slug']
        novel_title = novel.get('title', novel_slug)
        novel_config = load_novel_config(novel_slug)
        
        # Check story-level author
        story_author = novel_config.get('author', {}).get('name')
        if story_author:
            if story_author not in author_contributions:
                author_contributions[story_author] = {'stories': [], 'chapters': []}
            author_contributions[story_author]['stories'].append({
                'slug': novel_slug,
                'title': novel_title,
                'description': novel.get('description'),
                'role': 'Author'
            })
        
        # Check each chapter for author/translator contributions (use primary language only to avoid duplicates)
        primary_lang = novel_config.get('primary_language', 'en')
        for arc in novel.get('arcs', []):
            for chapter in arc.get('chapters', []):
                chapter_id = chapter['id']
                chapter_title = chapter['title']
                
                # Load chapter content to get front matter (use primary language only)
                try:
                    chapter_content, chapter_metadata = load_chapter_content(novel_slug, chapter_id, primary_lang)
                    
                    # Check chapter author
                    if chapter_metadata.get('author'):
                        author_name = chapter_metadata['author']
                        if author_name not in author_contributions:
                            author_contributions[author_name] = {'stories': [], 'chapters': []}
                        author_contributions[author_name]['chapters'].append({
                            'novel_slug': novel_slug,
                            'novel_title': novel_title,
                            'chapter_id': chapter_id,
                            'title': chapter_title,
                            'role': 'Author',
                            'published': chapter_metadata.get('published')
                        })
                    
                    # Check chapter translator
                    if chapter_metadata.get('translator'):
                        translator_name = chapter_metadata['translator']
                        if translator_name not in author_contributions:
                            author_contributions[translator_name] = {'stories': [], 'chapters': []}
                        author_contributions[translator_name]['chapters'].append({
                            'novel_slug': novel_slug,
                            'novel_title': novel_title,
                            'chapter_id': chapter_id,
                            'title': chapter_title,
                            'role': 'Translator',
                            'published': chapter_metadata.get('published')
                        })
                except:
                    # Skip chapters that can't be loaded
                    continue
    
    return author_contributions

def get_non_hidden_chapters(novel_config, novel_slug, language='en', include_drafts=False):
    """Get list of chapters that are not hidden, password protected, or drafts"""
    visible_chapters = []
    
    for arc in novel_config.get('arcs', []):
        arc_chapters = []
        for chapter in arc.get('chapters', []):
            chapter_id = chapter['id']
            
            # Load chapter content to check if it's hidden, password protected, or draft
            try:
                chapter_content, chapter_metadata = load_chapter_content(novel_slug, chapter_id, language)
                
                # Skip if chapter should be skipped
                if should_skip_chapter(chapter_metadata, include_drafts):
                    continue
                
                arc_chapters.append({
                    'id': chapter_id,
                    'title': chapter['title'],
                    'content': chapter_content,
                    'metadata': chapter_metadata
                })
            except:
                # Skip chapters that can't be loaded
                continue
        
        if arc_chapters:  # Only include arcs with visible chapters
            visible_chapters.append({
                'title': arc['title'],
                'cover_art': arc.get('cover_art'),
                'chapters': arc_chapters
            })
    
    return visible_chapters


def generate_story_epub(novel_slug, novel_config, site_config, novel_data=None, language='en'):
    """Generate EPUB for entire story"""
    if not _check_ebooklib():
        return False
    
    # Check if EPUB generation is enabled
    if not site_config.get('pdf_epub', {}).get('generate_enabled', True):
        return False
    if not site_config.get('pdf_epub', {}).get('epub_enabled', True):
        return False
    if not novel_config.get('downloads', {}).get('epub_enabled', True):
        return False
    
    try:
        # Get non-hidden chapters for the specified language
        chapters_data = get_non_hidden_chapters(novel_config, novel_slug, language, INCLUDE_DRAFTS)
        if not chapters_data:
            return False
        
        # Create EPUB book
        import ebooklib
        from ebooklib import epub
        book = epub.EpubBook()
        
        # Set metadata
        story_title = novel_config.get('title', novel_slug)
        book.set_identifier(f'web-novel-{novel_slug}')
        book.set_title(story_title)
        book.set_language('en')
        
        author_name = novel_config.get('author', {}).get('name', 'Unknown Author')
        book.add_author(author_name)
        
        description = novel_config.get('description', '')
        if description:
            book.add_metadata('DC', 'description', description)
        
        # Track added images to avoid duplicates
        added_images = {}
        
        # Add cover image if available - use processed image paths if available
        cover_art_path = None
        if novel_data and novel_data.get('front_page', {}).get('cover_art'):
            cover_art_path = novel_data['front_page']['cover_art']
        elif novel_config.get('front_page', {}).get('cover_art'):
            cover_art_path = novel_config['front_page']['cover_art']
            
        if cover_art_path:
            cover_image_absolute = os.path.join(BUILD_DIR, cover_art_path)
            if os.path.exists(cover_image_absolute):
                # Determine image type
                image_ext = os.path.splitext(cover_art_path)[1].lower()
                image_type = 'image/jpeg' if image_ext in ['.jpg', '.jpeg'] else 'image/png'
                
                # Read and add cover image
                with open(cover_image_absolute, 'rb') as img_file:
                    cover_image = img_file.read()
                
                # Create proper cover filename with extension
                cover_filename = f"cover{image_ext}"
                book.set_cover(cover_filename, cover_image)
                added_images[cover_art_path] = cover_filename
        
        # Create and add CSS file for styling
        css_content = """
        body { font-family: Georgia, serif; line-height: 1.6; }
        h1 { border-bottom: 2px solid #333; padding-bottom: 0.5em; }
        p { margin-bottom: 1em; text-align: justify; }
        img { max-width: 100%; height: auto; display: block; margin: 1.5em auto; text-align: center; }
        p img { margin: 1.5em auto; }
        """
        
        css_item = epub.EpubItem(
            uid="style_default",
            file_name="style/default.css",
            media_type="text/css",
            content=css_content
        )
        book.add_item(css_item)
        
        # Add chapters to EPUB
        spine = ['nav']
        toc = []
        
        for arc_index, arc in enumerate(chapters_data):
            arc_chapters = []
            
            for chapter_index, chapter in enumerate(arc['chapters']):
                # Create EPUB chapter
                chapter_id = f"chapter_{arc_index}_{chapter_index}"
                chapter_file = f"chapter_{arc_index}_{chapter_index}.xhtml"
                
                # Try to load processed HTML content first, fall back to markdown
                chapter_html = load_processed_chapter_content(novel_slug, chapter['id'], language)
                if not chapter_html:
                    # Fallback to markdown processing
                    chapter_html = markdown.markdown(chapter['content'])
                
                # Process images in chapter content
                chapter_html = process_epub_images(chapter_html, novel_slug, book, added_images)
                
                # Create EPUB chapter content
                epub_chapter = epub.EpubHtml(
                    title=chapter['title'],
                    file_name=chapter_file,
                    lang='en'
                )
                
                epub_chapter.content = f"""
                <html xmlns="http://www.w3.org/1999/xhtml">
                <head>
                    <title>{chapter['title']}</title>
                    <link rel="stylesheet" type="text/css" href="../style/default.css"/>
                </head>
                <body>
                    <h1>{chapter['title']}</h1>
                    {chapter_html}
                </body>
                </html>
                """
                
                # Link the CSS file to this chapter
                epub_chapter.add_item(css_item)
                book.add_item(epub_chapter)
                spine.append(epub_chapter)
                arc_chapters.append(epub_chapter)
            
            # Add arc to TOC if multiple arcs
            if len(chapters_data) > 1:
                toc.append((epub.Section(arc['title']), arc_chapters))
            else:
                toc.extend(arc_chapters)
        
        # Set TOC and spine
        book.toc = toc
        book.spine = spine
        
        # Add default navigation files
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # Ensure output directory exists
        epub_dir = os.path.join(BUILD_DIR, "static", "epub")
        os.makedirs(epub_dir, exist_ok=True)
        
        # Write EPUB file with language suffix if not English
        if language == 'en':
            epub_filename = f"{novel_slug}.epub"
        else:
            epub_filename = f"{novel_slug}_{language}.epub"
        epub_path = os.path.join(epub_dir, epub_filename)
        epub.write_epub(epub_path, book, {})
        
        return True
    except Exception as e:
        print(f"Error generating EPUB for {novel_slug}: {e}")
        return False

def generate_arc_epub(novel_slug, novel_config, site_config, arc_index, novel_data=None, language='en'):
    """Generate EPUB for a specific arc"""
    if not _check_ebooklib():
        return False
    
    # Check if EPUB generation is enabled
    if not site_config.get('pdf_epub', {}).get('generate_enabled', True):
        return False
    if not site_config.get('pdf_epub', {}).get('epub_enabled', True):
        return False
    if not novel_config.get('downloads', {}).get('epub_enabled', True):
        return False
    if not novel_config.get('downloads', {}).get('include_arcs', True):
        return False
    
    try:
        # Get all chapters and filter for this arc
        all_chapters = get_non_hidden_chapters(novel_config, novel_slug, 'en', INCLUDE_DRAFTS)
        if not all_chapters or arc_index >= len(all_chapters):
            return False
        
        # Get the specific arc
        arc_data = all_chapters[arc_index]
        if not arc_data['chapters']:
            return False
        
        # Create EPUB book
        import ebooklib
        from ebooklib import epub
        book = epub.EpubBook()
        
        # Set metadata
        arc_title = arc_data['title']
        story_title = novel_config.get('title', novel_slug)
        epub_title = f"{story_title} - {arc_title}"
        
        book.set_identifier(f'web-novel-{novel_slug}-arc-{arc_index}')
        book.set_title(epub_title)
        book.set_language('en')
        
        author_name = novel_config.get('author', {}).get('name', 'Unknown Author')
        book.add_author(author_name)
        
        description = novel_config.get('description', '')
        if description:
            book.add_metadata('DC', 'description', f"{description} - {arc_title}")
        
        # Track added images to avoid duplicates
        added_images = {}
        
        # Add cover image - prefer arc cover, fall back to story cover
        cover_art_path = None
        # Try to get arc cover from processed data first
        if novel_data and novel_data.get('arcs') and arc_index < len(novel_data['arcs']):
            cover_art_path = novel_data['arcs'][arc_index].get('cover_art')
        
        # Fall back to story cover if no arc cover
        if not cover_art_path:
            if novel_data and novel_data.get('front_page', {}).get('cover_art'):
                cover_art_path = novel_data['front_page']['cover_art']
            elif novel_config.get('front_page', {}).get('cover_art'):
                cover_art_path = novel_config['front_page']['cover_art']
                
        if cover_art_path:
            cover_image_absolute = os.path.join(BUILD_DIR, cover_art_path)
            if os.path.exists(cover_image_absolute):
                # Determine image type
                image_ext = os.path.splitext(cover_art_path)[1].lower()
                image_type = 'image/jpeg' if image_ext in ['.jpg', '.jpeg'] else 'image/png'
                
                # Read and add cover image
                with open(cover_image_absolute, 'rb') as img_file:
                    cover_image = img_file.read()
                
                # Create proper cover filename with extension
                cover_filename = f"cover{image_ext}"
                book.set_cover(cover_filename, cover_image)
                added_images[cover_art_path] = cover_filename
        
        # Create and add CSS file for styling
        css_content = """
        body { font-family: Georgia, serif; line-height: 1.6; }
        h1 { border-bottom: 2px solid #333; padding-bottom: 0.5em; }
        p { margin-bottom: 1em; text-align: justify; }
        img { max-width: 100%; height: auto; display: block; margin: 1.5em auto; text-align: center; }
        p img { margin: 1.5em auto; }
        """
        
        css_item = epub.EpubItem(
            uid="style_default",
            file_name="style/default.css",
            media_type="text/css",
            content=css_content
        )
        book.add_item(css_item)
        
        # Add chapters to EPUB
        spine = ['nav']
        toc = []
        
        for chapter_index, chapter in enumerate(arc_data['chapters']):
            # Create EPUB chapter
            chapter_id = f"chapter_{chapter_index}"
            chapter_file = f"chapter_{chapter_index}.xhtml"
            
            # Try to load processed HTML content first, fall back to markdown
            chapter_html = load_processed_chapter_content(novel_slug, chapter['id'], language)
            if not chapter_html:
                # Fallback to markdown processing
                chapter_html = markdown.markdown(chapter['content'])
            
            # Process images in chapter content
            chapter_html = process_epub_images(chapter_html, novel_slug, book, added_images)
            
            # Create EPUB chapter content
            epub_chapter = epub.EpubHtml(
                title=chapter['title'],
                file_name=chapter_file,
                lang='en'
            )
            
            epub_chapter.content = f"""
            <html xmlns="http://www.w3.org/1999/xhtml">
            <head>
                <title>{chapter['title']}</title>
                <link rel="stylesheet" type="text/css" href="../style/default.css"/>
            </head>
            <body>
                <h1>{chapter['title']}</h1>
                {chapter_html}
            </body>
            </html>
            """
            
            # Link the CSS file to this chapter
            epub_chapter.add_item(css_item)
            book.add_item(epub_chapter)
            spine.append(epub_chapter)
            toc.append(epub_chapter)
        
        # Set TOC and spine
        book.toc = toc
        book.spine = spine
        
        # Add default navigation files
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # Ensure output directory exists
        epub_dir = os.path.join(BUILD_DIR, "static", "epub")
        os.makedirs(epub_dir, exist_ok=True)
        
        # Generate EPUB with arc-specific filename and language suffix if not English
        arc_slug = arc_title.lower().replace(' ', '-').replace(':', '').replace(',', '')
        if language == 'en':
            epub_filename = f"{novel_slug}-{arc_slug}.epub"
        else:
            epub_filename = f"{novel_slug}-{arc_slug}_{language}.epub"
        epub_path = os.path.join(epub_dir, epub_filename)
        epub.write_epub(epub_path, book, {})
        
        return True
    except Exception as e:
        print(f"Error generating EPUB for {novel_slug} arc {arc_index}: {e}")
        return False

def load_processed_chapter_content(novel_slug, chapter_id, language='en'):
    """Load processed chapter content from the built HTML files"""
    chapter_path = os.path.join(BUILD_DIR, novel_slug, language, chapter_id, 'index.html')
    if not os.path.exists(chapter_path):
        return None
    
    try:
        with open(chapter_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Extract just the chapter content between the chapter-content div
        import re
        # Look for the inner content wrapper
        content_match = re.search(r'<div id="chapter-content-wrapper"[^>]*>(.*?)</div>', html_content, re.DOTALL)
        if content_match:
            inner_content = content_match.group(1).strip()
            # Remove the duplicate h1 title if present (it's already in the EPUB structure)
            inner_content = re.sub(r'<h1[^>]*>.*?</h1>', '', inner_content, count=1)
            return inner_content.strip()
        
        # Fallback: try the outer chapter-content div
        content_match = re.search(r'<div class="chapter-content">(.*?)</div>', html_content, re.DOTALL)
        if content_match:
            return content_match.group(1).strip()
        
        # Fallback: try to extract content between main tags
        main_match = re.search(r'<main[^>]*>(.*?)</main>', html_content, re.DOTALL)
        if main_match:
            content = main_match.group(1)
            # Remove navigation and other non-content elements, keep just the chapter text
            content = re.sub(r'<nav[^>]*>.*?</nav>', '', content, flags=re.DOTALL)
            content = re.sub(r'<div class="chapter-nav[^"]*">.*?</div>', '', content, flags=re.DOTALL)
            content = re.sub(r'<div class="comments-section">.*?</div>', '', content, flags=re.DOTALL)
            return content.strip()
        
        return None
    except Exception as e:
        print(f"Error loading processed chapter content for {chapter_id}: {e}")
        return None

def process_epub_images(content_html, novel_slug, book, added_images):
    """Process images in chapter content and add them to EPUB"""
    import re
    
    # Import EPUB library
    try:
        import ebooklib
        from ebooklib import epub
    except ImportError:
        print("ebooklib not available for image processing")
        return content_html
    
    # Find all image references in the HTML
    img_pattern = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>'
    
    def replace_image(match):
        img_tag = match.group(0)
        src = match.group(1)
        
        # Skip external images
        if src.startswith(('http://', 'https://', '//')):
            return img_tag
        
        # Convert relative path to absolute
        if src.startswith('../'):
            # Remove leading ../../../ and reconstruct path
            clean_src = src.replace('../', '')  
            image_absolute = os.path.join(BUILD_DIR, clean_src)
        else:
            image_absolute = os.path.join(BUILD_DIR, src)
        
        if not os.path.exists(image_absolute):
            return img_tag  # Keep original if image not found
        
        # Check if image already added
        if src in added_images:
            epub_filename = added_images[src]
        else:
            # Add image to EPUB
            try:
                with open(image_absolute, 'rb') as img_file:
                    image_data = img_file.read()
                
                # Generate EPUB-friendly filename
                image_name = os.path.basename(src)
                image_ext = os.path.splitext(image_name)[1].lower()
                image_type = 'image/jpeg' if image_ext in ['.jpg', '.jpeg'] else 'image/png'
                
                # Create unique filename for EPUB
                epub_filename = f"images/{len(added_images)}_{image_name}"
                
                # Create EPUB image item
                epub_image = epub.EpubImage(
                    uid=f"img_{len(added_images)}",
                    file_name=epub_filename,
                    media_type=image_type,
                    content=image_data
                )
                
                book.add_item(epub_image)
                added_images[src] = epub_filename
                
            except Exception as e:
                print(f"Error adding image {src} to EPUB: {e}")
                return img_tag
        
        # Replace src with EPUB path (no ../ prefix needed for EPUB internal files)
        new_img_tag = img_tag.replace(f'src="{src}"', f'src="{epub_filename}"')
        new_img_tag = new_img_tag.replace(f"src='{src}'", f"src='{epub_filename}'")
        
        return new_img_tag
    
    # Process all images in the content
    processed_content = re.sub(img_pattern, replace_image, content_html)
    return processed_content

def update_toc_with_downloads(novel, novel_slug, novel_config, site_config, lang):
    """Update TOC page with download links after files are generated"""
    # Read the existing TOC file
    novel_dir = os.path.join(BUILD_DIR, novel_slug)
    lang_dir = os.path.join(novel_dir, lang)
    toc_dir = os.path.join(lang_dir, "toc")
    toc_file = os.path.join(toc_dir, "index.html")
    
    if not os.path.exists(toc_file):
        return
    
    # Generate download links data
    download_links = generate_download_links(novel_slug, novel_config, site_config, lang)
    
    # Prepare all the same data that was used for original TOC generation
    available_languages = novel_config.get('languages', {}).get('available', ['en'])
    
    # Build social metadata for TOC
    toc_url = f"{site_config.get('site_url', '').rstrip('/')}/{novel_slug}/{lang}/toc/"
    toc_social_meta = build_social_meta(site_config, novel_config, {}, 'toc', f"{novel.get('title', '')} - Table of Contents", toc_url)
    toc_seo_meta = build_seo_meta(site_config, novel_config, {}, 'toc')
    
    # Build footer data for TOC
    footer_data = build_footer_content(site_config, novel_config, 'toc')
    
    # Build comments configuration for TOC
    toc_comments_enabled = should_enable_comments(site_config, novel_config, {}, 'toc')
    comments_config = build_comments_config(site_config)
    
    # Filter out hidden chapters for TOC display
    filtered_novel = filter_hidden_chapters_from_novel(novel, novel_slug, lang)
    
    # Calculate story length statistics
    story_length_stats = calculate_story_length_stats(novel_slug, lang)
    
    # Determine which unit to display based on configuration
    length_config = novel_config.get('length_display', {})
    language_units = length_config.get('language_units', {})
    default_unit = length_config.get('default_unit', 'words')
    
    # Check for language-specific override, fall back to default
    display_unit = language_units.get(lang, default_unit)
    
    if display_unit == 'characters':
        story_length_count = story_length_stats['characters']
        story_length_unit = 'characters'
    else:
        story_length_count = story_length_stats['words']
        story_length_unit = 'words'
    
    # Re-generate the TOC page with download links
    with open(toc_file, "w", encoding='utf-8') as f:
        f.write(render_template("toc.html", 
                               novel=filtered_novel, 
                               current_language=lang, 
                               available_languages=available_languages,
                               story_length_count=story_length_count,
                               story_length_unit=story_length_unit,
                               site_name=site_config.get('site_name', 'Web Novel Collection'),
                               social_title=toc_social_meta['title'],
                               social_description=toc_social_meta['description'], 
                               social_image=toc_social_meta['image'],
                               social_url=toc_social_meta['url'],
                               seo_meta_description=toc_seo_meta.get('meta_description'),
                               seo_keywords=toc_social_meta.get('keywords'),
                               allow_indexing=toc_seo_meta.get('allow_indexing', True),
                               twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle'),
                               footer_data=footer_data,
                               download_links=download_links,
                               comments_enabled=toc_comments_enabled,
                               comments_repo=comments_config['repo'],
                               comments_issue_term=comments_config['issue_term'],
                               comments_label=comments_config['label'],
                               comments_theme=comments_config['theme']))

def generate_download_links(novel_slug, novel_config, site_config, language='en'):
    """Generate download links data for TOC template"""
    download_links = {}
    
    # Check if downloads are enabled
    if not site_config.get('epub', {}).get('generate_enabled', True):
        return None
    if not novel_config.get('downloads', {}).get('epub_enabled', True):
        return None
    
    # Generate language-specific filename suffix
    lang_suffix = f"_{language}" if language != 'en' else ""
    
    # Full story downloads
    if site_config.get('epub', {}).get('generate_enabled', True) and novel_config.get('downloads', {}).get('epub_enabled', True):
        epub_filename = f"{novel_slug}{lang_suffix}.epub"
        epub_path = f"../../../static/epub/{epub_filename}"
        if os.path.exists(os.path.join(BUILD_DIR, "static", "epub", epub_filename)):
            download_links['story_epub'] = epub_path
    
    # Arc-specific downloads
    if novel_config.get('downloads', {}).get('include_arcs', True):
        all_chapters = get_non_hidden_chapters(novel_config, novel_slug, 'en', INCLUDE_DRAFTS)
        arc_downloads = []
        
        for arc_index, arc in enumerate(all_chapters):
            if not arc['chapters']:  # Skip empty arcs
                continue
                
            arc_download = {'title': arc['title']}
            arc_title_slug = arc['title'].lower().replace(' ', '-').replace(':', '').replace(',', '')
            
            
            # Check for arc EPUB
            if site_config.get('epub', {}).get('generate_enabled', True) and novel_config.get('downloads', {}).get('epub_enabled', True):
                arc_epub_filename = f"{novel_slug}-{arc_title_slug}{lang_suffix}.epub"
                arc_epub_path = f"../../../static/epub/{arc_epub_filename}"
                if os.path.exists(os.path.join(BUILD_DIR, "static", "epub", arc_epub_filename)):
                    arc_download['epub'] = arc_epub_path
            
            # Only add arc if it has at least one download
            if 'epub' in arc_download:
                arc_downloads.append(arc_download)
        
        if arc_downloads:
            download_links['arcs'] = arc_downloads
    
    # Return None if no downloads available
    return download_links if download_links else None

def load_novel_config(novel_slug):
    """Load configuration for a specific novel"""
    config_file = os.path.join(CONTENT_DIR, novel_slug, "config.yaml")
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}

def should_show_tags(novel_config, chapter_front_matter):
    """Determine if tags should be shown based on config and front matter"""
    # Check front matter override first
    if 'show_tags' in chapter_front_matter:
        return chapter_front_matter['show_tags']
    
    # Fall back to novel config
    return novel_config.get('display', {}).get('show_tags', True)

def should_show_metadata(novel_config, chapter_front_matter):
    """Determine if metadata should be shown based on config and front matter"""
    # Check front matter override first
    if 'show_metadata' in chapter_front_matter:
        return chapter_front_matter['show_metadata']
    
    # Fall back to novel config
    return novel_config.get('display', {}).get('show_metadata', True)

def should_show_translation_notes(novel_config, chapter_front_matter):
    """Determine if translation notes should be shown based on config and front matter"""
    # Check front matter override first
    if 'show_translation_notes' in chapter_front_matter:
        return chapter_front_matter['show_translation_notes']
    
    # Fall back to novel config
    return novel_config.get('display', {}).get('show_translation_notes', True)

def should_enable_comments(site_config, novel_config, chapter_metadata, page_type):
    """Determine if comments should be enabled based on config hierarchy"""
    # Check chapter-level override first
    if 'comments' in chapter_metadata and 'enabled' in chapter_metadata['comments']:
        return chapter_metadata['comments']['enabled']
    
    # Check story-level config based on page type
    if page_type == 'chapter' and novel_config.get('comments', {}).get('chapter_comments') is not None:
        return novel_config['comments']['chapter_comments']
    elif page_type == 'toc' and novel_config.get('comments', {}).get('toc_comments') is not None:
        return novel_config['comments']['toc_comments']
    elif novel_config.get('comments', {}).get('enabled') is not None:
        return novel_config['comments']['enabled']
    
    # Fall back to site config
    return site_config.get('comments', {}).get('enabled', False)

def build_comments_config(site_config):
    """Build comments configuration for templates"""
    comments_config = site_config.get('comments', {})
    
    return {
        'repo': comments_config.get('utterances_repo', ''),
        'issue_term': comments_config.get('utterances_issue_term', 'pathname'),
        'label': comments_config.get('utterances_label', 'comment'),
        'theme': comments_config.get('utterances_theme', 'github-light')
    }

def is_chapter_hidden(chapter_metadata):
    """Check if chapter is marked as hidden"""
    return chapter_metadata.get('hidden', False)

def is_chapter_draft(chapter_metadata):
    """Check if a chapter is marked as a draft"""
    return chapter_metadata.get('draft', False)

def should_skip_chapter(chapter_metadata, include_drafts=False):
    """Check if a chapter should be skipped during generation"""
    if is_chapter_hidden(chapter_metadata):
        return True
    if is_chapter_draft(chapter_metadata) and not include_drafts:
        return True
    # Skip password-protected chapters
    if chapter_metadata.get('password'):
        return True
    return False

def get_navigation_chapters(novel_slug, all_chapters, current_chapter_id, lang):
    """Get previous and next chapters for navigation, skipping hidden chapters"""
    visible_chapters = []
    
    # Filter out hidden chapters from navigation
    for chapter in all_chapters:
        try:
            _, chapter_metadata = load_chapter_content(novel_slug, chapter['id'], lang)
            if not should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS):
                visible_chapters.append(chapter)
        except:
            # Include chapters that can't be loaded (they might exist in other languages)
            visible_chapters.append(chapter)
    
    # Find current chapter position in visible chapters
    current_index = -1
    for i, chapter in enumerate(visible_chapters):
        if chapter['id'] == current_chapter_id:
            current_index = i
            break
    
    if current_index == -1:
        # Current chapter is not in visible list (probably hidden), no navigation
        return None, None
    
    prev_chapter = visible_chapters[current_index - 1] if current_index > 0 else None
    next_chapter = visible_chapters[current_index + 1] if current_index < len(visible_chapters) - 1 else None
    
    return prev_chapter, next_chapter

def calculate_story_length_stats(novel_slug, lang):
    """Calculate total character and word count for all visible chapters in a story"""
    import re
    
    total_chars = 0
    total_words = 0
    novel_config = load_novel_config(novel_slug)
    
    # Get all chapters from the novel config
    all_chapters = []
    for arc in novel_config.get("arcs", []):
        all_chapters.extend(arc.get("chapters", []))
    
    for chapter in all_chapters:
        chapter_id = chapter["id"]
        try:
            chapter_content_md, chapter_metadata = load_chapter_content(novel_slug, chapter_id, lang)
            
            # Skip chapters that should be skipped
            if should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS):
                continue
            
            # Remove markdown formatting and count characters/words
            # Remove front matter (everything before the first ---\n)
            content_lines = chapter_content_md.split('\n')
            content_start = 0
            front_matter_count = 0
            
            for i, line in enumerate(content_lines):
                if line.strip() == '---':
                    front_matter_count += 1
                    if front_matter_count == 2:
                        content_start = i + 1
                        break
            
            # Get just the content without front matter
            content_only = '\n'.join(content_lines[content_start:])
            
            # Remove markdown formatting for accurate counting
            # Remove headers
            content_only = re.sub(r'^#+\s+', '', content_only, flags=re.MULTILINE)
            # Remove emphasis/bold
            content_only = re.sub(r'\*+([^*]+)\*+', r'\1', content_only)
            content_only = re.sub(r'_+([^_]+)_+', r'\1', content_only)
            # Remove links
            content_only = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', content_only)
            # Remove images
            content_only = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', content_only)
            # Remove extra whitespace but preserve word boundaries
            content_only = re.sub(r'\s+', ' ', content_only).strip()
            
            # Count characters (excluding spaces)
            char_count = len(re.sub(r'\s', '', content_only))
            total_chars += char_count
            
            # Count words (split by whitespace)
            if content_only.strip():
                word_count = len(content_only.split())
                total_words += word_count
            
        except:
            # Skip chapters that can't be loaded
            continue
    
    return {
        'characters': total_chars,
        'words': total_words
    }

def filter_hidden_chapters_from_novel(novel, novel_slug, lang):
    """Create a copy of novel data with hidden chapters filtered out for TOC display"""
    filtered_novel = novel.copy()
    filtered_arcs = []
    
    for arc in novel.get('arcs', []):
        filtered_chapters = []
        
        for chapter in arc.get('chapters', []):
            try:
                _, chapter_metadata = load_chapter_content(novel_slug, chapter['id'], lang)
                if not should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS):
                    # Add published date to chapter data for TOC display
                    enhanced_chapter = chapter.copy()
                    enhanced_chapter['published'] = chapter_metadata.get('published')
                    filtered_chapters.append(enhanced_chapter)
            except:
                # Include chapters that can't be loaded (they might exist in other languages)
                filtered_chapters.append(chapter)
        
        # Only include arcs that have visible chapters
        if filtered_chapters:
            filtered_arc = arc.copy()
            filtered_arc['chapters'] = filtered_chapters
            filtered_arcs.append(filtered_arc)
    
    filtered_novel['arcs'] = filtered_arcs
    return filtered_novel

def load_chapter_content(novel_slug, chapter_id, language='en'):
    """Load chapter content from markdown file with language support and front matter parsing"""
    # Try language-specific file first
    chapter_file = os.path.join(CONTENT_DIR, novel_slug, "chapters", language, f"{chapter_id}.md")
    if os.path.exists(chapter_file):
        with open(chapter_file, 'r', encoding='utf-8') as f:
            content = f.read()
            front_matter, markdown_content = parse_front_matter(content)
            return markdown_content, front_matter
    
    # Fallback to default language file (in root chapters folder)
    chapter_file = os.path.join(CONTENT_DIR, novel_slug, "chapters", f"{chapter_id}.md")
    if os.path.exists(chapter_file):
        with open(chapter_file, 'r', encoding='utf-8') as f:
            content = f.read()
            front_matter, markdown_content = parse_front_matter(content)
            return markdown_content, front_matter
    
    return f"# {chapter_id}\n\nContent not found for language: {language}.", {}

def get_available_languages(novel_slug):
    """Get list of available languages for a novel"""
    languages = ['en']  # Default language
    chapters_dir = os.path.join(CONTENT_DIR, novel_slug, "chapters")
    
    if os.path.exists(chapters_dir):
        for item in os.listdir(chapters_dir):
            item_path = os.path.join(chapters_dir, item)
            if os.path.isdir(item_path) and len(item) == 2:  # Assume 2-letter language codes
                languages.append(item)
    
    return sorted(set(languages))

def chapter_translation_exists(novel_slug, chapter_id, language):
    """Check if a chapter translation exists for a specific language"""
    chapter_file = os.path.join(CONTENT_DIR, novel_slug, "chapters", language, f"{chapter_id}.md")
    return os.path.exists(chapter_file)

def parse_front_matter(content):
    """Parse YAML front matter from markdown content"""
    front_matter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(front_matter_pattern, content, re.DOTALL)
    
    if match:
        try:
            front_matter = yaml.safe_load(match.group(1))
            markdown_content = match.group(2)
            return front_matter or {}, markdown_content
        except yaml.YAMLError:
            # If YAML parsing fails, treat the whole thing as markdown
            return {}, content
    else:
        # No front matter found
        return {}, content

def slugify_tag(tag):
    """Convert tag to filesystem-safe slug"""
    import unicodedata
    # Normalize unicode characters and convert to ASCII where possible
    normalized = unicodedata.normalize('NFKD', tag.lower().strip())
    # Keep unicode characters but remove problematic filesystem characters
    slug = re.sub(r'[<>:"/\\|?*]', '-', normalized)
    # Replace multiple spaces/hyphens with single hyphen
    slug = re.sub(r'[\s\-]+', '-', slug).strip('-')
    # If the slug is empty after processing, use a hash of the original
    if not slug:
        import hashlib
        slug = hashlib.md5(tag.encode('utf-8')).hexdigest()[:8]
    return slug

def collect_tags_for_novel(novel_slug, language):
    """Collect all tags from chapters in a specific language for a novel"""
    tags_data = {}  # tag -> list of chapters
    
    chapters_dir = os.path.join(CONTENT_DIR, novel_slug, "chapters", language)
    root_chapters_dir = os.path.join(CONTENT_DIR, novel_slug, "chapters")
    
    # Check language-specific directory first
    search_dirs = []
    if os.path.exists(chapters_dir):
        search_dirs.append((chapters_dir, language))
    elif os.path.exists(root_chapters_dir):
        search_dirs.append((root_chapters_dir, 'fallback'))
    
    for search_dir, dir_lang in search_dirs:
        if os.path.exists(search_dir):
            for filename in os.listdir(search_dir):
                if filename.endswith('.md'):
                    chapter_id = filename[:-3]  # Remove .md extension
                    chapter_file = os.path.join(search_dir, filename)
                    
                    with open(chapter_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        front_matter, _ = parse_front_matter(content)
                        
                        # Skip hidden chapters from tag collections
                        if is_chapter_hidden(front_matter):
                            continue
                        
                        chapter_tags = front_matter.get('tags', [])
                        chapter_title = front_matter.get('title', f'Chapter {chapter_id}')
                        
                        for tag in chapter_tags:
                            if tag not in tags_data:
                                tags_data[tag] = []
                            
                            tags_data[tag].append({
                                'id': chapter_id,
                                'title': chapter_title,
                                'filename': filename
                            })
    
    return tags_data

def extract_local_images(markdown_content):
    """Extract local image references from markdown content and HTML img tags"""
    local_images = []
    
    # Regex to match ![alt](path "title") or ![alt](path) 
    markdown_image_pattern = r'!\[([^\]]*)\]\(([^)]+?)(?:\s+"([^"]*)")?\)'
    markdown_matches = re.findall(markdown_image_pattern, markdown_content)
    
    for alt_text, image_path, title in markdown_matches:
        # Only process if it looks like a local file (no http/https, no leading /)
        if not image_path.startswith(('http://', 'https://', '/')):
            # Construct the title part separately to avoid f-string issues
            title_part = ""
            if title:
                title_part = f' "{title}"'
            
            local_images.append({
                'alt': alt_text,
                'original_path': image_path,
                'title': title or '',
                'full_match': f'![{alt_text}]({image_path}{title_part})',
                'type': 'markdown'
            })
    
    # Regex to match <img src="path" alt="alt" title="title" ... />
    html_image_pattern = r'<img\s+[^>]*src\s*=\s*["\']([^"\']+)["\'][^>]*>'
    html_matches = re.findall(html_image_pattern, markdown_content, re.IGNORECASE)
    
    for image_path in html_matches:
        # Only process if it looks like a local file (no http/https, no leading /)
        if not image_path.startswith(('http://', 'https://', '/')):
            # Find the full img tag to replace later
            full_match_pattern = r'<img\s+[^>]*src\s*=\s*["\']' + re.escape(image_path) + r'["\'][^>]*>'
            full_match = re.search(full_match_pattern, markdown_content, re.IGNORECASE)
            
            if full_match:
                # Extract alt text if present
                alt_match = re.search(r'alt\s*=\s*["\']([^"\']*)["\']', full_match.group(0), re.IGNORECASE)
                alt_text = alt_match.group(1) if alt_match else ''
                
                local_images.append({
                    'alt': alt_text,
                    'original_path': image_path,
                    'title': '',  # HTML img tags don't typically use title in the same way
                    'full_match': full_match.group(0),
                    'type': 'html'
                })
    
    return local_images

def process_chapter_images(novel_slug, chapter_id, language, markdown_content):
    """Process and copy chapter images, return updated markdown content"""
    local_images = extract_local_images(markdown_content)
    if not local_images:
        return markdown_content
    
    # Determine chapter source directory
    if language == 'en':
        chapter_source_dir = os.path.join(CONTENT_DIR, novel_slug, "chapters")
    else:
        chapter_source_dir = os.path.join(CONTENT_DIR, novel_slug, "chapters", language)
    
    # Create images directory in build
    build_images_dir = os.path.join(BUILD_DIR, "images", novel_slug, chapter_id)
    os.makedirs(build_images_dir, exist_ok=True)
    
    updated_content = markdown_content
    
    for image_info in local_images:
        source_image_path = os.path.join(chapter_source_dir, image_info['original_path'])
        
        if os.path.exists(source_image_path):
            # Copy image to build directory
            image_filename = os.path.basename(image_info['original_path'])
            dest_image_path = os.path.join(build_images_dir, image_filename)
            shutil.copy2(source_image_path, dest_image_path)
            
            # Update markdown content with new path (relative to the chapter page)
            new_image_path = f"../../../images/{novel_slug}/{chapter_id}/{image_filename}"
            
            if image_info['type'] == 'markdown':
                # Handle markdown images
                new_markdown = f"![{image_info['alt']}]({new_image_path}"
                if image_info['title']:
                    new_markdown += f' "{image_info["title"]}"'
                new_markdown += ")"
                updated_content = updated_content.replace(image_info['full_match'], new_markdown)
            
            elif image_info['type'] == 'html':
                # Handle HTML img tags - replace the src attribute
                old_src_pattern = r'src\s*=\s*["\'][^"\']*["\']'
                new_src = f'src="{new_image_path}"'
                new_img_tag = re.sub(old_src_pattern, new_src, image_info['full_match'], flags=re.IGNORECASE)
                updated_content = updated_content.replace(image_info['full_match'], new_img_tag)
    
    return updated_content

# Add the slugify_tag function as a Jinja2 filter
env.filters['slugify_tag'] = slugify_tag

# Add the find_author_username function as a Jinja2 filter
def find_author_username_filter(author_name, authors_config):
    """Jinja2 filter to find author username by name"""
    return find_author_username(author_name, authors_config)

env.filters['find_author_username'] = find_author_username_filter

def has_translated_chapters(novel_slug, language):
    """Check if a novel has translated chapters for a given language"""
    build_dir = os.path.join(BUILD_DIR, novel_slug, language)
    if not os.path.exists(build_dir):
        return False
    
    # Count chapter files (excluding toc and tags directories)
    chapter_count = 0
    for item in os.listdir(build_dir):
        item_path = os.path.join(build_dir, item)
        if os.path.isdir(item_path) and item.startswith('chapter-'):
            chapter_index_path = os.path.join(item_path, 'index.html')
            if os.path.exists(chapter_index_path):
                chapter_count += 1
    
    return chapter_count > 0

def load_all_novels_data():
    """Load all novels from the content directory (for processing)"""
    novels = []
    
    # Scan content directory for novel folders
    if os.path.exists(CONTENT_DIR):
        for novel_folder in os.listdir(CONTENT_DIR):
            novel_path = os.path.join(CONTENT_DIR, novel_folder)
            if os.path.isdir(novel_path):
                # Try to load novel config
                config_file = os.path.join(novel_path, "config.yaml")
                if os.path.exists(config_file):
                    with open(config_file, 'r', encoding='utf-8') as f:
                        novel_data = yaml.safe_load(f)
                        novel_data['slug'] = novel_folder
                        novels.append(novel_data)
                else:
                    # Fallback: use hardcoded data for existing novel
                    if novel_folder == "my-awesome-web-novel":
                        novel_data = {
                            "title": "My Awesome Web Novel",
                            "slug": novel_folder,
                            "primary_language": "en",
                            "description": "A thrilling adventure across mystical lands and perilous quests.",
                            "arcs": [
                                {
                                    "title": "Arc 1: The Beginning",
                                    "chapters": [
                                        {"id": "chapter-1", "title": "Chapter 1: The Prophecy"},
                                        {"id": "chapter-2", "title": "Chapter 2: A New Journey"},
                                    ]
                                },
                                {
                                    "title": "Arc 2: The Quest", 
                                    "chapters": [
                                        {"id": "chapter-3", "title": "Chapter 3: Ancient Ruins"},
                                        {"id": "chapter-4", "title": "Chapter 4: The Guardian"},
                                    ]
                                }
                            ]
                        }
                        novels.append(novel_data)
    
    return novels


def convert_markdown_to_html(md_content):
    # Convert Markdown to HTML. This will also handle image paths.
    return markdown.markdown(md_content)

def copy_static_assets():
    if os.path.exists(STATIC_DIR):
        shutil.copytree(STATIC_DIR, os.path.join(BUILD_DIR, "static"), dirs_exist_ok=True)

def render_template(template_name, **kwargs):
    template = env.get_template(template_name)
    return template.render(**kwargs)

def build_site(include_drafts=False):
    global INCLUDE_DRAFTS
    INCLUDE_DRAFTS = include_drafts
    
    print("Building site...")
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(BUILD_DIR)

    copy_static_assets()
    
    # Load site configuration
    site_config = load_site_config()

    # Load all novels for processing
    all_novels_data = load_all_novels_data()
    
    # Process cover art for all novels first
    for novel in all_novels_data:
        novel_slug = novel['slug']
        novel_config = load_novel_config(novel_slug)
        
        # Process cover art images and get processed paths
        processed_images = process_cover_art(novel_slug, novel_config)
        
        # Update novel data with processed image paths
        if processed_images.get('story_cover'):
            if 'front_page' not in novel:
                novel['front_page'] = {}
            novel['front_page']['cover_art'] = processed_images['story_cover']
        
        # Update arc data with processed image paths
        if novel_config.get('arcs') and novel.get('arcs'):
            for i, arc in enumerate(novel_config['arcs']):
                if i < len(novel['arcs']):  # Safety check
                    arc_cover_key = f'arc_{i}_cover'
                    if processed_images.get(arc_cover_key):
                        novel['arcs'][i]['cover_art'] = processed_images[arc_cover_key]
    
    # Filter novels for front page display
    front_page_novels_data = []
    for novel_data in all_novels_data:
        show_on_front_page = novel_data.get('front_page', {}).get('show_on_front_page', True)
        if show_on_front_page:
            front_page_novels_data.append(novel_data)

    # Generate robots.txt (using all novels)
    robots_txt_content = generate_robots_txt(site_config, all_novels_data)
    with open(os.path.join(BUILD_DIR, "robots.txt"), "w", encoding='utf-8') as f:
        f.write(robots_txt_content)

    # Generate sitemap.xml (using all novels)
    sitemap_xml_content = generate_sitemap_xml(site_config, all_novels_data)
    with open(os.path.join(BUILD_DIR, "sitemap.xml"), "w", encoding='utf-8') as f:
        f.write(sitemap_xml_content)

    # Generate site-wide RSS feed (using all novels)
    site_rss_content = generate_rss_feed(site_config, all_novels_data)
    with open(os.path.join(BUILD_DIR, "rss.xml"), "w", encoding='utf-8') as f:
        f.write(site_rss_content)

    # Build social metadata for front page
    front_page_url = site_config.get('site_url', '').rstrip('/')
    social_meta = build_social_meta(site_config, {}, {}, 'index', site_config.get('site_name', 'Web Novel Collection'), front_page_url)
    seo_meta = build_seo_meta(site_config, {}, {}, 'index')

    # Build footer data for front page
    footer_data = build_footer_content(site_config, page_type='site')

    # Render front page with novels that should be displayed
    with open(os.path.join(BUILD_DIR, "index.html"), "w", encoding='utf-8') as f:
        f.write(render_template("index.html", 
                               novels=front_page_novels_data,
                               site_name=site_config.get('site_name', 'Web Novel Collection'),
                               social_title=social_meta['title'],
                               social_description=social_meta['description'],
                               social_image=social_meta['image'],
                               social_url=social_meta['url'],
                               seo_meta_description=seo_meta.get('meta_description'),
                               seo_keywords=social_meta.get('keywords'),
                               allow_indexing=seo_meta.get('allow_indexing', True),
                               twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle'),
                               footer_data=footer_data))

    # Generate author pages
    authors_config = load_authors_config()
    author_contributions = collect_author_contributions(all_novels_data)
    
    if authors_config:
        # Create authors directory
        authors_dir = os.path.join(BUILD_DIR, "authors")
        os.makedirs(authors_dir, exist_ok=True)
        
        # Build social metadata for authors index
        authors_url = f"{site_config.get('site_url', '').rstrip('/')}/authors/"
        authors_social_meta = build_social_meta(site_config, {}, {}, 'authors', "Authors", authors_url)
        authors_seo_meta = build_seo_meta(site_config, {}, {}, 'authors')
        
        # Render authors index page
        with open(os.path.join(authors_dir, "index.html"), "w", encoding='utf-8') as f:
            f.write(render_template("authors.html",
                                   authors=authors_config,
                                   site_name=site_config.get('site_name', 'Web Novel Collection'),
                                   social_title=authors_social_meta['title'],
                                   social_description=authors_social_meta['description'],
                                   social_image=authors_social_meta['image'],
                                   social_url=authors_social_meta['url'],
                                   seo_meta_description=authors_seo_meta.get('meta_description'),
                                   seo_keywords=authors_social_meta.get('keywords'),
                                   allow_indexing=authors_seo_meta.get('allow_indexing', True),
                                   twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle'),
                                   footer_data=footer_data))
        
        # Generate individual author pages
        for username, author_info in authors_config.items():
            author_dir = os.path.join(authors_dir, username)
            os.makedirs(author_dir, exist_ok=True)
            
            # Get contributions for this author (match by name)
            author_name = author_info.get('name', username)
            contributions = author_contributions.get(author_name, {'stories': [], 'chapters': []})
            
            # Sort chapters by publication date (most recent first)
            if contributions['chapters']:
                contributions['chapters'].sort(key=lambda x: x.get('published', '1900-01-01'), reverse=True)
                
                # Limit chapters based on site configuration
                max_chapters = site_config.get('author_pages', {}).get('max_recent_chapters', 20)
                if max_chapters > 0:
                    contributions['chapters'] = contributions['chapters'][:max_chapters]
            
            # Build social metadata for author
            author_url = f"{site_config.get('site_url', '').rstrip('/')}/authors/{username}/"
            author_social_meta = build_social_meta(site_config, {}, {}, 'author', f"{author_name} - Author", author_url)
            author_seo_meta = build_seo_meta(site_config, {}, {}, 'author')
            
            # Render author page
            with open(os.path.join(author_dir, "index.html"), "w", encoding='utf-8') as f:
                f.write(render_template("author.html",
                                       author=author_info,
                                       stories=contributions['stories'],
                                       chapters=contributions['chapters'],
                                       max_chapters=max_chapters,
                                       site_name=site_config.get('site_name', 'Web Novel Collection'),
                                       social_title=author_social_meta['title'],
                                       social_description=author_social_meta['description'],
                                       social_image=author_social_meta['image'],
                                       social_url=author_social_meta['url'],
                                       seo_meta_description=author_seo_meta.get('meta_description'),
                                       seo_keywords=author_social_meta.get('keywords'),
                                       allow_indexing=author_seo_meta.get('allow_indexing', True),
                                       twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle'),
                                       footer_data=footer_data))

    # Process each novel (including hidden ones)
    for novel in all_novels_data:
        novel_slug = novel['slug']
        novel_config = load_novel_config(novel_slug)
        available_languages = get_available_languages(novel_slug)
        novel['languages'] = available_languages
        
        # Create novel directory
        novel_dir = os.path.join(BUILD_DIR, novel_slug)
        os.makedirs(novel_dir, exist_ok=True)

        # Generate story-specific RSS feed
        story_rss_content = generate_rss_feed(site_config, all_novels_data, novel_config, novel_slug)
        with open(os.path.join(novel_dir, "rss.xml"), "w", encoding='utf-8') as f:
            f.write(story_rss_content)

        # Process each language
        for lang in available_languages:
            lang_dir = os.path.join(novel_dir, lang)
            os.makedirs(lang_dir, exist_ok=True)

            # Render table of contents page for this novel/language
            toc_dir = os.path.join(lang_dir, "toc")
            os.makedirs(toc_dir, exist_ok=True)
            
            # Build social metadata for TOC
            toc_url = f"{site_config.get('site_url', '').rstrip('/')}/{novel_slug}/{lang}/toc/"
            toc_social_meta = build_social_meta(site_config, novel_config, {}, 'toc', f"{novel.get('title', '')} - Table of Contents", toc_url)
            toc_seo_meta = build_seo_meta(site_config, novel_config, {}, 'toc')
            
            # Build footer data for TOC
            footer_data = build_footer_content(site_config, novel_config, 'toc')
            
            # Build comments configuration for TOC
            toc_comments_enabled = should_enable_comments(site_config, novel_config, {}, 'toc')
            comments_config = build_comments_config(site_config)
            
            # Filter out hidden chapters for TOC display
            filtered_novel = filter_hidden_chapters_from_novel(novel, novel_slug, lang)
            
            # Calculate story length statistics
            story_length_stats = calculate_story_length_stats(novel_slug, lang)
            
            # Determine which unit to display based on configuration
            length_config = novel_config.get('length_display', {})
            language_units = length_config.get('language_units', {})
            default_unit = length_config.get('default_unit', 'words')
            
            # Check for language-specific override, fall back to default
            display_unit = language_units.get(lang, default_unit)
            
            if display_unit == 'characters':
                story_length_count = story_length_stats['characters']
                story_length_unit = 'characters'
            else:
                story_length_count = story_length_stats['words']
                story_length_unit = 'words'
            
            # Generate download links for this story
            download_links = generate_download_links(novel_slug, novel_config, site_config, lang)
            
            with open(os.path.join(toc_dir, "index.html"), "w", encoding='utf-8') as f:
                f.write(render_template("toc.html", 
                                       novel=filtered_novel, 
                                       current_language=lang, 
                                       available_languages=available_languages,
                                       story_length_count=story_length_count,
                                       story_length_unit=story_length_unit,
                                       site_name=site_config.get('site_name', 'Web Novel Collection'),
                                       social_title=toc_social_meta['title'],
                                       social_description=toc_social_meta['description'], 
                                       social_image=toc_social_meta['image'],
                                       social_url=toc_social_meta['url'],
                                       seo_meta_description=toc_seo_meta.get('meta_description'),
                                       seo_keywords=toc_social_meta.get('keywords'),
                                       allow_indexing=toc_seo_meta.get('allow_indexing', True),
                                       twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle'),
                                       footer_data=footer_data,
                                       download_links=download_links,
                                       comments_enabled=toc_comments_enabled,
                                       comments_repo=comments_config['repo'],
                                       comments_issue_term=comments_config['issue_term'],
                                       comments_label=comments_config['label'],
                                       comments_theme=comments_config['theme']))

            # Render chapter pages for this novel/language
            all_chapters = []
            for arc in novel["arcs"]:
                all_chapters.extend(arc["chapters"])

            for i, chapter in enumerate(all_chapters):
                chapter_id = chapter["id"]
                chapter_title = chapter["title"]
                primary_lang = novel.get('primary_language', 'en')
                
                # Check if translation exists for this language
                translation_exists = (lang == primary_lang) or chapter_translation_exists(novel_slug, chapter_id, lang)
                
                if translation_exists:
                    # Generate normal chapter page
                    chapter_content_md, chapter_metadata = load_chapter_content(novel_slug, chapter_id, lang)
                    
                    # Skip draft chapters unless include_drafts is True
                    if is_chapter_draft(chapter_metadata) and not INCLUDE_DRAFTS:
                        print(f"      Skipping draft chapter: {chapter_id} - {chapter_title}")
                        continue
                    
                    # Process chapter images and update markdown
                    chapter_content_md = process_chapter_images(novel_slug, chapter_id, lang, chapter_content_md)
                    
                    # Handle password protection
                    is_password_protected = 'password' in chapter_metadata and chapter_metadata['password']
                    encrypted_content = None
                    password_hash = None
                    password_hint = None
                    
                    if is_password_protected:
                        # Convert markdown to HTML first
                        chapter_content_html = convert_markdown_to_html(chapter_content_md)
                        
                        # Build the complete content to be encrypted including comments
                        complete_content = f'<div class="chapter-content">\n{chapter_content_html}\n</div>'
                        
                        # Add translator commentary if present
                        if chapter_metadata.get('translator_commentary'):
                            complete_content += f'''
                        <div class="translator-commentary">
                            <h3>Translator's Commentary</h3>
                            <div class="commentary-content">
                                {chapter_metadata['translator_commentary']}
                            </div>
                        </div>'''
                        
                        # Add comments section if enabled
                        comments_enabled = should_enable_comments(site_config, novel_config, chapter_metadata, 'chapter')
                        if comments_enabled:
                            comments_config = build_comments_config(site_config)
                            complete_content += f'''
                        <div class="comments-section">
                            <h3>Comments</h3>
                            <script src="https://utteranc.es/client.js"
                                    repo="{comments_config['repo']}"
                                    issue-term="{comments_config['issue_term']}"
                                    label="{comments_config['label']}"
                                    theme="{comments_config['theme']}"
                                    crossorigin="anonymous"
                                    async>
                            </script>
                        </div>'''
                        
                        # Encrypt the complete content
                        encrypted_content = encrypt_content_with_password(complete_content, chapter_metadata['password'])
                        password_hash = create_password_verification_hash(chapter_metadata['password'])
                        password_hint = chapter_metadata.get('password_hint', 'This chapter is password protected.')
                        # Set content to placeholder for password-protected chapters
                        chapter_content_html = '<div id="password-protected-content" style="text-align: center; padding: 2rem;"><p>This chapter is password protected.</p></div>'
                    else:
                        chapter_content_html = convert_markdown_to_html(chapter_content_md)
                    
                    # Use navigation function to skip hidden chapters
                    prev_chapter, next_chapter = get_navigation_chapters(novel_slug, all_chapters, chapter_id, lang)

                    # Use front matter title if available, otherwise use chapter title from config
                    display_title = chapter_metadata.get('title', chapter_title)
                    
                    # Determine what to display based on config and front matter
                    show_tags = should_show_tags(novel_config, chapter_metadata)
                    show_metadata = should_show_metadata(novel_config, chapter_metadata)
                    show_translation_notes = should_show_translation_notes(novel_config, chapter_metadata)
                    
                    # Build social metadata for chapter
                    chapter_url = f"{site_config.get('site_url', '').rstrip('/')}/{novel_slug}/{lang}/{chapter_id}/"
                    chapter_social_meta = build_social_meta(site_config, novel_config, chapter_metadata, 'chapter', display_title, chapter_url)
                    chapter_seo_meta = build_seo_meta(site_config, novel_config, chapter_metadata, 'chapter')
                    
                    # Build footer data for chapter
                    footer_data = build_footer_content(site_config, novel_config, 'chapter')
                    
                    # Build comments configuration
                    comments_enabled = should_enable_comments(site_config, novel_config, chapter_metadata, 'chapter')
                    comments_config = build_comments_config(site_config)
                    
                    chapter_dir = os.path.join(lang_dir, chapter_id)
                    os.makedirs(chapter_dir, exist_ok=True)
                    with open(os.path.join(chapter_dir, "index.html"), "w", encoding='utf-8') as f:
                        # Filter out hidden chapters for chapter dropdown
                        filtered_novel = filter_hidden_chapters_from_novel(novel, novel_slug, lang)
                        f.write(render_template("chapter.html", 
                                                novel=filtered_novel,
                                                chapter=chapter,
                                                chapter_title=display_title,
                                                chapter_content=chapter_content_html,
                                                chapter_metadata=chapter_metadata,
                                                prev_chapter=prev_chapter,
                                                next_chapter=next_chapter,
                                                current_language=lang,
                                                available_languages=available_languages,
                                                show_tags=show_tags,
                                                show_metadata=show_metadata,
                                                show_translation_notes=show_translation_notes,
                                                is_password_protected=is_password_protected,
                                                encrypted_content=encrypted_content,
                                                password_hash=password_hash,
                                                password_hint=password_hint,
                                                authors_config=authors_config,
                                                site_name=site_config.get('site_name', 'Web Novel Collection'),
                                                social_title=chapter_social_meta['title'],
                                                social_description=chapter_social_meta['description'],
                                                social_image=chapter_social_meta['image'],
                                                social_url=chapter_social_meta['url'],
                                                seo_meta_description=chapter_seo_meta.get('meta_description'),
                                                seo_keywords=chapter_social_meta.get('keywords'),
                                                allow_indexing=chapter_seo_meta.get('allow_indexing', True),
                                                twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle'),
                                                footer_data=footer_data,
                                                comments_enabled=comments_enabled,
                                                comments_repo=comments_config['repo'],
                                                comments_issue_term=comments_config['issue_term'],
                                                comments_label=comments_config['label'],
                                                comments_theme=comments_config['theme']))
                else:
                    # Generate chapter page showing "not translated" message in primary language
                    chapter_content_md, chapter_metadata = load_chapter_content(novel_slug, chapter_id, primary_lang)
                    # Process chapter images and update markdown (using primary language)
                    chapter_content_md = process_chapter_images(novel_slug, chapter_id, primary_lang, chapter_content_md)
                    
                    # Handle password protection (same as above)
                    is_password_protected = 'password' in chapter_metadata and chapter_metadata['password']
                    encrypted_content = None
                    password_hash = None
                    password_hint = None
                    
                    if is_password_protected:
                        # Convert markdown to HTML first
                        chapter_content_html = convert_markdown_to_html(chapter_content_md)
                        
                        # Build the complete content to be encrypted including comments
                        complete_content = f'<div class="chapter-content">\n{chapter_content_html}\n</div>'
                        
                        # Add translator commentary if present
                        if chapter_metadata.get('translator_commentary'):
                            complete_content += f'''
                        <div class="translator-commentary">
                            <h3>Translator's Commentary</h3>
                            <div class="commentary-content">
                                {chapter_metadata['translator_commentary']}
                            </div>
                        </div>'''
                        
                        # Add comments section if enabled
                        comments_enabled = should_enable_comments(site_config, novel_config, chapter_metadata, 'chapter')
                        if comments_enabled:
                            comments_config = build_comments_config(site_config)
                            complete_content += f'''
                        <div class="comments-section">
                            <h3>Comments</h3>
                            <script src="https://utteranc.es/client.js"
                                    repo="{comments_config['repo']}"
                                    issue-term="{comments_config['issue_term']}"
                                    label="{comments_config['label']}"
                                    theme="{comments_config['theme']}"
                                    crossorigin="anonymous"
                                    async>
                            </script>
                        </div>'''
                        
                        # Encrypt the complete content
                        encrypted_content = encrypt_content_with_password(complete_content, chapter_metadata['password'])
                        password_hash = create_password_verification_hash(chapter_metadata['password'])
                        password_hint = chapter_metadata.get('password_hint', 'This chapter is password protected.')
                        # Set content to placeholder for password-protected chapters
                        chapter_content_html = '<div id="password-protected-content" style="text-align: center; padding: 2rem;"><p>This chapter is password protected.</p></div>'
                    else:
                        chapter_content_html = convert_markdown_to_html(chapter_content_md)
                    
                    # Use navigation function to skip hidden chapters
                    prev_chapter, next_chapter = get_navigation_chapters(novel_slug, all_chapters, chapter_id, lang)

                    # Use front matter title if available, otherwise use chapter title from config
                    display_title = chapter_metadata.get('title', chapter_title)
                    
                    # Determine what to display based on config and front matter
                    show_tags = should_show_tags(novel_config, chapter_metadata)
                    show_metadata = should_show_metadata(novel_config, chapter_metadata)
                    show_translation_notes = should_show_translation_notes(novel_config, chapter_metadata)
                    
                    # Build social metadata for chapter (using primary language metadata)
                    chapter_url = f"{site_config.get('site_url', '').rstrip('/')}/{novel_slug}/{lang}/{chapter_id}/"
                    chapter_social_meta = build_social_meta(site_config, novel_config, chapter_metadata, 'chapter', display_title, chapter_url)
                    chapter_seo_meta = build_seo_meta(site_config, novel_config, chapter_metadata, 'chapter')
                    
                    # Build footer data for chapter (missing translation case)
                    footer_data = build_footer_content(site_config, novel_config, 'chapter')
                    
                    # Build comments configuration (missing translation case)
                    comments_enabled = should_enable_comments(site_config, novel_config, chapter_metadata, 'chapter')
                    comments_config = build_comments_config(site_config)
                    
                    chapter_dir = os.path.join(lang_dir, chapter_id)
                    os.makedirs(chapter_dir, exist_ok=True)
                    with open(os.path.join(chapter_dir, "index.html"), "w", encoding='utf-8') as f:
                        # Filter out hidden chapters for chapter dropdown
                        filtered_novel = filter_hidden_chapters_from_novel(novel, novel_slug, lang)
                        f.write(render_template("chapter.html", 
                                                novel=filtered_novel,
                                                chapter=chapter,
                                                chapter_title=display_title,
                                                chapter_content=chapter_content_html,
                                                chapter_metadata=chapter_metadata,
                                                prev_chapter=prev_chapter,
                                                next_chapter=next_chapter,
                                                current_language=lang,
                                                primary_language=primary_lang,
                                                requested_language=lang,
                                                translation_missing=True,
                                                available_languages=available_languages,
                                                show_tags=show_tags,
                                                show_metadata=show_metadata,
                                                show_translation_notes=show_translation_notes,
                                                is_password_protected=is_password_protected,
                                                encrypted_content=encrypted_content,
                                                password_hash=password_hash,
                                                password_hint=password_hint,
                                                authors_config=authors_config,
                                                site_name=site_config.get('site_name', 'Web Novel Collection'),
                                                social_title=chapter_social_meta['title'],
                                                social_description=chapter_social_meta['description'],
                                                social_image=chapter_social_meta['image'],
                                                social_url=chapter_social_meta['url'],
                                                seo_meta_description=chapter_seo_meta.get('meta_description'),
                                                seo_keywords=chapter_social_meta.get('keywords'),
                                                allow_indexing=chapter_seo_meta.get('allow_indexing', True),
                                                twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle'),
                                                footer_data=footer_data,
                                                comments_enabled=comments_enabled,
                                                comments_repo=comments_config['repo'],
                                                comments_issue_term=comments_config['issue_term'],
                                                comments_label=comments_config['label'],
                                                comments_theme=comments_config['theme']))

        # Generate tag pages for this language (after all chapters are processed)
        for lang in available_languages:
            lang_dir = os.path.join(novel_dir, lang)
            tags_data = collect_tags_for_novel(novel_slug, lang)
            if tags_data:
                # Create tags directory
                tags_dir = os.path.join(lang_dir, "tags")
                os.makedirs(tags_dir, exist_ok=True)
                
                # Create tag slug mapping for templates
                tag_slug_map = {tag: slugify_tag(tag) for tag in tags_data.keys()}
                
                # Generate main tags index page
                with open(os.path.join(tags_dir, "index.html"), "w", encoding='utf-8') as f:
                    f.write(render_template("tags_index.html",
                                            novel=novel,
                                            tags_data=tags_data,
                                            tag_slug_map=tag_slug_map,
                                            current_language=lang,
                                            available_languages=available_languages))
                
                # Generate individual tag pages
                for tag, chapters in tags_data.items():
                    tag_slug = slugify_tag(tag)
                    tag_page_dir = os.path.join(tags_dir, tag_slug)
                    os.makedirs(tag_page_dir, exist_ok=True)
                    
                    with open(os.path.join(tag_page_dir, "index.html"), "w", encoding='utf-8') as f:
                        f.write(render_template("tag_page.html",
                                                novel=novel,
                                                tag_name=tag,
                                                tag_slug=tag_slug,
                                                chapters=chapters,
                                                current_language=lang,
                                                available_languages=available_languages))

    # Generate EPUB downloads after all HTML is built
    print("Generating EPUB downloads...")
    for novel in all_novels_data:
        novel_slug = novel['slug']
        novel_config = load_novel_config(novel_slug)
        available_languages = novel_config.get('languages', {}).get('available', ['en'])
        
        print(f"  Generating downloads for {novel_slug}...")
        
        # Generate EPUBs for each available language
        for language in available_languages:
            # Check if this language has translated chapters
            if has_translated_chapters(novel_slug, language):
                language_suffix = f"-{language}" if language != novel_config.get('languages', {}).get('default', 'en') else ""
                
                # Generate full story EPUB
                if generate_story_epub(novel_slug, novel_config, site_config, novel, language):
                    print(f"    Generated EPUB for {novel_slug}{language_suffix}")
                
                # Generate arc-specific EPUBs if enabled
                if novel_config.get('downloads', {}).get('include_arcs', True):
                    all_chapters = get_non_hidden_chapters(novel_config, novel_slug, language, INCLUDE_DRAFTS)
                    for arc_index, arc in enumerate(all_chapters):
                        if arc['chapters']:  # Only generate if arc has chapters
                            if generate_arc_epub(novel_slug, novel_config, site_config, arc_index, novel, language):
                                print(f"    Generated EPUB for {novel_slug} - {arc['title']}{language_suffix}")
    
    # Update TOC pages with download links after downloads are generated
    print("Updating TOC pages with download links...")
    for novel in all_novels_data:
        novel_slug = novel['slug']
        novel_config = load_novel_config(novel_slug)
        available_languages = novel_config.get('languages', {}).get('available', ['en'])
        
        # Update TOC for each language
        for lang in available_languages:
            update_toc_with_downloads(novel, novel_slug, novel_config, site_config, lang)

    print("Site built.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Static site generator for web novels')
    parser.add_argument('--include-drafts', action='store_true', 
                        help='Include draft chapters in the generated site')
    args = parser.parse_args()
    
    # Pass the include_drafts flag to build_site
    build_site(include_drafts=args.include_drafts)


