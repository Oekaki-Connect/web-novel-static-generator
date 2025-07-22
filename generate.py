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

def load_chapter_content(chapter_id):
    """Load chapter content from markdown file"""
    chapter_file = os.path.join(CONTENT_DIR, "my-awesome-web-novel", "chapters", f"{chapter_id}.md")
    if os.path.exists(chapter_file):
        with open(chapter_file, 'r', encoding='utf-8') as f:
            return f.read()
    return f"# {chapter_id}\n\nContent not found."

def load_novel_data():
    # Novel data structure with all created chapters
    novel_data = {
        "title": "My Awesome Web Novel",
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
    return novel_data

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

    novel_data = load_novel_data()

    # Render front page
    with open(os.path.join(BUILD_DIR, "index.html"), "w") as f:
        f.write(render_template("index.html", novel=novel_data))

    # Render table of contents page
    with open(os.path.join(BUILD_DIR, "toc.html"), "w") as f:
        f.write(render_template("toc.html", novel=novel_data))

    # Render chapter pages
    all_chapters = []
    for arc in novel_data["arcs"]:
        all_chapters.extend(arc["chapters"])

    for i, chapter in enumerate(all_chapters):
        chapter_id = chapter["id"]
        chapter_title = chapter["title"]
        
        # Load actual content from markdown file
        chapter_content_md = load_chapter_content(chapter_id)
        chapter_content_html = convert_markdown_to_html(chapter_content_md)

        prev_chapter = all_chapters[i-1] if i > 0 else None
        next_chapter = all_chapters[i+1] if i < len(all_chapters) - 1 else None

        with open(os.path.join(BUILD_DIR, f"{chapter_id}.html"), "w") as f:
            f.write(render_template("chapter.html", 
                                    chapter_title=chapter_title,
                                    chapter_content=chapter_content_html,
                                    prev_chapter=prev_chapter,
                                    next_chapter=next_chapter))

    print("Site built.")

if __name__ == "__main__":
    build_site()


