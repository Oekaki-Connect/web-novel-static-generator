import os
import shutil
from jinja2 import Environment, FileSystemLoader
import markdown
import yaml
import re
import glob
from pathlib import Path
import hashlib
import base64
import json
import datetime
import argparse
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from bs4 import BeautifulSoup
# Lazy import for optional dependencies
EBOOKLIB_AVAILABLE = False

# Global flags for chapter inclusion
INCLUDE_DRAFTS = False
INCLUDE_SCHEDULED = False


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

BUILD_DIR = os.path.abspath("./build")
CONTENT_DIR = "./content"
PAGES_DIR = "./pages"
TEMPLATES_DIR = "./templates"
STATIC_DIR = "./static"

# Global template environment (will be enhanced with novel-specific support)
env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

# Global asset map for cache busting
ASSET_MAP = {}

def asset_url(filename):
    """Convert asset filename to cache-busted version if available"""
    return ASSET_MAP.get(filename, filename)

# Register the asset_url filter
env.filters['asset_url'] = asset_url

# Cache for novel-specific template environments
_novel_template_envs = {}

def get_novel_template_directories(novel_slug):
    """Get list of template directories for a novel (novel-specific first, then defaults)"""
    directories = []
    
    # Novel-specific templates directory
    novel_templates_dir = os.path.join(CONTENT_DIR, novel_slug, "templates")
    if os.path.exists(novel_templates_dir):
        directories.append(novel_templates_dir)
    
    # Default templates directory (fallback)
    directories.append(TEMPLATES_DIR)
    
    return directories

def get_novel_template_env(novel_slug):
    """Get or create a Jinja2 environment for a specific novel with template override support"""
    if novel_slug not in _novel_template_envs:
        template_dirs = get_novel_template_directories(novel_slug)
        loader = FileSystemLoader(template_dirs)
        novel_env = Environment(loader=loader)
        
        # Add the same filters as the global environment
        novel_env.filters['slugify_tag'] = slugify_tag
        novel_env.filters['format_date_for_display'] = format_date_for_display
        novel_env.filters['find_author_username'] = find_author_username_filter
        novel_env.filters['asset_url'] = asset_url
        
        # Note: is_chapter_new filter will be set per render with proper config
        
        _novel_template_envs[novel_slug] = novel_env
    
    return _novel_template_envs[novel_slug]

def check_novel_has_custom_templates(novel_slug):
    """Check if a novel has any custom templates"""
    novel_templates_dir = os.path.join(CONTENT_DIR, novel_slug, "templates")
    return os.path.exists(novel_templates_dir) and os.listdir(novel_templates_dir)

def list_novel_custom_templates(novel_slug):
    """List all custom templates for a novel"""
    novel_templates_dir = os.path.join(CONTENT_DIR, novel_slug, "templates")
    if not os.path.exists(novel_templates_dir):
        return []
    
    custom_templates = []
    for file in os.listdir(novel_templates_dir):
        if file.endswith('.html'):
            custom_templates.append(file)
    
    return sorted(custom_templates)

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
                if should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS, INCLUDE_SCHEDULED):
                    continue
                
                # Skip hidden chapters, password-protected, or non-indexed chapters
                if (is_chapter_hidden(chapter_metadata) or 
                    ('password' in chapter_metadata and chapter_metadata['password']) or
                    chapter_metadata.get('seo', {}).get('allow_indexing') is False):
                    continue
                
                published_date = chapter_metadata.get('published')
                if published_date:
                    try:
                        # Handle both string and date object formats
                        if isinstance(published_date, str):
                            pub_datetime = datetime.strptime(published_date, '%Y-%m-%d')
                        else:
                            # Assume it's already a date object, convert to datetime
                            pub_datetime = datetime.combine(published_date, datetime.min.time())
                        
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
                    if should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS, INCLUDE_SCHEDULED):
                        continue
                    
                    # Skip hidden, password-protected, or non-indexed chapters
                    if (is_chapter_hidden(chapter_metadata) or 
                        ('password' in chapter_metadata and chapter_metadata['password']) or
                        chapter_metadata.get('seo', {}).get('allow_indexing') is False):
                        continue
                    
                    published_date = chapter_metadata.get('published')
                    if published_date:
                        try:
                            # Handle both string and date object formats
                            if isinstance(published_date, str):
                                pub_datetime = datetime.strptime(published_date, '%Y-%m-%d')
                            else:
                                # Assume it's already a date object, convert to datetime
                                pub_datetime = datetime.combine(published_date, datetime.min.time())
                            
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
    
    # Add page index
    available_languages = site_config.get('languages', {}).get('available', ['en'])
    for lang in available_languages:
        index_filename = f"pages-{lang}.html" if lang != 'en' else "pages.html"
        sitemap_entries.append(f"""    <url>
        <loc>{site_url}/{index_filename}</loc>
        <changefreq>weekly</changefreq>
        <priority>0.7</priority>
    </url>""")
    
    # Add static pages
    all_pages = get_all_pages()
    available_languages = site_config.get('languages', {}).get('available', ['en'])
    
    for page_data in all_pages:
        page_slug = page_data['slug']
        # Load page metadata to check if it should be included
        for lang in available_languages:
            try:
                _, page_metadata = load_page_content(page_slug, lang)
                
                # Skip pages that don't allow indexing, are drafts, or are password-protected
                if should_skip_page(page_metadata, INCLUDE_DRAFTS):
                    continue
                    
                page_allow_indexing = page_metadata.get('seo', {}).get('allow_indexing')
                is_password_protected = 'password' in page_metadata and page_metadata['password']
                
                if page_allow_indexing is False or is_password_protected:
                    continue
                
                # Build the page URL
                if '/' in page_slug:
                    # Nested page (e.g., "resources/translation-guide")
                    page_url = f"{site_url}/{page_slug}/{lang}/"
                else:
                    # Top-level page (e.g., "about")
                    page_url = f"{site_url}/{page_slug}/{lang}/"
                
                # Get updated date if available
                lastmod = ""
                if page_metadata.get('updated'):
                    try:
                        from datetime import datetime
                        update_date = datetime.strptime(page_metadata['updated'], '%Y-%m-%d')
                        lastmod = f"\n        <lastmod>{update_date.strftime('%Y-%m-%d')}</lastmod>"
                    except:
                        pass
                
                sitemap_entries.append(f"""    <url>
        <loc>{page_url}</loc>
        <changefreq>monthly</changefreq>
        <priority>0.6</priority>{lastmod}
    </url>""")
                    
            except:
                # Skip pages that don't exist for this language
                continue
    
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
                    if should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS, INCLUDE_SCHEDULED):
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
                        if should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS, INCLUDE_SCHEDULED):
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
    images_dir = os.path.normpath(os.path.join(BUILD_DIR, "static", "images"))
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

def get_non_hidden_chapters(novel_config, novel_slug, language='en', include_drafts=False, include_scheduled=False):
    """Get list of chapters that are not hidden or drafts"""
    visible_chapters = []
    
    for arc in novel_config.get('arcs', []):
        arc_chapters = []
        for chapter in arc.get('chapters', []):
            chapter_id = chapter['id']
            
            # Load chapter content to check if it's hidden, password protected, or draft
            try:
                chapter_content, chapter_metadata = load_chapter_content(novel_slug, chapter_id, language)
                
                # Skip if chapter should be skipped
                if should_skip_chapter(chapter_metadata, include_drafts, include_scheduled):
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

def get_chapters_for_epub(novel_config, novel_slug, language='en', include_drafts=False, include_scheduled=False):
    """Get list of chapters for EPUB generation (excludes hidden, draft, and password-protected)"""
    visible_chapters = []
    
    for arc in novel_config.get('arcs', []):
        arc_chapters = []
        for chapter in arc.get('chapters', []):
            chapter_id = chapter['id']
            
            # Load chapter content to check if it should be included in EPUB
            try:
                chapter_content, chapter_metadata = load_chapter_content(novel_slug, chapter_id, language)
                
                # Skip if chapter should be skipped in EPUB
                if should_skip_chapter_in_epub(chapter_metadata, include_drafts):
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


def load_page_content(page_slug, language='en'):
    """Load page content from markdown file with language support and front matter parsing"""
    # Try language-specific file first
    if language != 'en':
        page_file = os.path.join(PAGES_DIR, language, f"{page_slug}.md")
        if os.path.exists(page_file):
            with open(page_file, 'r', encoding='utf-8') as f:
                content = f.read()
                front_matter, markdown_content = parse_front_matter(content)
                return markdown_content, front_matter
    
    # Fallback to default language file
    page_file = os.path.join(PAGES_DIR, f"{page_slug}.md")
    if os.path.exists(page_file):
        with open(page_file, 'r', encoding='utf-8') as f:
            content = f.read()
            front_matter, markdown_content = parse_front_matter(content)
            return markdown_content, front_matter
    
    return None, {}

def load_nested_page_content(page_path, language='en'):
    """Load nested page content (e.g., resources/translation-guide)"""
    page_slug = page_path.replace('/', os.sep)
    
    # Try language-specific file first
    if language != 'en':
        page_file = os.path.join(PAGES_DIR, language, f"{page_slug}.md")
        if os.path.exists(page_file):
            with open(page_file, 'r', encoding='utf-8') as f:
                content = f.read()
                front_matter, markdown_content = parse_front_matter(content)
                return markdown_content, front_matter
    
    # Fallback to default language file
    page_file = os.path.join(PAGES_DIR, f"{page_slug}.md")
    if os.path.exists(page_file):
        with open(page_file, 'r', encoding='utf-8') as f:
            content = f.read()
            front_matter, markdown_content = parse_front_matter(content)
            return markdown_content, front_matter
    
    return None, {}

def get_all_pages():
    """Get list of all available pages"""
    pages = []
    
    if not os.path.exists(PAGES_DIR):
        return pages
    
    def scan_pages_directory(directory, prefix=""):
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            
            if os.path.isfile(item_path) and item.endswith('.md'):
                page_slug = prefix + item[:-3]  # Remove .md extension
                try:
                    content, metadata = load_page_content(page_slug.replace(os.sep, '/'))
                    if content:
                        pages.append({
                            'slug': page_slug.replace(os.sep, '/'),
                            'title': metadata.get('title', page_slug),
                            'description': metadata.get('description', ''),
                            'metadata': metadata
                        })
                except:
                    continue
            elif os.path.isdir(item_path) and not item.startswith('.') and len(item) != 2:  # Ignore language dirs
                scan_pages_directory(item_path, prefix + item + "/")
    
    scan_pages_directory(PAGES_DIR)
    return pages

def get_available_page_languages(page_slug):
    """Get list of available languages for a page"""
    languages = ['en']  # Default language
    
    if not os.path.exists(PAGES_DIR):
        return languages
    
    # Check for language-specific versions
    for item in os.listdir(PAGES_DIR):
        item_path = os.path.join(PAGES_DIR, item)
        if os.path.isdir(item_path) and len(item) == 2:  # Assume 2-letter language codes
            page_file = os.path.join(item_path, f"{page_slug}.md")
            if os.path.exists(page_file):
                languages.append(item)
    
    return sorted(set(languages))

def should_skip_page(page_metadata, include_drafts=False):
    """Check if a page should be skipped during generation"""
    if page_metadata.get('hidden', False):
        return True
    if page_metadata.get('draft', False) and not include_drafts:
        return True
    return False

def build_page_navigation(site_config, current_language='en', current_page_slug=None):
    """Build navigation menus from static pages"""
    if not os.path.exists(PAGES_DIR):
        return {'header': [], 'footer': []}
    
    navigation = {'header': [], 'footer': []}
    all_pages = get_all_pages()
    
    # Filter pages for current language and collect nav items
    nav_items = {'header': [], 'footer': []}
    
    for page_data in all_pages:
        page_slug = page_data['slug']
        page_metadata = page_data['metadata']
        
        # Skip if page should be skipped
        if should_skip_page(page_metadata, INCLUDE_DRAFTS):
            continue
        
        # Check if page is available in current language
        page_languages = get_available_page_languages(page_slug)
        if current_language not in page_languages:
            continue
        
        # Check navigation placement
        nav_placement = page_metadata.get('navigation')
        if nav_placement in ['header', 'footer']:
            nav_order = page_metadata.get('nav_order', 999)
            
            nav_items[nav_placement].append({
                'title': page_metadata.get('title', page_slug),
                'url': f"{page_slug}/{current_language}/",
                'slug': page_slug,
                'order': nav_order,
                'active': page_slug == current_page_slug
            })
    
    # Sort by nav_order
    for placement in ['header', 'footer']:
        nav_items[placement].sort(key=lambda x: x['order'])
        navigation[placement] = nav_items[placement]
    
    return navigation

