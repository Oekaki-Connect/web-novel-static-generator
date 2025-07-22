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

def get_navigation_chapters(novel_slug, all_chapters, current_chapter_id, lang):
    """Get previous and next chapters for navigation, skipping hidden chapters"""
    visible_chapters = []
    
    # Filter out hidden chapters from navigation
    for chapter in all_chapters:
        try:
            _, chapter_metadata = load_chapter_content(novel_slug, chapter['id'], lang)
            if not is_chapter_hidden(chapter_metadata):
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

def filter_hidden_chapters_from_novel(novel, novel_slug, lang):
    """Create a copy of novel data with hidden chapters filtered out for TOC display"""
    filtered_novel = novel.copy()
    filtered_arcs = []
    
    for arc in novel.get('arcs', []):
        filtered_chapters = []
        
        for chapter in arc.get('chapters', []):
            try:
                _, chapter_metadata = load_chapter_content(novel_slug, chapter['id'], lang)
                if not is_chapter_hidden(chapter_metadata):
                    filtered_chapters.append(chapter)
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
            local_images.append({
                'alt': alt_text,
                'original_path': image_path,
                'title': title or '',
                'full_match': f'![{alt_text}]({image_path}{"" if not title else f" \"{title}\""})',
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

def load_novels_data():
    """Load all novels from the content directory"""
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
                                },
                                {
                                    "title": "Arc 3: The Trials",
                                    "chapters": [
                                        {"id": "chapter-5", "title": "Chapter 5: The Test"},
                                        {"id": "chapter-6", "title": "Chapter 6: Allies in Darkness"},
                                    ]
                                },
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

def build_site():
    print("Building site...")
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(BUILD_DIR)

    copy_static_assets()
    
    # Load site configuration
    site_config = load_site_config()

    novels_data = load_novels_data()

    # Generate robots.txt
    robots_txt_content = generate_robots_txt(site_config, novels_data)
    with open(os.path.join(BUILD_DIR, "robots.txt"), "w", encoding='utf-8') as f:
        f.write(robots_txt_content)

    # Generate sitemap.xml
    sitemap_xml_content = generate_sitemap_xml(site_config, novels_data)
    with open(os.path.join(BUILD_DIR, "sitemap.xml"), "w", encoding='utf-8') as f:
        f.write(sitemap_xml_content)

    # Generate site-wide RSS feed
    site_rss_content = generate_rss_feed(site_config, novels_data)
    with open(os.path.join(BUILD_DIR, "rss.xml"), "w", encoding='utf-8') as f:
        f.write(site_rss_content)

    # Build social metadata for front page
    front_page_url = site_config.get('site_url', '').rstrip('/')
    social_meta = build_social_meta(site_config, {}, {}, 'index', site_config.get('site_name', 'Web Novel Collection'), front_page_url)
    seo_meta = build_seo_meta(site_config, {}, {}, 'index')

    # Build footer data for front page
    footer_data = build_footer_content(site_config, page_type='site')

    # Render front page with all novels
    with open(os.path.join(BUILD_DIR, "index.html"), "w", encoding='utf-8') as f:
        f.write(render_template("index.html", 
                               novels=novels_data,
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

    # Process each novel
    for novel in novels_data:
        novel_slug = novel['slug']
        novel_config = load_novel_config(novel_slug)
        available_languages = get_available_languages(novel_slug)
        novel['languages'] = available_languages
        
        # Create novel directory
        novel_dir = os.path.join(BUILD_DIR, novel_slug)
        os.makedirs(novel_dir, exist_ok=True)

        # Generate story-specific RSS feed
        story_rss_content = generate_rss_feed(site_config, novels_data, novel_config, novel_slug)
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
            
            with open(os.path.join(toc_dir, "index.html"), "w", encoding='utf-8') as f:
                f.write(render_template("toc.html", 
                                       novel=filtered_novel, 
                                       current_language=lang, 
                                       available_languages=available_languages,
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
                        f.write(render_template("chapter.html", 
                                                novel=novel,
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
                        f.write(render_template("chapter.html", 
                                                novel=novel,
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

    print("Site built.")

if __name__ == "__main__":
    build_site()


