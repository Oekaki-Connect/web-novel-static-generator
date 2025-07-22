import os
import shutil
from jinja2 import Environment, FileSystemLoader
import markdown
import yaml

BUILD_DIR = "./build"
CONTENT_DIR = "./content"
TEMPLATES_DIR = "./templates"
STATIC_DIR = "./static"

env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

def load_chapter_content(novel_slug, chapter_id, language='en'):
    """Load chapter content from markdown file with language support"""
    # Try language-specific file first
    chapter_file = os.path.join(CONTENT_DIR, novel_slug, "chapters", language, f"{chapter_id}.md")
    if os.path.exists(chapter_file):
        with open(chapter_file, 'r', encoding='utf-8') as f:
            return f.read()
    
    # Fallback to default language file (in root chapters folder)
    chapter_file = os.path.join(CONTENT_DIR, novel_slug, "chapters", f"{chapter_id}.md")
    if os.path.exists(chapter_file):
        with open(chapter_file, 'r', encoding='utf-8') as f:
            return f.read()
    
    return f"# {chapter_id}\n\nContent not found for language: {language}."

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

    novels_data = load_novels_data()

    # Render front page with all novels
    with open(os.path.join(BUILD_DIR, "index.html"), "w", encoding='utf-8') as f:
        f.write(render_template("index.html", novels=novels_data))

    # Process each novel
    for novel in novels_data:
        novel_slug = novel['slug']
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
            with open(os.path.join(lang_dir, "toc.html"), "w", encoding='utf-8') as f:
                f.write(render_template("toc.html", novel=novel, current_language=lang, available_languages=available_languages))

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
                    chapter_content_md = load_chapter_content(novel_slug, chapter_id, lang)
                    chapter_content_html = convert_markdown_to_html(chapter_content_md)
                    
                    prev_chapter = all_chapters[i-1] if i > 0 else None
                    next_chapter = all_chapters[i+1] if i < len(all_chapters) - 1 else None

                    with open(os.path.join(lang_dir, f"{chapter_id}.html"), "w", encoding='utf-8') as f:
                        f.write(render_template("chapter.html", 
                                                novel=novel,
                                                chapter=chapter,
                                                chapter_title=chapter_title,
                                                chapter_content=chapter_content_html,
                                                prev_chapter=prev_chapter,
                                                next_chapter=next_chapter,
                                                current_language=lang,
                                                available_languages=available_languages))
                else:
                    # Generate chapter page showing "not translated" message in primary language
                    chapter_content_md = load_chapter_content(novel_slug, chapter_id, primary_lang)
                    chapter_content_html = convert_markdown_to_html(chapter_content_md)
                    
                    prev_chapter = all_chapters[i-1] if i > 0 else None
                    next_chapter = all_chapters[i+1] if i < len(all_chapters) - 1 else None

                    with open(os.path.join(lang_dir, f"{chapter_id}.html"), "w", encoding='utf-8') as f:
                        f.write(render_template("chapter.html", 
                                                novel=novel,
                                                chapter=chapter,
                                                chapter_title=chapter_title,
                                                chapter_content=chapter_content_html,
                                                prev_chapter=prev_chapter,
                                                next_chapter=next_chapter,
                                                current_language=lang,
                                                primary_language=primary_lang,
                                                requested_language=lang,
                                                translation_missing=True,
                                                available_languages=available_languages))

    print("Site built.")

if __name__ == "__main__":
    build_site()