def load_webring_config():
    """Load webring configuration from webring.yaml"""
    webring_file = os.path.join(os.getcwd(), "webring.yaml")
    if os.path.exists(webring_file):
        with open(webring_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            return config.get('webring', {})
    return {}

def fetch_rss_feed(url, timeout=10):
    """Fetch and parse RSS feed from URL with comprehensive error handling"""
    try:
        with urlopen(url, timeout=timeout) as response:
            # Check response status
            if response.status != 200:
                print(f"    Warning: RSS feed returned status {response.status}: {url}")
                return None
                
            content = response.read().decode('utf-8')
            soup = BeautifulSoup(content, 'xml')
            
            # Verify it's actually an RSS/XML feed
            if not soup.find('rss') and not soup.find('feed'):
                print(f"    Warning: URL does not appear to be a valid RSS feed: {url}")
                return None
                
            return soup
    except (URLError, HTTPError) as e:
        print(f"    Warning: Network error fetching RSS feed from {url}: {e}")
        return None
    except UnicodeDecodeError as e:
        print(f"    Warning: Unable to decode RSS feed content from {url}: {e}")
        return None
    except Exception as e:
        print(f"    Warning: Unexpected error fetching RSS feed from {url}: {e}")
        return None

def parse_rss_items(rss_soup, site_name, site_url):
    """Parse RSS feed and extract items"""
    if not rss_soup:
        return []
    
    items = []
    for item in rss_soup.find_all('item'):
        title_elem = item.find('title')
        link_elem = item.find('link')
        pub_date_elem = item.find('pubDate')
        description_elem = item.find('description')
        
        if title_elem and link_elem:
            title = title_elem.get_text(strip=True)
            link = link_elem.get_text(strip=True)
            
            # Parse publication date
            pub_date = None
            if pub_date_elem:
                try:
                    date_str = pub_date_elem.get_text(strip=True)
                    # Try to parse common RSS date formats
                    for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S %Z', '%Y-%m-%dT%H:%M:%S%z']:
                        try:
                            pub_date = datetime.datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                    if not pub_date:
                        # Fallback: try parsing without timezone
                        try:
                            pub_date = datetime.datetime.strptime(date_str[:25], '%a, %d %b %Y %H:%M:%S')
                        except ValueError:
                            pass
                except Exception:
                    pass
            
            # Extract description
            description = ""
            if description_elem:
                desc_text = description_elem.get_text(strip=True)
                # Limit description length
                if len(desc_text) > 150:
                    description = desc_text[:147] + "..."
                else:
                    description = desc_text
            
            items.append({
                'title': title,
                'link': link,
                'pub_date': pub_date,
                'description': description,
                'site_name': site_name,
                'site_url': site_url
            })
    
    return items

def generate_webring_data(webring_config, display_config):
    """Generate webring data by fetching and parsing RSS feeds"""
    if not webring_config.get('enabled', False):
        return []
    
    all_items = []
    max_items = webring_config.get('max_items', 20)
    sites_list = webring_config.get('sites', [])
    
    if not sites_list:
        print("Webring enabled but no sites configured")
        return []
    
    print("Fetching webring RSS feeds...")
    
    successful_sites = 0
    failed_sites = 0
    
    for site in sites_list:
        site_name = site.get('name', 'Unknown Site')
        site_url = site.get('url', '')
        rss_url = site.get('rss', '')
        
        if not rss_url:
            print(f"    Skipping {site_name}: No RSS URL configured")
            failed_sites += 1
            continue
            
        print(f"    Fetching RSS from {site_name}...")
        rss_soup = fetch_rss_feed(rss_url)
        
        if rss_soup:
            items = parse_rss_items(rss_soup, site_name, site_url)
            if items:
                all_items.extend(items)
                successful_sites += 1
                print(f"      Success: Found {len(items)} items from {site_name}")
            else:
                print(f"      Warning: No valid items found in RSS feed from {site_name}")
                failed_sites += 1
        else:
            failed_sites += 1
    
    # Sort by publication date (newest first)
    all_items.sort(key=lambda x: x['pub_date'] or datetime.datetime.min, reverse=True)
    
    # Limit to max_items
    limited_items = all_items[:max_items]
    
    # Format dates for display
    date_format = display_config.get('date_format', '%B %d, %Y')
    for item in limited_items:
        if item['pub_date']:
            item['formatted_date'] = item['pub_date'].strftime(date_format)
        else:
            item['formatted_date'] = 'Unknown date'
    
    print(f"    Generated webring with {len(limited_items)} items from {successful_sites}/{len(sites_list)} sites")
    if failed_sites > 0:
        print(f"    Note: {failed_sites} site(s) failed to load - webring will continue with available content")
    
    return limited_items


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
        chapters_data = get_chapters_for_epub(novel_config, novel_slug, language, INCLUDE_DRAFTS, INCLUDE_SCHEDULED)
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
        epub_dir = os.path.normpath(os.path.join(BUILD_DIR, "static", "epub"))
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
        all_chapters = get_chapters_for_epub(novel_config, novel_slug, language, INCLUDE_DRAFTS, INCLUDE_SCHEDULED)
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
        epub_dir = os.path.normpath(os.path.join(BUILD_DIR, "static", "epub"))
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
                               novel_slug=novel_slug,
                               site_config=site_config,
                               novel_config=novel_config,
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
        all_chapters = get_non_hidden_chapters(novel_config, novel_slug, 'en', INCLUDE_DRAFTS, INCLUDE_SCHEDULED)
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

def should_show_tags(novel_config, chapter_front_matter, translation_missing=False):
    """Determine if tags should be shown based on config and front matter"""
    # Don't show tags for hidden chapters since their tag pages don't exist
    if is_chapter_hidden(chapter_front_matter):
        return False
    
    # Don't show tags for translation-missing chapters since the tag pages 
    # may not exist in the target language
    if translation_missing:
        return False
    
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
    if 'comments' in chapter_metadata:
        if isinstance(chapter_metadata['comments'], bool):
            return chapter_metadata['comments']
        elif isinstance(chapter_metadata['comments'], dict) and 'enabled' in chapter_metadata['comments']:
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

def parse_publish_date(date_string):
    """
    Parse a publish date string into a datetime object.
    Supports multiple formats:
    - "2025-01-15" (date only)
    - "2025-01-15 14:30:00" (date and time)
    - "2025-01-15T14:30:00" (ISO format)
    - "2025-01-15T14:30:00Z" (UTC)
    - "2025-01-15T14:30:00-05:00" (with timezone)
    """
    if not date_string:
        return None
    
    # Convert to string if not already
    date_string = str(date_string).strip()
    
    # List of date formats to try
    formats = [
        "%Y-%m-%d",                    # 2025-01-15
        "%Y-%m-%d %H:%M:%S",          # 2025-01-15 14:30:00
        "%Y-%m-%dT%H:%M:%S",          # 2025-01-15T14:30:00
        "%Y-%m-%dT%H:%M:%SZ",         # 2025-01-15T14:30:00Z
    ]
    
    # Try parsing with each format
    for fmt in formats:
        try:
            return datetime.datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    
    # Try parsing ISO format with timezone
    try:
        # Handle timezone offsets like +05:00 or -05:00 or Z
        if ('+' in date_string and '+' in date_string[-6:]) or \
           ('-' in date_string and '-' in date_string[-6:]) or \
           date_string.endswith('Z'):
            return datetime.datetime.fromisoformat(date_string.replace('Z', '+00:00'))
    except (ValueError, ImportError):
        pass
    
    print(f"Warning: Could not parse publish date '{date_string}'. Using current time as fallback.")
    return datetime.datetime.now()

def is_chapter_scheduled_future(chapter_metadata, current_time=None):
    """
    Check if a chapter has a future publish date and should not be published yet.
    Returns True if the chapter should be excluded from the build.
    """
    if current_time is None:
        current_time = datetime.datetime.now()
    
    published_date_str = chapter_metadata.get('published')
    if not published_date_str:
        # No publish date means publish immediately
        return False
    
    published_date = parse_publish_date(published_date_str)
    if not published_date:
        # Invalid date, publish immediately as fallback
        return False
    
    # Handle timezone awareness - convert both to naive datetimes for comparison
    if published_date.tzinfo is not None:
        # Convert timezone-aware datetime to naive UTC
        published_date = published_date.utctimetuple()
        published_date = datetime.datetime(*published_date[:6])
    
    if current_time.tzinfo is not None:
        # Convert timezone-aware datetime to naive UTC
        current_time = current_time.utctimetuple()
        current_time = datetime.datetime(*current_time[:6])
    
    # If published date is in the future, exclude from build
    return published_date > current_time

def should_skip_chapter(chapter_metadata, include_drafts=False, include_scheduled=False):
    """
    Check if a chapter should be skipped during generation.
    
    Args:
        chapter_metadata: Chapter metadata dictionary
        include_drafts: Whether to include draft chapters
        include_scheduled: Whether to include chapters with future publish dates
    """
    if is_chapter_hidden(chapter_metadata):
        return True
    if is_chapter_draft(chapter_metadata) and not include_drafts:
        return True
    if is_chapter_scheduled_future(chapter_metadata) and not include_scheduled:
        return True
    return False

def format_date_for_display(date_string):
    """
    Format a date string to YYYY-MM-DD format for display on TOC.
    Handles various input formats and returns simplified date.
    """
    if not date_string:
        return None
    
    parsed_date = parse_publish_date(date_string)
    if not parsed_date:
        return date_string  # Return original if parsing fails
    
    return parsed_date.strftime("%Y-%m-%d")

def is_chapter_new(published_date_str, current_time=None, new_threshold_days=7, show_new_tags=True):
    """
    Check if a chapter was published within the configured threshold.
    Returns True if the chapter should be marked as (NEW!).
    
    Args:
        published_date_str: The publish date string from chapter metadata
        current_time: Current time for comparison (defaults to now)
        new_threshold_days: Number of days to consider a chapter "new" (default: 7)
        show_new_tags: Whether to show NEW! tags at all (default: True)
    """
    if not published_date_str or not show_new_tags:
        return False
    
    if current_time is None:
        current_time = datetime.datetime.now()
    
    published_date = parse_publish_date(published_date_str)
    if not published_date:
        return False
    
    # Handle timezone awareness - convert both to naive datetimes for comparison
    if published_date.tzinfo is not None:
        # Convert timezone-aware datetime to naive UTC
        published_date = published_date.utctimetuple()
        published_date = datetime.datetime(*published_date[:6])
    
    if current_time.tzinfo is not None:
        # Convert timezone-aware datetime to naive UTC
        current_time = current_time.utctimetuple()
        current_time = datetime.datetime(*current_time[:6])
    
    # Check if published within the configured threshold
    time_difference = current_time - published_date
    return time_difference.days <= new_threshold_days and time_difference.days >= 0

def should_skip_chapter_in_epub(chapter_metadata, include_drafts=False, include_scheduled=False):
    """Check if a chapter should be skipped in EPUB generation"""
    if should_skip_chapter(chapter_metadata, include_drafts, include_scheduled):
        return True
    # Also skip password-protected chapters in EPUBs
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
            if not should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS, INCLUDE_SCHEDULED):
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
            if should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS, INCLUDE_SCHEDULED):
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
                if not should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS, INCLUDE_SCHEDULED):
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
    build_images_dir = os.path.normpath(os.path.join(BUILD_DIR, "images", novel_slug, chapter_id))
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

def process_manga_pages(novel_slug, chapter_id, language, chapter_metadata, novel_config):
    """Process manga pages for a manga chapter and return page data"""
    # Determine chapter source directory
    if language == 'en':
        chapter_source_dir = os.path.join(CONTENT_DIR, novel_slug, "chapters")
    else:
        chapter_source_dir = os.path.join(CONTENT_DIR, novel_slug, "chapters", language)
    
    # Look for page images in the chapter directory and chapter subfolder
    page_files = []
    
    # First, try to find pages in a subfolder named after the chapter_id
    chapter_subfolder = os.path.join(chapter_source_dir, chapter_id)
    if os.path.exists(chapter_subfolder):
        # Scan for page files in the subfolder
        for ext in ['png', 'jpg', 'jpeg', 'webp']:
            pattern = os.path.join(chapter_subfolder, f"page*.{ext}")
            page_files.extend(glob.glob(pattern))
    
    # If no pages found in subfolder, try the main chapter directory
    if not page_files:
        for ext in ['png', 'jpg', 'jpeg', 'webp']:
            pattern = os.path.join(chapter_source_dir, f"page*.{ext}")
            page_files.extend(glob.glob(pattern))
    
    if not page_files:
        print(f"    Warning: No manga pages found for {chapter_id}")
        return {}
    
    # Sort pages naturally (page01, page02, etc.)
    page_files.sort(key=lambda x: os.path.basename(x))
    
    # Create images directory in build
    build_images_dir = os.path.normpath(os.path.join(BUILD_DIR, "images", novel_slug, chapter_id))
    os.makedirs(build_images_dir, exist_ok=True)
    
    # Process each page
    pages_data = []
    for i, page_file in enumerate(page_files):
        page_filename = os.path.basename(page_file)
        dest_image_path = os.path.join(build_images_dir, page_filename)
        
        # Copy image to build directory
        shutil.copy2(page_file, dest_image_path)
        
        # Build page data
        page_number = i + 1
        page_path = f"../../../images/{novel_slug}/{chapter_id}/{page_filename}"
        
        # Generate alt text from pattern or use default
        alt_pattern = chapter_metadata.get('page_alt_pattern', '{story_title} Chapter {chapter_number}, Page {page}')
        story_title = novel_config.get('title', 'Manga')
        chapter_number = chapter_metadata.get('chapter_number', '?')
        alt_text = alt_pattern.format(
            story_title=story_title,
            chapter_number=chapter_number,
            page=page_number
        )
        
        page_data = {
            'number': page_number,
            'filename': page_filename,
            'path': page_path,
            'alt_text': alt_text
        }
        pages_data.append(page_data)
    
    # Get manga configuration
    manga_config = {
        'reading_direction': chapter_metadata.get('reading_direction', novel_config.get('reading_direction', 'ltr')),
        'cover_separate': chapter_metadata.get('cover_separate', novel_config.get('manga_defaults', {}).get('cover_separate', True)),
        'view_mode': novel_config.get('manga_defaults', {}).get('view_mode', 'single'),
        'image_scaling': novel_config.get('manga_defaults', {}).get('image_scaling', 'fit_screen'),
        'zoom_level': novel_config.get('manga_defaults', {}).get('zoom_level', 100),
        'preload_pages': novel_config.get('manga_defaults', {}).get('preload_pages', 3),
        'page_turn_area': novel_config.get('manga_defaults', {}).get('page_turn_area', 'right_half')
    }
    
    print(f"    Processed {len(pages_data)} manga pages for {chapter_id}")
    
    return {
        'pages': pages_data,
        'page_count': len(pages_data),
        'config': manga_config
    }

# Add the slugify_tag function as a Jinja2 filter
env.filters['slugify_tag'] = slugify_tag

# Add date formatting and new chapter detection filters
env.filters['format_date_for_display'] = format_date_for_display

# Create a configurable is_chapter_new filter that will be set up per template render
def create_is_chapter_new_filter(site_config, novel_config):
    """Create a configured is_chapter_new filter based on site and novel configs"""
    # Get site-level defaults
    site_new_config = site_config.get('new_chapter_tags', {})
    site_show_new = site_new_config.get('enabled', True)
    site_threshold = site_new_config.get('threshold_days', 7)
    
    # Get novel-level overrides
    novel_new_config = novel_config.get('new_chapter_tags', {}) if novel_config else {}
    show_new_tags = novel_new_config.get('enabled', site_show_new)
    threshold_days = novel_new_config.get('threshold_days', site_threshold)
    
    
    def is_chapter_new_filter(published_date_str, current_time=None):
        return is_chapter_new(published_date_str, current_time, threshold_days, show_new_tags)
    
    return is_chapter_new_filter

# Default filter (will be overridden during template rendering)
env.filters['is_chapter_new'] = lambda x: is_chapter_new(x)

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
    # Convert Markdown to HTML with essential extensions for web novels
    return markdown.markdown(md_content, extensions=[
        'tables',      # Table support for comparisons/data
        'footnotes',   # Author notes, translation notes
        'smarty',      # Professional typography (curly quotes, em-dashes)
        'attr_list',   # Custom CSS classes {: .class-name}
        'md_in_html',  # Mix markdown inside HTML blocks
        'abbr'         # Abbreviations with hover tooltips
    ])

def calculate_file_hash(filepath, length=8):
    """Calculate a partial hash of a file for cache busting"""
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()[:length]

