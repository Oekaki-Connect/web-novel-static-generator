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

def load_novel_data():
    # This function will load novel data from a structured source (e.g., YAML/Markdown files)
    # For now, we'll use dummy data.
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
        
        # Dummy content for now
        chapter_content_md = f"# {chapter_title}\n\nThis is the content for {chapter_title}.\n\n![Example Image](static/images/example.jpg)"
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


