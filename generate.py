import os
import shutil
from jinja2 import Environment, FileSystemLoader
import markdown
import yaml
import re
from pathlib import Path

BUILD_DIR = "./build"
CONTENT_DIR = "./content"
TEMPLATES_DIR = "./templates"
STATIC_DIR = "./static"

env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

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

    # Build social metadata for front page
    front_page_url = site_config.get('site_url', '').rstrip('/')
    social_meta = build_social_meta(site_config, {}, {}, 'index', site_config.get('site_name', 'Web Novel Collection'), front_page_url)
    seo_meta = build_seo_meta(site_config, {}, {}, 'index')

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
                               twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle')))

    # Process each novel
    for novel in novels_data:
        novel_slug = novel['slug']
        novel_config = load_novel_config(novel_slug)
        available_languages = get_available_languages(novel_slug)
        novel['languages'] = available_languages
        
        # Create novel directory
        novel_dir = os.path.join(BUILD_DIR, novel_slug)
        os.makedirs(novel_dir, exist_ok=True)

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
            
            with open(os.path.join(toc_dir, "index.html"), "w", encoding='utf-8') as f:
                f.write(render_template("toc.html", 
                                       novel=novel, 
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
                                       twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle')))

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
                    chapter_content_html = convert_markdown_to_html(chapter_content_md)
                    
                    prev_chapter = all_chapters[i-1] if i > 0 else None
                    next_chapter = all_chapters[i+1] if i < len(all_chapters) - 1 else None

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
                                                site_name=site_config.get('site_name', 'Web Novel Collection'),
                                                social_title=chapter_social_meta['title'],
                                                social_description=chapter_social_meta['description'],
                                                social_image=chapter_social_meta['image'],
                                                social_url=chapter_social_meta['url'],
                                                seo_meta_description=chapter_seo_meta.get('meta_description'),
                                                seo_keywords=chapter_social_meta.get('keywords'),
                                                allow_indexing=chapter_seo_meta.get('allow_indexing', True),
                                                twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle')))
                else:
                    # Generate chapter page showing "not translated" message in primary language
                    chapter_content_md, chapter_metadata = load_chapter_content(novel_slug, chapter_id, primary_lang)
                    # Process chapter images and update markdown (using primary language)
                    chapter_content_md = process_chapter_images(novel_slug, chapter_id, primary_lang, chapter_content_md)
                    chapter_content_html = convert_markdown_to_html(chapter_content_md)
                    
                    prev_chapter = all_chapters[i-1] if i > 0 else None
                    next_chapter = all_chapters[i+1] if i < len(all_chapters) - 1 else None

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
                                                site_name=site_config.get('site_name', 'Web Novel Collection'),
                                                social_title=chapter_social_meta['title'],
                                                social_description=chapter_social_meta['description'],
                                                social_image=chapter_social_meta['image'],
                                                social_url=chapter_social_meta['url'],
                                                seo_meta_description=chapter_seo_meta.get('meta_description'),
                                                seo_keywords=chapter_social_meta.get('keywords'),
                                                allow_indexing=chapter_seo_meta.get('allow_indexing', True),
                                                twitter_handle=site_config.get('social_embeds', {}).get('twitter_handle')))

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