def copy_static_assets():
    """Copy static assets with cache-busting hashed filenames"""
    asset_map = {}  # Map original names to hashed names
    
    if os.path.exists(STATIC_DIR):
        target_static_dir = os.path.normpath(os.path.join(BUILD_DIR, "static"))
        os.makedirs(target_static_dir, exist_ok=True)
        
        # Files to add cache busting
        cache_bust_files = ['style.css', 'theme-toggle.js']
        
        for root, dirs, files in os.walk(STATIC_DIR):
            rel_dir = os.path.relpath(root, STATIC_DIR)
            target_dir = os.path.join(target_static_dir, rel_dir) if rel_dir != '.' else target_static_dir
            
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            
            for file in files:
                src_file = os.path.join(root, file)
                
                if file in cache_bust_files:
                    # Generate hashed filename
                    file_hash = calculate_file_hash(src_file)
                    name, ext = os.path.splitext(file)
                    hashed_filename = f"{name}-{file_hash}{ext}"
                    dst_file = os.path.join(target_dir, hashed_filename)
                    
                    # Store mapping
                    asset_map[file] = hashed_filename
                else:
                    # Copy without modification
                    dst_file = os.path.join(target_dir, file)
                
                shutil.copy2(src_file, dst_file)
    
    return asset_map

def generate_static_pages(site_config):
    """Generate all static pages"""
    if not os.path.exists(PAGES_DIR):
        print("No pages directory found, skipping static page generation.")
        return
    
    print("Generating static pages...")
    
    # Get all available pages
    all_pages = get_all_pages()
    
    # Get available languages from site config or scan pages
    available_languages = site_config.get('languages', {}).get('available', ['en'])
    
    for page_data in all_pages:
        page_slug = page_data['slug']
        
        # Handle nested paths (e.g., "resources/translation-guide")
        if '/' in page_slug:
            page_languages = get_available_page_languages(page_slug)
        else:
            page_languages = get_available_page_languages(page_slug)
        
        for lang in available_languages:
            if lang not in page_languages:
                continue
            
            # Load page content for this language
            if '/' in page_slug:
                page_content, page_metadata = load_nested_page_content(page_slug, lang)
            else:
                page_content, page_metadata = load_page_content(page_slug, lang)
            
            if not page_content:
                continue
            
            # Skip if page should be skipped
            if should_skip_page(page_metadata, INCLUDE_DRAFTS):
                print(f"      Skipping draft/hidden page: {page_slug} ({lang})")
                continue
            
            # Create page directory
            page_dir = os.path.normpath(os.path.join(BUILD_DIR, page_slug, lang))
            os.makedirs(page_dir, exist_ok=True)
            
            # Calculate breadcrumb depth - need to account for nested directory structure
            # From resources/translation-guide/en/ we need to go up 3 levels to reach root
            breadcrumb_depth = page_slug.count('/') + 2  # +2 for lang and page itself
            
            # Build breadcrumbs
            breadcrumbs = [{'title': 'Home', 'url': '../' * breadcrumb_depth}]
            if '/' in page_slug:
                parts = page_slug.split('/')
                url_parts = []
                for i, part in enumerate(parts[:-1]):
                    url_parts.append(part)
                    # Need to go up the full breadcrumb_depth, then navigate to the parent page
                    parent_url = '../' * breadcrumb_depth + '/'.join(url_parts) + f'/{lang}/'
                    breadcrumbs.append({
                        'title': part.title(),
                        'url': parent_url
                    })
            breadcrumbs.append({'title': page_metadata.get('title', page_slug)})
            
            # Handle password protection
            is_password_protected = 'password' in page_metadata and page_metadata['password']
            encrypted_content = None
            password_hash = None
            
            if is_password_protected:
                # Convert markdown to HTML
                page_content_html = markdown.markdown(page_content)
                
                # Encrypt content
                password = page_metadata['password']
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                
                # Simple XOR encryption
                encrypted_content = ''
                for i, char in enumerate(page_content_html):
                    encrypted_content += chr(ord(char) ^ ord(password[i % len(password)]))
            else:
                # Convert markdown to HTML
                page_content_html = markdown.markdown(page_content)
            
            # Build social and SEO metadata
            page_url = f"{site_config.get('site_url', '').rstrip('/')}/{page_slug}/{lang}/"
            social_meta = build_social_meta(site_config, {}, page_metadata, 'page', page_metadata.get('title', ''), page_url)
            seo_meta = build_seo_meta(site_config, {}, page_metadata, 'page')
            
            # Check if comments are enabled
            comments_enabled = should_enable_comments(site_config, {}, page_metadata, 'page')
            comments_config = build_comments_config(site_config)
            
            # Get footer data
            footer_data = build_footer_content(site_config, {}, 'page')
            
            # Build navigation
            page_navigation = build_page_navigation(site_config, lang, page_slug)
            
            # Language URLs for switcher
            language_urls = {}
            for available_lang in page_languages:
                if available_lang in available_languages:
                    language_urls[available_lang] = f"../{available_lang}/"
            
            # Get navigation data
            navigation_data = build_page_navigation(site_config, lang, page_slug)
            
            # Generate page HTML
            page_html = render_template("page.html",
                                       page=page_metadata,
                                       content=page_content_html if not is_password_protected else '',
                                       current_language=lang,
                                       available_languages=page_languages,
                                       language_urls=language_urls,
                                       breadcrumbs=breadcrumbs,
                                       breadcrumb_depth=breadcrumb_depth,
                                       site_name=site_config.get('site_name', 'Web Novel Collection'),
                                       site_navigation=navigation_data['header'],
                                       footer_navigation=navigation_data['footer'],
                                       is_password_protected=is_password_protected,
                                       encrypted_content=encrypted_content,
                                       password_hash=password_hash,
                                       password_hint=page_metadata.get('password_hint'),
                                       social_title=social_meta['title'],
                                       social_description=social_meta['description'],
                                       social_image=social_meta['image'],
                                       social_url=social_meta['url'],
                                       seo_meta_description=seo_meta.get('meta_description'),
                                       seo_keywords=social_meta.get('keywords'),
                                       allow_indexing=seo_meta.get('allow_indexing', True),
                                       twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle'),
                                       footer_data=footer_data,
                                       comments_enabled=comments_enabled,
                                       comments_repo=comments_config['repo'],
                                       comments_issue_term=comments_config['issue_term'],
                                       comments_label=comments_config['label'],
                                       comments_theme=comments_config['theme'])
            
            # Write page
            with open(os.path.join(page_dir, "index.html"), "w", encoding='utf-8') as f:
                f.write(page_html)
            
            print(f"    Generated page: {page_slug} ({lang})")
    
    print("Static pages generated.")
    
    # Generate page index
    generate_page_index(site_config)

def generate_page_index(site_config):
    """Generate page index files showing all available static pages"""
    print("Generating page index...")
    
    all_pages = get_all_pages()
    available_languages = site_config.get('languages', {}).get('available', ['en'])
    
    for lang in available_languages:
        # Collect pages for this language
        page_categories = {}
        
        for page_data in all_pages:
            page_slug = page_data['slug']
            
            try:
                _, page_metadata = load_page_content(page_slug, lang)
                
                # Skip drafts unless include_drafts is True
                if should_skip_page(page_metadata, INCLUDE_DRAFTS):
                    continue
                
                # Determine category (top-level vs nested pages)
                if '/' in page_slug:
                    category = page_slug.split('/')[0].title()
                else:
                    category = 'Main Pages'
                
                if category not in page_categories:
                    page_categories[category] = []
                
                # Check if password protected
                is_password_protected = 'password' in page_metadata and page_metadata['password']
                
                # Get available languages for this page
                page_languages = get_available_page_languages(page_slug)
                
                # Build page URL - use the current language if available, otherwise fallback to English
                target_lang = lang if lang in page_languages else 'en'
                if '/' in page_slug:
                    page_url = f"{page_slug}/{target_lang}/"
                else:
                    page_url = f"{page_slug}/{target_lang}/"
                
                page_info = {
                    'title': page_metadata.get('title', page_slug.replace('/', ' - ').title()),
                    'description': page_metadata.get('description', ''),
                    'url': page_url,
                    'updated': page_metadata.get('updated'),
                    'is_password_protected': is_password_protected,
                    'languages': page_languages,
                    'slug': page_slug
                }
                
                page_categories[category].append(page_info)
                
            except:
                # Skip pages that don't exist for this language
                continue
        
        # Sort categories and pages within categories
        for category in page_categories:
            page_categories[category].sort(key=lambda x: x['title'])
        
        # Get site navigation
        navigation_data = build_page_navigation(site_config, lang)
        
        # Get footer data
        footer_data = build_footer_content(site_config, {}, 'page')
        
        # Generate social meta
        social_meta = {
            'title': f"Site Pages | {site_config.get('site_name', 'Web Novel Collection')}",
            'description': f"Browse all pages available on {site_config.get('site_name', 'Web Novel Collection')}",
            'image': site_config.get('site_url', '').rstrip('/') + site_config.get('social_embeds', {}).get('default_image', '/static/images/site-default-social.jpg'),
            'url': site_config.get('site_url', '').rstrip('/') + '/pages/'
        }
        
        # Generate page index HTML
        page_index_html = render_template("page_index.html",
                                         current_language=lang,
                                         available_languages=available_languages,
                                         site_name=site_config.get('site_name', 'Web Novel Collection'),
                                         site_navigation=navigation_data['header'],
                                         footer_navigation=navigation_data['footer'],
                                         page_categories=page_categories,
                                         footer_data=footer_data,
                                         social_image=social_meta['image'],
                                         site_url=site_config.get('site_url', '').rstrip('/'),
                                         twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle'))
        
        # Write page index file
        index_filename = f"pages-{lang}.html" if lang != 'en' else "pages.html"
        with open(os.path.join(BUILD_DIR, index_filename), "w", encoding='utf-8') as f:
            f.write(page_index_html)
        
        print(f"    Generated page index: {index_filename}")
    
    print("Page index generated.")

def render_template(template_name, novel_slug=None, site_config=None, novel_config=None, asset_map=None, **kwargs):
    """Render a template with optional novel-specific override support"""
    template_env = None
    
    if novel_slug:
        # Use novel-specific template environment if novel_slug is provided
        novel_env = get_novel_template_env(novel_slug)
        template_env = novel_env
        template = novel_env.get_template(template_name)
    else:
        # Use global template environment for non-novel-specific templates
        template_env = env
        template = env.get_template(template_name)
    
    # Set up configurable is_chapter_new filter if configs are provided
    if site_config is not None:
        is_chapter_new_filter = create_is_chapter_new_filter(site_config, novel_config)
        template_env.filters['is_chapter_new'] = is_chapter_new_filter
    
    # Add asset map to kwargs
    if asset_map:
        kwargs['asset_map'] = asset_map
    
    return template.render(**kwargs)

def build_site(include_drafts=False, include_scheduled=False, no_epub=False, optimize_images=False, serve_mode=False, serve_port=8000):
    global INCLUDE_DRAFTS, INCLUDE_SCHEDULED, ASSET_MAP
    INCLUDE_DRAFTS = include_drafts
    INCLUDE_SCHEDULED = include_scheduled
    ASSET_MAP = {}
    
    print("Building site...")
    if os.path.exists(BUILD_DIR):
        # On Windows, retry deletion if it fails due to file locks
        import time
        for attempt in range(3):
            try:
                shutil.rmtree(BUILD_DIR)
                break
            except (OSError, PermissionError) as e:
                if attempt < 2:
                    print(f"Retrying directory deletion (attempt {attempt + 1})...")
                    time.sleep(0.5)
                else:
                    raise e
    
    # Ensure directory is created with retry
    for attempt in range(3):
        try:
            os.makedirs(BUILD_DIR, exist_ok=True)
            break
        except (OSError, PermissionError) as e:
            if attempt < 2:
                print(f"Retrying directory creation (attempt {attempt + 1})...")
                time.sleep(0.5)
            else:
                raise e

    ASSET_MAP = copy_static_assets()
    
    # Load site configuration
    site_config = load_site_config()
    
    # Generate static pages
    generate_static_pages(site_config)

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

    # Generate webring data
    webring_config = load_webring_config()
    display_config = {}
    if os.path.exists(os.path.join(os.getcwd(), "webring.yaml")):
        with open(os.path.join(os.getcwd(), "webring.yaml"), 'r', encoding='utf-8') as f:
            full_config = yaml.safe_load(f)
            display_config = full_config.get('display', {})
    
    webring_data = generate_webring_data(webring_config, display_config)

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
                               footer_data=footer_data,
                               webring_data=webring_data,
                               webring_title=display_config.get('title'),
                               webring_subtitle=display_config.get('subtitle'),
                               webring_show_dates=display_config.get('show_dates', True),
                               webring_show_descriptions=display_config.get('show_descriptions', True)))

    # Generate author pages
    authors_config = load_authors_config()
    author_contributions = collect_author_contributions(all_novels_data)
    
    if authors_config:
        # Create authors directory
        authors_dir = os.path.normpath(os.path.join(BUILD_DIR, "authors"))
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
            author_dir = os.path.normpath(os.path.join(authors_dir, username))
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
        novel_dir = os.path.normpath(os.path.join(BUILD_DIR, novel_slug))
        os.makedirs(novel_dir, exist_ok=True)

        # Generate story-specific RSS feed
        story_rss_content = generate_rss_feed(site_config, all_novels_data, novel_config, novel_slug)
        with open(os.path.join(novel_dir, "rss.xml"), "w", encoding='utf-8') as f:
            f.write(story_rss_content)

        # Process each language
        for lang in available_languages:
            lang_dir = os.path.normpath(os.path.join(novel_dir, lang))
            os.makedirs(lang_dir, exist_ok=True)

            # Render table of contents page for this novel/language
            toc_dir = os.path.normpath(os.path.join(lang_dir, "toc"))
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
                                       novel_slug=novel_slug,
                                       site_config=site_config,
                                       novel_config=novel_config,
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
                    
                    # Skip draft/scheduled chapters unless flags are set
                    if should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS, INCLUDE_SCHEDULED):
                        # Safe printing that handles Unicode issues
                        safe_title = chapter_title.encode('ascii', errors='replace').decode('ascii')
                        if is_chapter_draft(chapter_metadata):
                            print(f"      Skipping draft chapter: {chapter_id} - {safe_title}")
                        elif is_chapter_scheduled_future(chapter_metadata):
                            publish_date = chapter_metadata.get('published', 'Unknown')
                            print(f"      Skipping scheduled chapter: {chapter_id} - {safe_title} (publish: {publish_date})")
                        else:
                            print(f"      Skipping chapter: {chapter_id} - {safe_title}")
                        continue
                    
                    # Determine if this is a manga chapter
                    story_chapter_type = novel_config.get('chapter_type')
                    chapter_type = chapter_metadata.get('type', story_chapter_type)
                    is_manga_chapter = chapter_type == 'manga'
                    
                    # Initialize manga data
                    manga_data = None
                    
                    if is_manga_chapter:
                        # Process manga pages instead of regular content
                        print(f"      Processing manga chapter: {chapter_id}")
                        manga_data = process_manga_pages(novel_slug, chapter_id, lang, chapter_metadata, novel_config)
                        
                        if not manga_data:
                            print(f"      Error: No manga pages found for {chapter_id}, skipping...")
                            continue
                        
                        # For manga chapters, still process the markdown content for display below images
                        chapter_content_html = convert_markdown_to_html(chapter_content_md)
                    else:
                        # Process regular chapter images and update markdown
                        chapter_content_md = process_chapter_images(novel_slug, chapter_id, lang, chapter_content_md)
                    
                    # Handle password protection
                    is_password_protected = 'password' in chapter_metadata and chapter_metadata['password']
                    encrypted_content = None
                    password_hash = None
                    password_hint = None
                    
                    if is_password_protected:
                        if not is_manga_chapter:
                            # Convert markdown to HTML first for regular chapters
                            chapter_content_html = convert_markdown_to_html(chapter_content_md)
                        else:
                            # For manga chapters, we'll handle this in the template
                            chapter_content_html = ""
                        
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
                        if not is_manga_chapter:
                            # Only convert markdown for non-manga chapters
                            chapter_content_html = convert_markdown_to_html(chapter_content_md)
                    
                    # Use navigation function to skip hidden chapters
                    prev_chapter, next_chapter = get_navigation_chapters(novel_slug, all_chapters, chapter_id, lang)

                    # Use front matter title if available, otherwise use chapter title from config
                    display_title = chapter_metadata.get('title', chapter_title)
                    
                    # Determine what to display based on config and front matter
                    show_tags = should_show_tags(novel_config, chapter_metadata, translation_missing=False)
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
                    
                    chapter_dir = os.path.normpath(os.path.join(lang_dir, chapter_id))
                    os.makedirs(chapter_dir, exist_ok=True)
                    with open(os.path.join(chapter_dir, "index.html"), "w", encoding='utf-8') as f:
                        # Filter out hidden chapters for chapter dropdown
                        filtered_novel = filter_hidden_chapters_from_novel(novel, novel_slug, lang)
                        f.write(render_template("chapter.html", 
                                                novel_slug=novel_slug,
                                                novel=filtered_novel,
                                                novel_title=novel['title'],
                                                arcs=novel['arcs'],
                                                chapter=chapter,
                                                chapter_id=chapter_id,
                                                chapter_title=display_title,
                                                chapter_content=chapter_content_html,
                                                chapter_metadata=chapter_metadata,
                                                prev_chapter=prev_chapter,
                                                next_chapter=next_chapter,
                                                language=lang,
                                                current_language=lang,
                                                available_languages=available_languages,
                                                show_tags=show_tags,
                                                show_metadata=show_metadata,
                                                show_translation_notes=show_translation_notes,
                                                password_protected=is_password_protected,
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
                                                footer_copyright=footer_data['copyright'],
                                                footer_links=footer_data['links'],
                                                footer_data=footer_data,
                                                comments_enabled=comments_enabled,
                                                comments_repo=comments_config['repo'],
                                                comments_issue_term=comments_config['issue_term'],
                                                comments_label=comments_config['label'],
                                                comments_theme=comments_config['theme'],
                                                is_serve_mode=serve_mode,
                                                serve_port=serve_port if serve_mode else None,
                                                is_manga_chapter=is_manga_chapter,
                                                manga_data=manga_data))
                else:
                    # Generate chapter page showing "not translated" message in primary language
                    chapter_content_md, chapter_metadata = load_chapter_content(novel_slug, chapter_id, primary_lang)
                    
                    # Skip draft/scheduled chapters unless flags are set (same check as above)
                    if should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS, INCLUDE_SCHEDULED):
                        # Safe printing that handles Unicode issues
                        safe_title = chapter_title.encode('ascii', errors='replace').decode('ascii')
                        if is_chapter_draft(chapter_metadata):
                            print(f"      Skipping draft chapter: {chapter_id} - {safe_title}")
                        elif is_chapter_scheduled_future(chapter_metadata):
                            publish_date = chapter_metadata.get('published', 'Unknown')
                            print(f"      Skipping scheduled chapter: {chapter_id} - {safe_title} (publish: {publish_date})")
                        else:
                            print(f"      Skipping chapter: {chapter_id} - {safe_title}")
                        continue
                    
                    # Determine if this is a manga chapter
                    story_chapter_type = novel_config.get('chapter_type')
                    chapter_type = chapter_metadata.get('type', story_chapter_type)
                    is_manga_chapter = chapter_type == 'manga'
                    
                    # Initialize manga data
                    manga_data = None
                    
                    if is_manga_chapter:
                        # Process manga pages instead of regular content (using primary language)
                        print(f"      Processing manga chapter (untranslated): {chapter_id}")
                        manga_data = process_manga_pages(novel_slug, chapter_id, primary_lang, chapter_metadata, novel_config)
                        
                        if not manga_data:
                            print(f"      Error: No manga pages found for {chapter_id}, skipping...")
                            continue
                        
                        # For manga chapters, still process the markdown content for display below images
                        chapter_content_html = convert_markdown_to_html(chapter_content_md)
                    else:
                        # Process regular chapter images and update markdown (using primary language)
                        chapter_content_md = process_chapter_images(novel_slug, chapter_id, primary_lang, chapter_content_md)
                    
                    # Handle password protection (same as above)
                    is_password_protected = 'password' in chapter_metadata and chapter_metadata['password']
                    encrypted_content = None
                    password_hash = None
                    password_hint = None
                    
                    if is_password_protected:
                        if not is_manga_chapter:
                            # Convert markdown to HTML first for regular chapters
                            chapter_content_html = convert_markdown_to_html(chapter_content_md)
                        else:
                            # For manga chapters, we'll handle this in the template
                            chapter_content_html = ""
                        
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
                        if not is_manga_chapter:
                            # Only convert markdown for non-manga chapters
                            chapter_content_html = convert_markdown_to_html(chapter_content_md)
                    
                    # Use navigation function to skip hidden chapters
                    prev_chapter, next_chapter = get_navigation_chapters(novel_slug, all_chapters, chapter_id, lang)

                    # Use front matter title if available, otherwise use chapter title from config
                    display_title = chapter_metadata.get('title', chapter_title)
                    
                    # Determine what to display based on config and front matter
                    show_tags = should_show_tags(novel_config, chapter_metadata, translation_missing=True)
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
                    
                    chapter_dir = os.path.normpath(os.path.join(lang_dir, chapter_id))
                    os.makedirs(chapter_dir, exist_ok=True)
                    with open(os.path.join(chapter_dir, "index.html"), "w", encoding='utf-8') as f:
                        # Filter out hidden chapters for chapter dropdown
                        filtered_novel = filter_hidden_chapters_from_novel(novel, novel_slug, lang)
                        f.write(render_template("chapter.html", 
                                                novel_slug=novel_slug,
                                                novel=filtered_novel,
                                                novel_title=novel['title'],
                                                arcs=novel['arcs'],
                                                chapter=chapter,
                                                chapter_id=chapter_id,
                                                chapter_title=display_title,
                                                chapter_content=chapter_content_html,
                                                chapter_metadata=chapter_metadata,
                                                prev_chapter=prev_chapter,
                                                next_chapter=next_chapter,
                                                language=lang,
                                                current_language=lang,
                                                primary_language=primary_lang,
                                                requested_language=lang,
                                                translation_missing=True,
                                                available_languages=available_languages,
                                                show_tags=show_tags,
                                                show_metadata=show_metadata,
                                                show_translation_notes=show_translation_notes,
                                                password_protected=is_password_protected,
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
                                                footer_copyright=footer_data['copyright'],
                                                footer_links=footer_data['links'],
                                                footer_data=footer_data,
                                                comments_enabled=comments_enabled,
                                                comments_repo=comments_config['repo'],
                                                comments_issue_term=comments_config['issue_term'],
                                                comments_label=comments_config['label'],
                                                comments_theme=comments_config['theme'],
                                                is_serve_mode=serve_mode,
                                                serve_port=serve_port if serve_mode else None,
                                                is_manga_chapter=is_manga_chapter,
                                                manga_data=manga_data))

        # Generate tag pages for this language (after all chapters are processed)
        for lang in available_languages:
            lang_dir = os.path.join(novel_dir, lang)
            tags_data = collect_tags_for_novel(novel_slug, lang)
            if tags_data:
                # Create tags directory
                tags_dir = os.path.normpath(os.path.join(lang_dir, "tags"))
                os.makedirs(tags_dir, exist_ok=True)
                
                # Create tag slug mapping for templates
                tag_slug_map = {tag: slugify_tag(tag) for tag in tags_data.keys()}
                
                # Generate main tags index page
                with open(os.path.join(tags_dir, "index.html"), "w", encoding='utf-8') as f:
                    f.write(render_template("tags_index.html",
                                            novel_slug=novel_slug,
                                            novel=novel,
                                            tags_data=tags_data,
                                            tag_slug_map=tag_slug_map,
                                            current_language=lang,
                                            available_languages=available_languages))
                
                # Generate individual tag pages
                for tag, chapters in tags_data.items():
                    tag_slug = slugify_tag(tag)
                    tag_page_dir = os.path.normpath(os.path.join(tags_dir, tag_slug))
                    os.makedirs(tag_page_dir, exist_ok=True)
                    
                    # Build cross-language tag mapping for this tag
                    cross_lang_tags = {}
                    for other_lang in available_languages:
                        if other_lang != lang:
                            other_tags_data = collect_tags_for_novel(novel_slug, other_lang)
                            # For now, just check if any tags exist in other language
                            # (proper cross-language tag mapping would require more complex logic)
                            if other_tags_data:
                                cross_lang_tags[other_lang] = None  # Don't show cross-language links for now
                    
                    with open(os.path.join(tag_page_dir, "index.html"), "w", encoding='utf-8') as f:
                        f.write(render_template("tag_page.html",
                                                novel_slug=novel_slug,
                                                novel=novel,
                                                tag_name=tag,
                                                tag_slug=tag_slug,
                                                chapters=chapters,
                                                current_language=lang,
                                                available_languages=available_languages,
                                                cross_lang_tags=cross_lang_tags))

    # Generate EPUB downloads after all HTML is built (unless --no-epub)
    if not no_epub:
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
                        all_chapters = get_non_hidden_chapters(novel_config, novel_slug, language, INCLUDE_DRAFTS, INCLUDE_SCHEDULED)
                        for arc_index, arc in enumerate(all_chapters):
                            if arc['chapters']:  # Only generate if arc has chapters
                                if generate_arc_epub(novel_slug, novel_config, site_config, arc_index, novel, language):
                                    print(f"    Generated EPUB for {novel_slug} - {arc['title']}{language_suffix}")
    else:
        print("Skipping EPUB generation (--no-epub flag)")
    
    # Update TOC pages with download links after downloads are generated (if EPUBs were generated)
    if not no_epub:
        print("Updating TOC pages with download links...")
    else:
        print("Updating TOC pages...")
    for novel in all_novels_data:
        novel_slug = novel['slug']
        novel_config = load_novel_config(novel_slug)
        available_languages = novel_config.get('languages', {}).get('available', ['en'])
        
        # Update TOC for each language
        for lang in available_languages:
            update_toc_with_downloads(novel, novel_slug, novel_config, site_config, lang)

    # Optimize images if enabled or forced
    optimize_all_images(site_config, optimize_images)

    print("Site built.")

def check_broken_links():
    """Check for broken internal links in the generated site"""
    print("\n" + "="*50)
    print("BROKEN LINK CHECK")
    print("="*50)
    
    build_dir = Path(BUILD_DIR)
    if not build_dir.exists():
        print("[ERROR] Build directory not found. Please generate the site first.")
        return
    
    # Load site config for URL validation
    site_config = load_site_config()
    
    broken_links = []
    total_files_checked = 0
    
    # Find all HTML files in build directory
    html_files = list(build_dir.rglob("*.html"))
    
    print(f"[INFO] Checking {len(html_files)} HTML files for broken links...")
    
    for html_file in html_files:
        total_files_checked += 1
        relative_path = html_file.relative_to(build_dir)
        
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'html.parser')
            file_dir = html_file.parent
            
            # Check internal links (<a href="">)
            for link in soup.find_all('a', href=True):
                href = link['href']
                if is_internal_link(href):
                    target_path = resolve_link_path(file_dir, href, build_dir)
                    if target_path and not target_path.exists():
                        try:
                            target_rel = str(target_path.relative_to(build_dir))
                        except ValueError:
                            target_rel = str(target_path)
                        broken_links.append({
                            'type': 'Internal Link',
                            'url': href,
                            'source_file': str(relative_path),
                            'target_path': target_rel
                        })
            
            # Check images (<img src="">)
            for img in soup.find_all('img', src=True):
                src = img['src']
                if is_internal_link(src):
                    target_path = resolve_link_path(file_dir, src, build_dir)
                    if target_path and not target_path.exists():
                        try:
                            target_rel = str(target_path.relative_to(build_dir))
                        except ValueError:
                            target_rel = str(target_path)
                        broken_links.append({
                            'type': 'Image',
                            'url': src,
                            'source_file': str(relative_path),
                            'target_path': target_rel
                        })
            
            # Check social embed images (og:image, twitter:image)
            for meta in soup.find_all('meta'):
                if meta.get('property') == 'og:image' or meta.get('name') == 'twitter:image':
                    content_attr = meta.get('content', '')
                    target_path = None
                    
                    if content_attr and is_internal_link(content_attr):
                        # Handle relative/absolute internal links
                        target_path = resolve_link_path(file_dir, content_attr, build_dir)
                    elif content_attr and is_local_site_url(content_attr, site_config):
                        # Handle site URLs (https://site.com/path/to/file.jpg)
                        target_path = convert_site_url_to_local_path(content_attr, site_config, build_dir)
                    
                    if target_path and not target_path.exists():
                        try:
                            target_rel = str(target_path.relative_to(build_dir))
                        except ValueError:
                            target_rel = str(target_path)
                        broken_links.append({
                            'type': 'Social Embed Image',
                            'url': content_attr,
                            'source_file': str(relative_path),
                            'target_path': target_rel
                        })
            
            # Check CSS files
            for link_tag in soup.find_all('link', href=True):
                if 'stylesheet' in link_tag.get('rel', []):
                    href = link_tag['href']
                    if is_internal_link(href):
                        target_path = resolve_link_path(file_dir, href, build_dir)
                        if target_path and not target_path.exists():
                            try:
                                target_rel = str(target_path.relative_to(build_dir))
                            except ValueError:
                                target_rel = str(target_path)
                            broken_links.append({
                                'type': 'CSS File',
                                'url': href,
                                'source_file': str(relative_path),
                                'target_path': target_rel
                            })
            
            # Check JavaScript files
            for script in soup.find_all('script', src=True):
                src = script['src']
                if is_internal_link(src):
                    target_path = resolve_link_path(file_dir, src, build_dir)
                    if target_path and not target_path.exists():
                        try:
                            target_rel = str(target_path.relative_to(build_dir))
                        except ValueError:
                            target_rel = str(target_path)
                        broken_links.append({
                            'type': 'JavaScript File',
                            'url': src,
                            'source_file': str(relative_path),
                            'target_path': target_rel
                        })
                        
        except Exception as e:
            try:
                print(f"[WARNING] Error parsing {relative_path}: {e}")
            except UnicodeEncodeError:
                print(f"[WARNING] Error parsing {relative_path}: <encoding error>")
    
    # Report results
    print(f"\n[RESULTS]")
    print(f"   Files checked: {total_files_checked}")
    print(f"   Broken links found: {len(broken_links)}")
    
    if broken_links:
        print(f"\n[ERROR] BROKEN LINKS DETECTED:")
        print("-" * 50)
        
        # Group by type
        by_type = {}
        for link in broken_links:
            link_type = link['type']
            if link_type not in by_type:
                by_type[link_type] = []
            by_type[link_type].append(link)
        
        # Generate markdown report
        report_path = os.path.join(os.path.dirname(BUILD_DIR), "broken_links_report.md")
        with open(report_path, 'w', encoding='utf-8') as report_file:
            report_file.write("# Broken Links Report\n\n")
            report_file.write(f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            report_file.write(f"**Files Checked:** {total_files_checked}\n")
            report_file.write(f"**Broken Links Found:** {len(broken_links)}\n\n")
            
            report_file.write("## Summary by Type\n\n")
            report_file.write("| Link Type | Count |\n")
            report_file.write("|-----------|-------|\n")
            for link_type, links in by_type.items():
                report_file.write(f"| {link_type} | {len(links)} |\n")
            report_file.write("\n")
            
            report_file.write("## Detailed Report\n\n")
            
            for link_type, links in by_type.items():
                report_file.write(f"### {link_type} ({len(links)} broken)\n\n")
                report_file.write("| URL | Source File | Target Path |\n")
                report_file.write("|-----|-------------|-------------|\n")
                
                for link in links:
                    # Escape pipe characters in URLs
                    url = link['url'].replace('|', '\\|')
                    source = link['source_file'].replace('\\', '/')
                    target = link['target_path'].replace('\\', '/')
                    report_file.write(f"| `{url}` | `{source}` | `{target}` |\n")
                
                report_file.write("\n")
        
        print(f"\n[INFO] Detailed report written to: {report_path}")
        
        for link_type, links in by_type.items():
            print(f"\n[{link_type.upper()}] ({len(links)} broken):")
            for link in links[:10]:  # Show first 10 of each type
                print(f"   [X] {link['url']}")
                print(f"       Source: {link['source_file']}")
                print(f"       Target: {link['target_path']}")
                print()
            
            if len(links) > 10:
                print(f"   ... and {len(links) - 10} more {link_type.lower()} links")
                print()
        
        print("\n[FAILED] Link check FAILED - broken links detected!")
        return False
    else:
        print("\n[SUCCESS] All links are working correctly!")
        print("[PASSED] Link check PASSED!")
        
        # Remove any existing report file if all links are good
        report_path = os.path.join(os.path.dirname(BUILD_DIR), "broken_links_report.md")
        if os.path.exists(report_path):
            os.remove(report_path)
            print(f"[INFO] Removed old broken links report: {report_path}")
        
        return True

def check_accessibility_issues(site_config):
    """Check for accessibility issues in the generated site"""
    if not site_config.get('accessibility', {}).get('enabled', True):
        return True
    
    accessibility_config = site_config.get('accessibility', {})
    enforce_alt_text = accessibility_config.get('enforce_alt_text', True)
    build_reports = accessibility_config.get('build_reports', True)
    
    # Skip report generation in GitHub Actions unless explicitly enabled
    is_github_actions = os.environ.get('GITHUB_ACTIONS') == 'true'
    if is_github_actions and not build_reports:
        print("[INFO] Skipping accessibility report generation (GitHub Actions detected)")
        return True
    
    print("\n" + "="*50)
    print("ACCESSIBILITY CHECK")
    print("="*50)
    
    accessibility_issues = []
    
    if enforce_alt_text:
        alt_text_issues = check_missing_alt_text()
        accessibility_issues.extend(alt_text_issues)
    
    # Future: Add more accessibility checks here
    # - ARIA label validation
    # - Keyboard navigation checks
    # - Color contrast validation
    # - Heading hierarchy validation
    
    if accessibility_issues:
        print(f"\n[WARNING] Found {len(accessibility_issues)} accessibility issue(s)")
        
        if build_reports and not is_github_actions:
            generate_accessibility_report(accessibility_issues)
        
        return False
    else:
        print("\n[SUCCESS] No accessibility issues found!")
        print("[PASSED] Accessibility check PASSED!")
        
        # Remove any existing accessibility report if no issues
        report_path = os.path.join(os.path.dirname(BUILD_DIR), "images_missing_alt_text_report.md")
        if os.path.exists(report_path):
            os.remove(report_path)
            print(f"[INFO] Removed old accessibility report: {report_path}")
        
        return True

def check_missing_alt_text():
    """Check for images missing alt text in the generated site"""
    missing_alt_issues = []
    build_dir = Path(BUILD_DIR)
    
    if not build_dir.exists():
        print("[ERROR] Build directory not found. Run a build first.")
        return missing_alt_issues
    
    # Find all HTML files
    html_files = list(build_dir.glob("**/*.html"))
    print(f"[INFO] Checking {len(html_files)} HTML files for images missing alt text...")
    
    for html_file in html_files:
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'html.parser')
            images = soup.find_all('img')
            
            for img in images:
                src = img.get('src', '')
                alt = img.get('alt', '').strip()
                
                # Skip if no src
                if not src:
                    continue
                
                # Check if alt text is missing or empty
                if not alt:
                    # Get relative path from build directory
                    relative_html_path = html_file.relative_to(build_dir)
                    
                    missing_alt_issues.append({
                        'file': str(relative_html_path),
                        'image_src': src,
                        'issue': 'Missing alt text',
                        'severity': 'warning'
                    })
                    
                    print(f"[WARNING] Missing alt text: {src} in {relative_html_path}")
        
        except Exception as e:
            print(f"[ERROR] Could not parse {html_file}: {e}")
    
    return missing_alt_issues

def generate_accessibility_report(issues):
    """Generate a markdown report of accessibility issues"""
    report_path = os.path.join(os.path.dirname(BUILD_DIR), "images_missing_alt_text_report.md")
    
    # Group issues by type
    alt_text_issues = [issue for issue in issues if 'alt text' in issue['issue']]
    
    report_content = []
    report_content.append("# Accessibility Issues Report")
    report_content.append("")
    report_content.append(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_content.append("")
    
    if alt_text_issues:
        report_content.append("## Images Missing Alt Text")
        report_content.append("")
        report_content.append("Images without alt text are inaccessible to screen readers and assistive technologies.")
        report_content.append("")
        report_content.append("| File | Image Source | Issue |")
        report_content.append("|------|-------------|-------|")
        
        for issue in alt_text_issues:
            report_content.append(f"| {issue['file']} | {issue['image_src']} | {issue['issue']} |")
        
        report_content.append("")
        report_content.append("### How to Fix")
        report_content.append("Add meaningful alt text to images in your markdown files:")
        report_content.append("```markdown")
        report_content.append("![Description of image](image.jpg \"Optional title\")")
        report_content.append("```")
        report_content.append("")
    
    # Add summary
    report_content.append("## Summary")
    report_content.append("")
    report_content.append(f"- **Total Issues**: {len(issues)}")
    report_content.append(f"- **Missing Alt Text**: {len(alt_text_issues)}")
    
    if len(issues) > 0:
        report_content.append("")
        report_content.append("### Recommendations")
        report_content.append("1. Add descriptive alt text to all images")
        report_content.append("2. Use empty alt text (`alt=\"\"`) for decorative images")
        report_content.append("3. Ensure alt text describes the content and function of the image")
        report_content.append("4. Keep alt text concise but informative")
    
    # Write report
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_content))
        
        print(f"[INFO] Accessibility report generated: {report_path}")
        
    except Exception as e:
        print(f"[ERROR] Could not generate accessibility report: {e}")

def is_internal_link(url):
    """Check if a URL is an internal link (not external or data/mailto/etc)"""
    if not url:
        return False
    
    # Skip external URLs, data URLs, mailto, etc.
    if url.startswith(('http://', 'https://', 'mailto:', 'tel:', 'data:', '//', '#')):
        return False
    
    # Skip anchor-only links
    if url.startswith('#'):
        return False
        
    return True

def is_local_site_url(url, site_config):
    """Check if a URL belongs to the local site domain"""
    if not url or not site_config:
        return False
    
    site_url = site_config.get('site_url', '').rstrip('/')
    if not site_url:
        return False
    
    return url.startswith(site_url + '/')

def convert_site_url_to_local_path(url, site_config, build_dir):
    """Convert a site URL to a local file path"""
    site_url = site_config.get('site_url', '').rstrip('/')
    if not url.startswith(site_url + '/'):
        return None
    
    # Remove site URL prefix to get relative path
    relative_path = url[len(site_url) + 1:]
    return Path(build_dir) / relative_path

def resolve_link_path(current_file_dir, link_url, build_dir):
    """Resolve a relative or absolute link to a file path in the build directory"""
    try:
        # Handle absolute paths from site root
        if link_url.startswith('/'):
            target_path = build_dir / link_url.lstrip('/')
        else:
            # Handle relative paths
            target_path = (current_file_dir / link_url).resolve()
        
        # Remove query strings and fragments
        url_parts = str(target_path).split('?')[0].split('#')[0]
        target_path = Path(url_parts)
        
        # If path doesn't exist but ends with /, try with index.html first
        if str(link_url).endswith('/'):
            index_path = target_path / 'index.html'
            if index_path.exists():
                return index_path
        
        # If path doesn't exist as-is, try with index.html appended (for directory links)
        if not target_path.exists():
            if target_path.is_dir():
                index_path = target_path / 'index.html'
                if index_path.exists():
                    return index_path
            else:
                # Try treating as directory and adding index.html
                index_path = target_path / 'index.html'
                if index_path.exists():
                    return index_path
        
        return target_path
        
    except Exception:
        return None

def clean_build_directory():
    """Delete the build directory to ensure a fresh build"""
    build_dir = Path(BUILD_DIR)
    if build_dir.exists():
        print(f"[INFO] Cleaning build directory: {BUILD_DIR}")
        import shutil
        shutil.rmtree(build_dir)
        print(f"[INFO] Build directory cleaned")
    else:
        print(f"[INFO] Build directory does not exist, nothing to clean")

def validate_all_configs():
    """Validate all config files and content without building"""
    print("Validating configuration files and content...")
    errors = []
    warnings = []
    
    # Validate site config
    try:
        site_config = load_site_config()
        print("[OK] Site config loaded successfully")
        
        # Check required fields
        if not site_config.get('site_name'):
            warnings.append("Missing site_name in site_config.yaml")
        if not site_config.get('site_url'):
            warnings.append("Missing site_url in site_config.yaml")
        
        # Check image optimization requirements
        img_opt = site_config.get('image_optimization', {})
        if img_opt.get('enabled', False):
            try:
                from PIL import Image
            except ImportError:
                errors.append("Image optimization enabled but Pillow library not found. Install with: pip install Pillow")
        
        # Check development server dependencies (informational only)
        try:
            import watchdog
            import websockets
        except ImportError:
            warnings.append("Development server dependencies not found. Install with: pip install watchdog websockets")
            
    except Exception as e:
        errors.append(f"Error loading site_config.yaml: {e}")
    
    # Validate novel configs
    content_dir = Path(CONTENT_DIR)
    if not content_dir.exists():
        errors.append(f"Content directory not found: {CONTENT_DIR}")
        print_validation_results(errors, warnings)
        return
    
    novel_dirs = [d for d in content_dir.iterdir() if d.is_dir()]
    print(f"[INFO] Found {len(novel_dirs)} novel directories")
    
    for novel_dir in novel_dirs:
        novel_slug = novel_dir.name
        config_file = novel_dir / "config.yaml"
        
        if not config_file.exists():
            errors.append(f"Missing config.yaml for novel: {novel_slug}")
            continue
            
        try:
            novel_config = load_novel_config(novel_slug)
            print(f"[OK] Novel config loaded: {novel_slug}")
            
            # Check required fields
            if not novel_config.get('title'):
                errors.append(f"Missing title in {novel_slug}/config.yaml")
            if not novel_config.get('arcs'):
                errors.append(f"Missing arcs in {novel_slug}/config.yaml")
                
            # Validate chapters exist
            chapters_dir = novel_dir / "chapters"
            if not chapters_dir.exists():
                errors.append(f"Missing chapters directory for novel: {novel_slug}")
                continue
                
            # Check if referenced chapters exist
            for arc in novel_config.get('arcs', []):
                for chapter in arc.get('chapters', []):
                    chapter_id = chapter.get('id')
                    if chapter_id:
                        chapter_file = chapters_dir / f"{chapter_id}.md"
                        if not chapter_file.exists():
                            errors.append(f"Missing chapter file: {novel_slug}/chapters/{chapter_id}.md")
                        else:
                            # Validate chapter front matter
                            try:
                                front_matter, content = parse_front_matter(chapter_file.read_text(encoding='utf-8'))
                                if content.strip() == "":
                                    warnings.append(f"Empty chapter content: {novel_slug}/chapters/{chapter_id}.md")
                            except Exception as e:
                                errors.append(f"Error parsing chapter {novel_slug}/{chapter_id}: {e}")
                                
        except Exception as e:
            errors.append(f"Error loading config for novel {novel_slug}: {e}")
    
    print_validation_results(errors, warnings)

def print_validation_results(errors, warnings):
    """Print validation results and exit with appropriate code"""
    print("\n" + "="*50)
    print("VALIDATION RESULTS")
    print("="*50)
    
    if warnings:
        print(f"\n[WARNINGS] ({len(warnings)} found):")
        for warning in warnings:
            print(f"  [!] {warning}")
    
    if errors:
        print(f"\n[ERRORS] ({len(errors)} found):")
        for error in errors:
            print(f"  [X] {error}")
        print("\n[FAILED] Validation failed - please fix errors before building")
        exit(1)
    else:
        print(f"\n[SUCCESS] Validation passed!")
        if warnings:
            print(f"Note: {len(warnings)} warnings found (non-critical)")
        print("[PASSED] All configs and content are valid")

def optimize_images_to_webp(source_dir, target_dir, quality=None):
    """Convert images to WebP format with optional compression"""
    try:
        from PIL import Image
        import os
        from pathlib import Path
        
        if quality is None:
            quality = 100  # No compression by default
        
        source_path = Path(source_dir)
        target_path = Path(target_dir)
        
        if not source_path.exists():
            return []
        
        # Supported image formats
        supported_formats = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}
        converted_images = []
        
        # Find all image files
        for image_file in source_path.rglob('*'):
            if image_file.suffix.lower() in supported_formats:
                try:
                    # Calculate relative path and target WebP path
                    rel_path = image_file.relative_to(source_path)
                    webp_path = target_path / rel_path.with_suffix('.webp')
                    
                    # Create target directory if it doesn't exist
                    webp_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Convert to WebP
                    with Image.open(image_file) as img:
                        # Convert to RGB if necessary (for PNG with transparency)
                        if img.mode in ('RGBA', 'LA', 'P'):
                            # Create white background for transparent images
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            if img.mode == 'P':
                                img = img.convert('RGBA')
                            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                            img = background
                        elif img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        # Save as WebP
                        img.save(webp_path, 'WebP', quality=quality, optimize=True)
                        
                        # Also copy original file
                        original_target = target_path / rel_path
                        original_target.parent.mkdir(parents=True, exist_ok=True)
                        if not original_target.exists():
                            import shutil
                            shutil.copy2(image_file, original_target)
                        
                        converted_images.append({
                            'original': str(rel_path),
                            'webp': str(rel_path.with_suffix('.webp')),
                            'original_size': image_file.stat().st_size,
                            'webp_size': webp_path.stat().st_size
                        })
                        
                except Exception as e:
                    print(f"[WARNING] Failed to convert {image_file}: {e}")
                    
        return converted_images
        
    except ImportError:
        print("[ERROR] Pillow library not found. Install with: pip install Pillow")
        return []

def should_optimize_images(site_config, force_optimize=False):
    """Determine if images should be optimized based on config and flags"""
    if force_optimize:
        return True, site_config.get('image_optimization', {}).get('quality', 100)
    
    optimization_config = site_config.get('image_optimization', {})
    enabled = optimization_config.get('enabled', False)
    quality = optimization_config.get('quality', 100)
    
    return enabled, quality

def optimize_all_images(site_config, force_optimize=False):
    """Optimize all images in the static directory"""
    should_optimize, quality = should_optimize_images(site_config, force_optimize)
    
    if not should_optimize:
        return
    
    print(f"Optimizing images to WebP (quality: {quality}%)...")
    
    # Optimize static images
    static_source = Path("static/images")
    static_target = Path(BUILD_DIR) / "static/images"
    
    if static_source.exists():
        converted = optimize_images_to_webp(static_source, static_target, quality)
        if converted:
            total_original = sum(img['original_size'] for img in converted)
            total_webp = sum(img['webp_size'] for img in converted)
            savings = ((total_original - total_webp) / total_original * 100) if total_original > 0 else 0
            
            print(f"  Converted {len(converted)} images to WebP")
            print(f"  Original size: {total_original / 1024:.1f} KB")
            print(f"  WebP size: {total_webp / 1024:.1f} KB")
            print(f"  Space saved: {savings:.1f}%")
        else:
            print("  No images found to convert")

def generate_stats_report():
    """Generate detailed statistics report and save to stats_report.md"""
    print("\n" + "="*50)
    print("GENERATING STATISTICS REPORT")
    print("="*50)
    
    stats = collect_site_statistics()
    
    report_path = os.path.join(os.path.dirname(BUILD_DIR), "stats_report.md")
    with open(report_path, 'w', encoding='utf-8') as report_file:
        write_stats_report(report_file, stats)
    
    print(f"\n[INFO] Statistics report written to: {report_path}")
    print_stats_summary(stats)

def collect_template_override_stats():
    """Collect statistics about template overrides across all novels"""
    template_stats = {
        'novels_with_overrides': 0,
        'total_custom_templates': 0,
        'override_details': []
    }
    
    all_novels_data = load_all_novels_data()
    for novel in all_novels_data:
        novel_slug = novel['slug']
        
        if check_novel_has_custom_templates(novel_slug):
            template_stats['novels_with_overrides'] += 1
            custom_templates = list_novel_custom_templates(novel_slug)
            template_stats['total_custom_templates'] += len(custom_templates)
            
            template_stats['override_details'].append({
                'novel_slug': novel_slug,
                'novel_title': novel.get('title', novel_slug),
                'custom_templates': custom_templates,
                'template_count': len(custom_templates)
            })
    
    return template_stats

def collect_site_statistics():
    """Collect comprehensive statistics about the generated site"""
    stats = {
        'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'novels': [],
        'total_chapters': 0,
        'total_words': 0,
        'total_characters': 0,
        'languages': set(),
        'tags': {},
        'images': 0,
        'build_files': 0
    }
    
    # Load site config
    site_config = load_site_config()
    
    # Collect novel statistics
    content_dir = Path(CONTENT_DIR)
    if content_dir.exists():
        novel_dirs = [d for d in content_dir.iterdir() if d.is_dir()]
        
        for novel_dir in novel_dirs:
            novel_slug = novel_dir.name
            try:
                novel_config = load_novel_config(novel_slug)
                novel_stats = collect_novel_statistics(novel_slug, novel_config)
                stats['novels'].append(novel_stats)
                
                # Aggregate totals
                stats['total_chapters'] += novel_stats['total_chapters']
                stats['total_words'] += novel_stats['total_words']
                stats['total_characters'] += novel_stats['total_characters']
                stats['languages'].update(novel_stats['languages'])
                
                # Aggregate tags
                for tag, count in novel_stats['tags'].items():
                    stats['tags'][tag] = stats['tags'].get(tag, 0) + count
                    
                stats['images'] += novel_stats['images']
                
            except Exception as e:
                print(f"[WARNING] Error collecting stats for {novel_slug}: {e}")
    
    # Count build files
    build_dir = Path(BUILD_DIR)
    if build_dir.exists():
        stats['build_files'] = len(list(build_dir.rglob("*.*")))
    
    stats['languages'] = sorted(list(stats['languages']))
    
    # Add template override statistics
    stats['template_overrides'] = collect_template_override_stats()
    
    return stats

def collect_novel_statistics(novel_slug, novel_config):
    """Collect statistics for a single novel"""
    novel_stats = {
        'slug': novel_slug,
        'title': novel_config.get('title', novel_slug),
        'status': novel_config.get('status', 'unknown'),
        'total_chapters': 0,
        'total_words': 0,
        'total_characters': 0,
        'languages': set(),
        'arcs': [],
        'tags': {},
        'images': 0,
        'translation_progress': {}
    }
    
    # Get available languages
    available_languages = novel_config.get('languages', {}).get('available', ['en'])
    novel_stats['languages'].update(available_languages)
    
    # Process each arc
    for arc in novel_config.get('arcs', []):
        arc_stats = {
            'title': arc.get('title', 'Unnamed Arc'),
            'chapters': len(arc.get('chapters', [])),
            'words': 0,
            'characters': 0
        }
        
        # Process each chapter
        for chapter in arc.get('chapters', []):
            chapter_id = chapter.get('id')
            if chapter_id:
                novel_stats['total_chapters'] += 1
                
                # Get stats for primary language (usually English)
                primary_lang = novel_config.get('primary_language', 'en')
                content_md, metadata = load_chapter_content(novel_slug, chapter_id, primary_lang)
                
                if content_md:
                    word_count = len(content_md.split())
                    char_count = len(content_md)
                    
                    arc_stats['words'] += word_count
                    arc_stats['characters'] += char_count
                    novel_stats['total_words'] += word_count
                    novel_stats['total_characters'] += char_count
                    
                    # Count tags
                    chapter_tags = metadata.get('tags', [])
                    for tag in chapter_tags:
                        novel_stats['tags'][tag] = novel_stats['tags'].get(tag, 0) + 1
                    
                    # Count images in chapter
                    image_count = len(re.findall(r'!\[.*?\]\(.*?\)', content_md))
                    novel_stats['images'] += image_count
                
                # Check translation progress
                for lang in available_languages:
                    if lang != primary_lang:
                        if chapter_translation_exists(novel_slug, chapter_id, lang):
                            if lang not in novel_stats['translation_progress']:
                                novel_stats['translation_progress'][lang] = 0
                            novel_stats['translation_progress'][lang] += 1
        
        novel_stats['arcs'].append(arc_stats)
    
    return novel_stats

def write_stats_report(report_file, stats):
    """Write the statistics report to a markdown file"""
    report_file.write("# Site Statistics Report\n\n")
    report_file.write(f"**Generated:** {stats['generated_at']}\n\n")
    
    # Overview section
    report_file.write("## Overview\n\n")
    report_file.write("| Metric | Value |\n")
    report_file.write("|--------|-------|\n")
    report_file.write(f"| Total Novels | {len(stats['novels'])} |\n")
    report_file.write(f"| Total Chapters | {stats['total_chapters']:,} |\n")
    report_file.write(f"| Total Words | {stats['total_words']:,} |\n")
    report_file.write(f"| Total Characters | {stats['total_characters']:,} |\n")
    report_file.write(f"| Available Languages | {len(stats['languages'])} ({', '.join(stats['languages'])}) |\n")
    report_file.write(f"| Unique Tags | {len(stats['tags'])} |\n")
    report_file.write(f"| Images | {stats['images']} |\n")
    report_file.write(f"| Build Files | {stats['build_files']:,} |\n\n")
    
    # Novels section
    if stats['novels']:
        report_file.write("## Novels\n\n")
        for novel in stats['novels']:
            report_file.write(f"### {novel['title']} (`{novel['slug']}`)\n\n")
            report_file.write("| Metric | Value |\n")
            report_file.write("|--------|-------|\n")
            report_file.write(f"| Status | {novel['status'].title()} |\n")
            report_file.write(f"| Chapters | {novel['total_chapters']} |\n")
            report_file.write(f"| Words | {novel['total_words']:,} |\n")
            report_file.write(f"| Characters | {novel['total_characters']:,} |\n")
            report_file.write(f"| Languages | {', '.join(sorted(novel['languages']))} |\n")
            report_file.write(f"| Images | {novel['images']} |\n")
            
            # Translation progress
            if novel['translation_progress']:
                report_file.write("\n**Translation Progress:**\n")
                total_chapters = novel['total_chapters']
                for lang, translated_count in novel['translation_progress'].items():
                    percentage = (translated_count / total_chapters * 100) if total_chapters > 0 else 0
                    report_file.write(f"- {lang.upper()}: {translated_count}/{total_chapters} chapters ({percentage:.1f}%)\n")
            
            # Arc breakdown
            if novel['arcs']:
                report_file.write("\n**Arc Breakdown:**\n")
                report_file.write("| Arc | Chapters | Words | Characters |\n")
                report_file.write("|-----|----------|-------|------------|\n")
                for arc in novel['arcs']:
                    report_file.write(f"| {arc['title']} | {arc['chapters']} | {arc['words']:,} | {arc['characters']:,} |\n")
            
            report_file.write("\n")
    
    # Tags section
    if stats['tags']:
        report_file.write("## Popular Tags\n\n")
        sorted_tags = sorted(stats['tags'].items(), key=lambda x: x[1], reverse=True)
        report_file.write("| Tag | Usage Count |\n")
        report_file.write("|-----|-------------|\n")
        for tag, count in sorted_tags[:20]:  # Top 20 tags
            report_file.write(f"| {tag} | {count} |\n")
        report_file.write("\n")
    
    # Template Overrides section
    template_stats = stats.get('template_overrides', {})
    if template_stats.get('novels_with_overrides', 0) > 0:
        report_file.write("## Template Overrides\n\n")
        report_file.write("| Metric | Value |\n")
        report_file.write("|--------|-------|\n")
        report_file.write(f"| Novels with Custom Templates | {template_stats['novels_with_overrides']} |\n")
        report_file.write(f"| Total Custom Templates | {template_stats['total_custom_templates']} |\n\n")
        
        report_file.write("### Novels with Custom Templates\n\n")
        for detail in template_stats['override_details']:
            report_file.write(f"**{detail['novel_title']}** (`{detail['novel_slug']}`)\n")
            report_file.write(f"- Custom templates: {detail['template_count']}\n")
            report_file.write(f"- Templates: {', '.join(detail['custom_templates'])}\n\n")
    else:
        report_file.write("## Template Overrides\n\n")
        report_file.write("No novels are using custom template overrides.\n\n")

def print_stats_summary(stats):
    """Print a summary of the statistics to console"""
    print(f"\n[SUMMARY]")
    print(f"   Novels: {len(stats['novels'])}")
    print(f"   Chapters: {stats['total_chapters']:,}")
    print(f"   Words: {stats['total_words']:,}")
    print(f"   Languages: {len(stats['languages'])}")
    print(f"   Build files: {stats['build_files']:,}")
    
    if stats['novels']:
        print(f"\n[NOVELS]")
        for novel in stats['novels']:
            print(f"   {novel['title']}: {novel['total_chapters']} chapters, {novel['total_words']:,} words")

def determine_rebuild_scope(changed_file_path):
    """Determine what needs to be rebuilt based on the changed file"""
    changed_file_path = os.path.normpath(changed_file_path).replace('\\', '/')
    
    # Site config changes require full rebuild
    if changed_file_path.endswith('site_config.yaml') or changed_file_path.endswith('site_config.yml'):
        return {'type': 'full', 'reason': 'Site config changed'}
    
    # Template changes require full rebuild
    if 'templates/' in changed_file_path and changed_file_path.endswith('.html'):
        return {'type': 'full', 'reason': 'Global template changed'}
    
    # Novel-specific template changes
    if 'content/' in changed_file_path and 'templates/' in changed_file_path and changed_file_path.endswith('.html'):
        # Extract novel slug from path (e.g., content/novel-slug/templates/chapter.html)
        parts = changed_file_path.split('/')
        if len(parts) >= 4 and parts[0] == 'content' and parts[2] == 'templates':
            novel_slug = parts[1]
            template_name = parts[3]
            return {'type': 'novel_template', 'novel': novel_slug, 'template': template_name, 'reason': f'Novel template {template_name} changed'}
    
    # Static file changes (CSS, JS, images)
    if 'static/' in changed_file_path:
        return {'type': 'static', 'file': changed_file_path, 'reason': 'Static asset changed'}
    
    # Novel config changes
    if 'content/' in changed_file_path and changed_file_path.endswith('config.yaml'):
        # Extract novel slug from path
        parts = changed_file_path.split('/')
        if len(parts) >= 2 and parts[0] == 'content':
            novel_slug = parts[1]
            return {'type': 'novel_config', 'novel': novel_slug, 'reason': 'Novel config changed'}
    
    # Chapter markdown changes
    if 'content/' in changed_file_path and changed_file_path.endswith('.md'):
        # Extract novel slug and chapter info
        parts = changed_file_path.split('/')
        if len(parts) >= 4 and parts[0] == 'content' and parts[2] == 'chapters':
            novel_slug = parts[1]
            
            # Check if it's a translation (e.g., content/novel/chapters/jp/chapter-1.md)
            if len(parts) == 5:
                language = parts[3]
                chapter_file = parts[4]
            else:
                language = 'en'
                chapter_file = parts[3]
            
            chapter_id = chapter_file[:-3] if chapter_file.endswith('.md') else chapter_file
            return {
                'type': 'chapter', 
                'novel': novel_slug, 
                'chapter': chapter_id, 
                'language': language,
                'reason': f'Chapter {chapter_id} changed'
            }
    
    # Static page changes
    if 'pages/' in changed_file_path and changed_file_path.endswith('.md'):
        # Extract page info
        parts = changed_file_path.split('/')
        if len(parts) >= 2 and parts[0] == 'pages':
            
            # Check if it's a translation (e.g., pages/jp/about.md)
            if len(parts) == 3 and len(parts[1]) == 2:  # Language code
                language = parts[1]
                page_file = parts[2]
            else:
                language = 'en'
                page_file = parts[1] if len(parts) == 2 else '/'.join(parts[1:])
            
            page_slug = page_file[:-3] if page_file.endswith('.md') else page_file
            return {
                'type': 'page',
                'page': page_slug,
                'language': language,
                'reason': f'Static page {page_slug} changed'
            }
    
    # Default to full rebuild for unknown changes
    return {'type': 'full', 'reason': 'Unknown file type changed'}

def incremental_rebuild_static(file_path):
    """Copy a single static file to build directory"""
    try:
        # Normalize the path
        rel_path = os.path.relpath(file_path, STATIC_DIR)
        target_path = os.path.normpath(os.path.join(BUILD_DIR, "static", rel_path))
        
        # Ensure target directory exists
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        # Copy the file
        import shutil
        shutil.copy2(file_path, target_path)
        print(f"    Updated static file: {rel_path}")
        return True
    except Exception as e:
        print(f"    Error updating static file {file_path}: {e}")
        return False

def incremental_rebuild_page(page_slug, language='en'):
    """Rebuild a single static page"""
    try:
        site_config = load_site_config()
        
        # Load page content
        if '/' in page_slug:
            page_content, page_metadata = load_nested_page_content(page_slug, language)
        else:
            page_content, page_metadata = load_page_content(page_slug, language)
        
        if not page_content:
            print(f"    Could not load page content for {page_slug}")
            return False
        
        # Skip if page should be skipped
        if should_skip_page(page_metadata, INCLUDE_DRAFTS):
            print(f"    Skipping draft/hidden page: {page_slug} ({language})")
            return True
        
        # Create page directory
        page_dir = os.path.normpath(os.path.join(BUILD_DIR, page_slug, language))
        os.makedirs(page_dir, exist_ok=True)
        
        # Calculate breadcrumb depth
        breadcrumb_depth = page_slug.count('/') + 2
        
        # Build breadcrumbs
        breadcrumbs = [{'title': 'Home', 'url': '../' * breadcrumb_depth}]
        if '/' in page_slug:
            parts = page_slug.split('/')
            url_parts = []
            for i, part in enumerate(parts[:-1]):
                url_parts.append(part)
                parent_url = '../' * breadcrumb_depth + '/'.join(url_parts) + f'/{language}/'
                breadcrumbs.append({
                    'title': part.replace('-', ' ').title(),
                    'url': parent_url
                })
        
        breadcrumbs.append({'title': page_metadata.get('title', page_slug.split('/')[-1].replace('-', ' ').title()), 'url': ''})
        
        # Get available languages for this page
        available_languages = get_available_page_languages(page_slug)
        
        # Render page
        page_html = render_template("page.html",
                                   title=page_metadata.get('title', page_slug.replace('-', ' ').title()),
                                   content=convert_markdown_to_html(page_content),
                                   metadata=page_metadata,
                                   current_language=language,
                                   available_languages=available_languages,
                                   page_slug=page_slug,
                                   breadcrumbs=breadcrumbs,
                                   site_config=site_config)
        
        # Write page file
        with open(os.path.join(page_dir, "index.html"), "w", encoding='utf-8') as f:
            f.write(page_html)
        
        print(f"    Rebuilt page: {page_slug} ({language})")
        return True
        
    except Exception as e:
        print(f"    Error rebuilding page {page_slug}: {e}")
        return False

def incremental_rebuild_chapter(novel_slug, chapter_id, language='en'):
    """Rebuild a single chapter and update related pages"""
    try:
        site_config = load_site_config()
        
        # Load novel config
        novel_config = load_novel_config(novel_slug)
        if not novel_config:
            print(f"    Could not load novel config for {novel_slug}")
            return False
        
        # Find the chapter in the novel structure
        chapter_info = None
        arc_info = None
        
        for arc in novel_config.get('arcs', []):
            for chapter in arc.get('chapters', []):
                if chapter['id'] == chapter_id:
                    chapter_info = chapter
                    arc_info = arc
                    break
            if chapter_info:
                break
        
        if not chapter_info:
            print(f"    Chapter {chapter_id} not found in novel config")
            return False
        
        # Load chapter content
        chapter_content, chapter_metadata = load_chapter_content(novel_slug, chapter_id, language)
        if not chapter_content:
            print(f"    Could not load chapter content for {chapter_id}")
            return False
        
        # Skip if chapter should be skipped
        if should_skip_chapter(chapter_metadata, INCLUDE_DRAFTS, INCLUDE_SCHEDULED):
            print(f"    Skipping draft/hidden chapter: {chapter_id}")
            return True
        
        # Create chapter directory
        novel_dir = os.path.normpath(os.path.join(BUILD_DIR, novel_slug))
        lang_dir = os.path.normpath(os.path.join(novel_dir, language))
        chapter_dir = os.path.normpath(os.path.join(lang_dir, chapter_id))
        os.makedirs(chapter_dir, exist_ok=True)
        
        # Process images for this chapter
        updated_content = process_chapter_images(novel_slug, chapter_id, language, chapter_content)
        
        # Build navigation
        languages_config = novel_config.get('languages', {'available': ['en']})
        if isinstance(languages_config, dict):
            available_languages = languages_config.get('available', ['en'])
        else:
            available_languages = languages_config if isinstance(languages_config, list) else ['en']
        
        if 'en' not in available_languages:
            available_languages.append('en')
        
        # Get chapter index for navigation
        all_chapters = []
        for arc in novel_config.get('arcs', []):
            for chapter in arc.get('chapters', []):
                chapter_content_check, chapter_metadata_check = load_chapter_content(novel_slug, chapter['id'], language)
                if chapter_content_check and not should_skip_chapter(chapter_metadata_check, INCLUDE_DRAFTS, INCLUDE_SCHEDULED):
                    all_chapters.append(chapter)
        
        current_index = next((i for i, ch in enumerate(all_chapters) if ch['id'] == chapter_id), -1)
        prev_chapter = all_chapters[current_index - 1] if current_index > 0 else None
        next_chapter = all_chapters[current_index + 1] if current_index < len(all_chapters) - 1 else None
        
        # Build comments config
        comments_config = build_comments_config(site_config)
        
        # Load authors config for template
        authors_config = load_authors_config()
        
        # Create novel structure for template (filtered to remove hidden chapters)
        novel_for_template = {
            'title': novel_config.get('title', novel_slug),
            'slug': novel_slug,
            'arcs': []
        }
        
        # Add only visible arcs and chapters
        for arc in novel_config.get('arcs', []):
            visible_chapters = []
            for chapter in arc.get('chapters', []):
                chapter_content_check, chapter_metadata_check = load_chapter_content(novel_slug, chapter['id'], language)
                if (chapter_content_check and 
                    not should_skip_chapter(chapter_metadata_check, INCLUDE_DRAFTS, INCLUDE_SCHEDULED) and 
                    not chapter_metadata_check.get('hidden', False)):
                    visible_chapters.append(chapter)
            
            if visible_chapters:  # Only include arc if it has visible chapters
                arc_for_template = {
                    'title': arc.get('title', ''),
                    'chapters': visible_chapters
                }
                novel_for_template['arcs'].append(arc_for_template)
        
        # Build social meta and other template variables
        chapter_social_meta = build_social_meta(site_config, novel_config, chapter_metadata, 'chapter', 
                                               chapter_metadata.get('title', chapter_info['title']), 
                                               f"{site_config.get('site_url', '').rstrip('/')}/{novel_slug}/{language}/{chapter_id}/")
        chapter_seo_meta = build_seo_meta(site_config, novel_config, chapter_metadata, 'chapter')
        footer_data = build_footer_content(site_config, novel_config, 'chapter')
        
        # Determine what to show
        show_tags = bool(chapter_metadata.get('tags'))
        show_metadata = bool(chapter_metadata.get('author') or chapter_metadata.get('translator') or chapter_metadata.get('published'))
        show_translation_notes = bool(chapter_metadata.get('translation_notes') or chapter_metadata.get('translator_commentary'))
        
        # Handle password protection
        is_password_protected = bool(chapter_metadata.get('password'))
        encrypted_content = None
        password_hash = None
        if is_password_protected:
            from hashlib import sha256
            password = chapter_metadata['password']
            password_hash = sha256(password.encode()).hexdigest()
            # Simple XOR encryption for demo (not secure)
            encrypted_content = ''.join(chr(ord(c) ^ 42) for c in updated_content)
        
        # Check comments
        comments_enabled = should_enable_comments(site_config, novel_config, chapter_metadata, 'chapter')
        
        # Render chapter  
        chapter_html = render_template("chapter.html",
                                     novel_slug=novel_slug,
                                     novel=novel_for_template,
                                     chapter=chapter_info,
                                     chapter_title=chapter_metadata.get('title', chapter_info['title']),
                                     chapter_content=convert_markdown_to_html(updated_content),
                                     chapter_metadata=chapter_metadata,
                                     prev_chapter=prev_chapter,
                                     next_chapter=next_chapter,
                                     current_language=language,
                                     available_languages=available_languages,
                                     show_tags=show_tags,
                                     show_metadata=show_metadata,
                                     show_translation_notes=show_translation_notes,
                                     is_password_protected=is_password_protected,
                                     encrypted_content=encrypted_content,
                                     password_hash=password_hash,
                                     password_hint=chapter_metadata.get('password_hint', ''),
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
                                     comments_theme=comments_config['theme'],
                                     authors_config=authors_config)
        
        # Write chapter file
        with open(os.path.join(chapter_dir, "index.html"), "w", encoding='utf-8') as f:
            f.write(chapter_html)
        
        print(f"    Rebuilt chapter: {novel_slug}/{chapter_id} ({language})")
        
        # Check if we need to update tag pages (if chapter tags changed)
        if chapter_metadata.get('tags'):
            print(f"    Chapter has tags, may need to rebuild tag pages")
            # For now, we'll leave tag rebuilding as a future enhancement
        
        return True
        
    except Exception as e:
        print(f"    Error rebuilding chapter {novel_slug}/{chapter_id}: {e}")
        return False

def perform_incremental_rebuild(rebuild_info, include_drafts=False, include_scheduled=False):
    """Perform incremental rebuild based on the rebuild scope"""
    global INCLUDE_DRAFTS, INCLUDE_SCHEDULED
    INCLUDE_DRAFTS = include_drafts
    INCLUDE_SCHEDULED = include_scheduled
    
    rebuild_type = rebuild_info['type']
    
    if rebuild_type == 'full':
        print(f"Full rebuild needed: {rebuild_info['reason']}")
        # Ensure build directory exists
        os.makedirs(BUILD_DIR, exist_ok=True)
        # Perform full rebuild
        build_site(include_drafts=include_drafts, include_scheduled=include_scheduled, no_epub=True, optimize_images=False)
        return True
        
    elif rebuild_type == 'static':
        print(f"Incremental rebuild: {rebuild_info['reason']}")
        return incremental_rebuild_static(rebuild_info['file'])
        
    elif rebuild_type == 'page':
        print(f"Incremental rebuild: {rebuild_info['reason']}")
        return incremental_rebuild_page(rebuild_info['page'], rebuild_info['language'])
        
    elif rebuild_type == 'chapter':
        print(f"Incremental rebuild: {rebuild_info['reason']}")
        return incremental_rebuild_chapter(rebuild_info['novel'], rebuild_info['chapter'], rebuild_info['language'])
        
    elif rebuild_type == 'novel_config':
        print(f"Novel rebuild needed: {rebuild_info['reason']}")
        # For novel config changes, we need to rebuild the entire novel
        # This is complex, so for now fall back to full rebuild
        os.makedirs(BUILD_DIR, exist_ok=True)
        build_site(include_drafts=include_drafts, include_scheduled=include_scheduled, no_epub=True, optimize_images=False)
        return True
        
    elif rebuild_type == 'novel_template':
        print(f"Novel template rebuild needed: {rebuild_info['reason']}")
        # Clear the template cache for this novel to force reload
        novel_slug = rebuild_info['novel']
        if novel_slug in _novel_template_envs:
            del _novel_template_envs[novel_slug]
        
        # For template changes, we need to rebuild the entire novel since 
        # we don't know which pages use this template
        os.makedirs(BUILD_DIR, exist_ok=True)
        build_site(include_drafts=include_drafts, include_scheduled=include_scheduled, no_epub=True, optimize_images=False)
        return True
        
    else:
        print(f"Unknown rebuild type: {rebuild_type}")
        return False

def start_development_server(port=8000, include_drafts=False, include_scheduled=False):
    """Start development server with live reload"""
    try:
        import asyncio
        import websockets
        import threading
        import time
        import signal
        import sys
        from http.server import HTTPServer, SimpleHTTPRequestHandler
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        import os
        from pathlib import Path
        
        print(f"Starting development server with live reload...")
        
        # WebSocket clients for live reload
        connected_clients = set()
        websocket_loop = None
        
        # File change handler
        class ChangeHandler(FileSystemEventHandler):
            def __init__(self):
                self.last_rebuild = 0
                self.rebuild_delay = 1  # Wait 1 second between rebuilds
                self.include_drafts = include_drafts
                self.include_scheduled = include_scheduled
            
            def on_modified(self, event):
                if event.is_directory:
                    return
                
                # Only rebuild for relevant file changes
                if self.should_rebuild(event.src_path):
                    current_time = time.time()
                    if current_time - self.last_rebuild > self.rebuild_delay:
                        self.last_rebuild = current_time
                        self.rebuild_site(event.src_path)
            
            def should_rebuild(self, file_path):
                """Check if file change should trigger rebuild"""
                file_path = str(file_path).lower()
                rebuild_extensions = {'.md', '.yaml', '.yml', '.css', '.js', '.html', '.jpg', '.jpeg', '.png', '.webp'}
                rebuild_dirs = {'content', 'templates', 'static', 'pages'}
                
                # Check file extension
                for ext in rebuild_extensions:
                    if file_path.endswith(ext):
                        break
                else:
                    return False
                
                # Check if in relevant directory
                for dir_name in rebuild_dirs:
                    if f'{os.sep}{dir_name}{os.sep}' in file_path or file_path.startswith(dir_name):
                        return True
                
                return False
            
            def rebuild_site(self, changed_file_path):
                """Rebuild site and notify clients using incremental rebuilds"""
                try:
                    print("File change detected, analyzing...")
                    
                    # Determine what needs to be rebuilt
                    rebuild_info = determine_rebuild_scope(changed_file_path)
                    
                    # Perform incremental rebuild
                    success = perform_incremental_rebuild(rebuild_info, include_drafts=self.include_drafts, include_scheduled=self.include_scheduled)
                    
                    if success:
                        print("Rebuild completed, waiting for filesystem sync...")
                        
                        # Trigger browser reload after a delay to ensure files are fully written
                        if connected_clients:
                            # Run broadcast in a thread-safe way with delay
                            def trigger_reload():
                                try:
                                    import time
                                    time.sleep(1.5)  # Wait for filesystem operations to complete
                                    loop = websocket_loop
                                    asyncio.run_coroutine_threadsafe(broadcast_reload(), loop)
                                    print("Browser refresh triggered")
                                except:
                                    pass
                            threading.Thread(target=trigger_reload, daemon=True).start()
                        else:
                            print("Rebuild complete")
                    else:
                        print("Rebuild failed, falling back to full rebuild...")
                        # Fallback to full rebuild if incremental failed
                        os.makedirs(BUILD_DIR, exist_ok=True)
                        build_site(include_drafts=self.include_drafts, include_scheduled=self.include_scheduled, no_epub=True, optimize_images=False)
                        
                except Exception as e:
                    print(f"Error rebuilding site: {e}")
                    # Create a minimal error page if rebuild fails
                    try:
                        error_html = f"""
<!DOCTYPE html>
<html>
<head><title>Build Error</title></head>
<body>
    <h1>Build Error</h1>
    <p>Error rebuilding site: {e}</p>
    <p>Check console for details.</p>
</body>
</html>"""
                        os.makedirs(BUILD_DIR, exist_ok=True)
                        with open(os.path.join(BUILD_DIR, 'index.html'), 'w') as f:
                            f.write(error_html)
                    except:
                        pass
        
        async def broadcast_reload():
            """Broadcast reload message to all connected clients"""
            if connected_clients:
                await asyncio.gather(
                    *[client.send("reload") for client in connected_clients.copy()],
                    return_exceptions=True
                )
        
        # WebSocket server for live reload
        async def websocket_handler(websocket, path):
            """Handle WebSocket connections for live reload"""
            connected_clients.add(websocket)
            print(f"Client connected for live reload (total: {len(connected_clients)})")
            try:
                await websocket.wait_closed()
            except:
                pass
            finally:
                connected_clients.discard(websocket)
                print(f"Client disconnected (total: {len(connected_clients)})")
        
        # Custom HTTP handler that injects live reload script
        class LiveReloadHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=BUILD_DIR, **kwargs)
            
            def end_headers(self):
                if self.path.endswith('.html') or self.path.endswith('/'):
                    # Inject live reload script
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                super().end_headers()
            
            def do_GET(self):
                if self.path.endswith('.html') or self.path.endswith('/'):
                    # Serve HTML with live reload script injected
                    try:
                        # Get the file path
                        if self.path.endswith('/'):
                            file_path = Path(BUILD_DIR) / self.path.lstrip('/') / 'index.html'
                        else:
                            file_path = Path(BUILD_DIR) / self.path.lstrip('/')
                        
                        if file_path.exists():
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            
                            # Inject live reload script before closing </body> tag
                            live_reload_script = f"""
<script>
(function() {{
    const ws = new WebSocket('ws://localhost:{port + 1}');
    ws.onmessage = function(event) {{
        if (event.data === 'reload') {{
            window.location.reload();
        }}
    }};
    ws.onclose = function() {{
        console.log('Live reload disconnected');
    }};
    ws.onerror = function() {{
        console.log('Live reload connection error');
    }};
}})();
</script>"""
                            
                            content = content.replace('</body>', f'{live_reload_script}</body>')
                            
                            self.send_response(200)
                            self.send_header('Content-Type', 'text/html; charset=utf-8')
                            self.send_header('Content-Length', len(content.encode('utf-8')))
                            self.end_headers()
                            self.wfile.write(content.encode('utf-8'))
                            return
                    except Exception:
                        pass  # Fall back to default handler
                
                # For non-HTML files or if injection fails, use default handler
                super().do_GET()
            
            def log_message(self, format, *args):
                # Suppress HTTP server logs for cleaner output
                pass
        
        # Start file watcher
        event_handler = ChangeHandler()
        observer = Observer()
        
        # Watch content, templates, static, and pages directories
        watch_dirs = ['content', 'templates', 'static', 'pages']
        for watch_dir in watch_dirs:
            if os.path.exists(watch_dir):
                observer.schedule(event_handler, watch_dir, recursive=True)
                print(f"Watching {watch_dir}/ for changes...")
        
        observer.start()
        
        # Start WebSocket server
        async def start_websocket_server():
            await websockets.serve(websocket_handler, "localhost", port + 1)
            print(f"WebSocket server started on ws://localhost:{port + 1}")
        
        # Start WebSocket server in background
        def run_websocket_server():
            nonlocal websocket_loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            websocket_loop = loop
            loop.run_until_complete(start_websocket_server())
            loop.run_forever()
        
        websocket_thread = threading.Thread(target=run_websocket_server, daemon=True)
        websocket_thread.start()
        
        # Store thread reference for cleanup
        cleanup_threads = [websocket_thread]
        
        # Start HTTP server
        httpd = HTTPServer(("localhost", port), LiveReloadHandler)
        
        # Global shutdown flag to prevent multiple shutdown attempts
        shutdown_in_progress = False
        
        # Set up proper signal handling for graceful shutdown
        def signal_handler(signum, frame):
            nonlocal shutdown_in_progress
            if shutdown_in_progress:
                print("Force terminating...")
                os._exit(1)
                return
                
            shutdown_in_progress = True
            print("\nShutting down server...")
            
            # Force exit after 1 second regardless
            def force_exit():
                time.sleep(1)
                print("Force exiting...")
                os._exit(1)
            
            timeout_thread = threading.Thread(target=force_exit, daemon=True)
            timeout_thread.start()
            
            try:
                # Stop everything immediately
                observer.stop()
                httpd.shutdown()
                httpd.server_close()
                
                # Don't wait for websocket cleanup
                print("Server shutdown complete.")
                
            except Exception as e:
                print(f"Error during shutdown: {e}")
            finally:
                os._exit(0)
        
        # Register signal handlers for Ctrl+C (and re-register periodically)
        def register_handlers():
            signal.signal(signal.SIGINT, signal_handler)
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, signal_handler)
        
        register_handlers()
        
        # Simplified signal re-registration (less aggressive)
        def reregister_signals():
            while not shutdown_in_progress:
                time.sleep(10)  # Re-register every 10 seconds
                try:
                    register_handlers()
                except:
                    pass
        
        signal_thread = threading.Thread(target=reregister_signals, daemon=True)
        signal_thread.start()
        
        print(f"Development server running at http://localhost:{port}/")
        print("Press Ctrl+C to stop the server")
        
        # Run HTTP server in a separate thread to keep main thread free for signals
        def run_server():
            try:
                httpd.serve_forever()
            except Exception as e:
                if not shutdown_in_progress:
                    print(f"Server error: {e}")
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        # Keep main thread alive and responsive to signals
        try:
            while not shutdown_in_progress:
                time.sleep(0.5)  # Check every 500ms
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt caught in main thread")
            signal_handler(signal.SIGINT, None)
        
        # Final cleanup
        print("\nServer stopped.")
        try:
            observer.stop()
            httpd.shutdown()
            httpd.server_close()
        except:
            pass
        os._exit(0)
            
    except ImportError as e:
        print(f"[ERROR] Missing dependencies for development server: {e}")
        print("Install with: pip install watchdog websockets")
    except Exception as e:
        print(f"[ERROR] Failed to start development server: {e}")

def watch_and_rebuild(include_drafts=False, include_scheduled=False):
    """Watch for file changes and rebuild without serving"""
    try:
        import time
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        import os
        
        print("Starting file watcher...")
        
        class ChangeHandler(FileSystemEventHandler):
            def __init__(self):
                self.last_rebuild = 0
                self.rebuild_delay = 1  # Wait 1 second between rebuilds
                self.include_drafts = include_drafts
                self.include_scheduled = include_scheduled
            
            def on_modified(self, event):
                if event.is_directory:
                    return
                
                # Only rebuild for relevant file changes
                if self.should_rebuild(event.src_path):
                    current_time = time.time()
                    if current_time - self.last_rebuild > self.rebuild_delay:
                        self.last_rebuild = current_time
                        self.rebuild_site(event.src_path)
            
            def should_rebuild(self, file_path):
                """Check if file change should trigger rebuild"""
                file_path = str(file_path).lower()
                rebuild_extensions = {'.md', '.yaml', '.yml', '.css', '.js', '.html', '.jpg', '.jpeg', '.png', '.webp'}
                rebuild_dirs = {'content', 'templates', 'static', 'pages'}
                
                # Check file extension
                for ext in rebuild_extensions:
                    if file_path.endswith(ext):
                        break
                else:
                    return False
                
                # Check if in relevant directory
                for dir_name in rebuild_dirs:
                    if f'{os.sep}{dir_name}{os.sep}' in file_path or file_path.startswith(dir_name):
                        return True
                
                return False
            
            def rebuild_site(self, changed_file_path):
                """Rebuild site using incremental rebuilds"""
                try:
                    print("File change detected, analyzing...")
                    
                    # Determine what needs to be rebuilt
                    rebuild_info = determine_rebuild_scope(changed_file_path)
                    
                    # Perform incremental rebuild
                    success = perform_incremental_rebuild(rebuild_info, include_drafts=self.include_drafts, include_scheduled=self.include_scheduled)
                    
                    if success:
                        print("Rebuild complete")
                    else:
                        print("Rebuild failed, falling back to full rebuild...")
                        # Fallback to full rebuild if incremental failed
                        os.makedirs(BUILD_DIR, exist_ok=True)
                        build_site(include_drafts=self.include_drafts, include_scheduled=self.include_scheduled, no_epub=True, optimize_images=False)
                        print("Full rebuild complete")
                        
                except Exception as e:
                    print(f"Error rebuilding site: {e}")
        
        # Start file watcher
        event_handler = ChangeHandler()
        observer = Observer()
        
        # Watch content, templates, static, and pages directories
        watch_dirs = ['content', 'templates', 'static', 'pages']
        for watch_dir in watch_dirs:
            if os.path.exists(watch_dir):
                observer.schedule(event_handler, watch_dir, recursive=True)
                print(f"Watching {watch_dir}/ for changes...")
        
        observer.start()
        
        print("File watcher started. Press Ctrl+C to stop.")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping file watcher...")
            observer.stop()
            observer.join()
            
    except ImportError as e:
        print(f"[ERROR] Missing dependencies for file watching: {e}")
        print("Install with: pip install watchdog")
    except Exception as e:
        print(f"[ERROR] Failed to start file watcher: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Static site generator for web novels')
    parser.add_argument('--include-drafts', action='store_true', 
                        help='Include draft chapters in the generated site')
    parser.add_argument('--include-scheduled', action='store_true',
                        help='Include chapters with future publish dates in the generated site')
    parser.add_argument('--check-links', action='store_true',
                        help='Check for broken internal links after site generation')
    parser.add_argument('--check-accessibility', action='store_true',
                        help='Check for accessibility issues after site generation')
    parser.add_argument('--clean', action='store_true',
                        help='Delete build directory before generating')
    parser.add_argument('--no-epub', action='store_true',
                        help='Skip EPUB generation for faster builds')
    parser.add_argument('--serve', type=int, nargs='?', const=8000, metavar='PORT',
                        help='Start local server with live reload (default: 8000)')
    parser.add_argument('--watch', action='store_true',
                        help='Watch for file changes and rebuild automatically')
    parser.add_argument('--validate', action='store_true',
                        help='Validate all config files and content without building')
    parser.add_argument('--stats', action='store_true',
                        help='Generate statistics report (stats_report.md)')
    parser.add_argument('--optimize-images', action='store_true',
                        help='Convert images to WebP format during build')
    args = parser.parse_args()
    
    # Handle --clean flag
    if args.clean:
        clean_build_directory()
    
    # Handle --validate flag  
    if args.validate:
        validate_all_configs()
        exit(0)
    
    # Handle --watch flag (watch and rebuild without server)
    if args.watch:
        # Build site once first
        build_site(include_drafts=args.include_drafts, 
                   no_epub=True,  # Skip EPUB for faster rebuilds
                   optimize_images=False)  # Skip optimization for speed
        # Start watching for changes
        watch_and_rebuild(include_drafts=args.include_drafts, include_scheduled=args.include_scheduled)
        exit(0)
    
    # Handle --serve flag (build, serve, and watch with live reload)
    if args.serve:
        # Build site once first
        build_site(include_drafts=args.include_drafts, 
                   no_epub=True,  # Skip EPUB for faster rebuilds
                   optimize_images=False)  # Skip optimization for speed
        # Start development server
        start_development_server(args.serve, include_drafts=args.include_drafts, include_scheduled=args.include_scheduled)
        exit(0)
    
    # Normal build mode
    build_site(include_drafts=args.include_drafts,
               include_scheduled=args.include_scheduled,
               no_epub=args.no_epub,
               optimize_images=args.optimize_images)
    
    # Generate statistics report if requested
    if args.stats:
        generate_stats_report()
    
    # Check for broken links if requested
    if args.check_links:
        check_broken_links()
    
    # Check for accessibility issues if requested
    if args.check_accessibility:
        # Load site config for accessibility check
        site_config = load_site_config()
        check_accessibility_issues(site_config)


