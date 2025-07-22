# Web Novel Static Site Generator

A Python-based static website generator specifically designed for web novels, with support for GitHub Actions and GitHub Pages deployment.

## Features

- **Front Page**: Clean landing page with novel title and description
- **Table of Contents**: Organized by story arcs with manual chapter sorting
- **Chapter Pages**: Individual pages for each chapter with navigation
- **Image Support**: Embedded images in chapter content
- **Responsive Design**: Mobile-friendly layout
- **GitHub Integration**: Automated deployment via GitHub Actions

## Project Structure

```
web-novel-generator/
├── .github/
│   └── workflows/
│       └── deploy.yml          # GitHub Actions workflow
├── content/
│   └── novel_title/
│       └── chapters/           # Chapter content files
├── templates/
│   ├── index.html             # Front page template
│   ├── toc.html               # Table of contents template
│   └── chapter.html           # Chapter page template
├── static/
│   ├── style.css              # Main stylesheet
│   └── images/                # Image assets
├── build/                     # Generated site (auto-created)
├── generate.py                # Main generator script
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## Quick Start

### 1. Setup

Clone or download this generator and install dependencies:

```bash
pip install -r requirements.txt
```

### 2. Configure Your Novel

Edit the `load_novel_data()` function in `generate.py` to define your novel structure:

```python
def load_novel_data():
    novel_data = {
        "title": "Your Novel Title",
        "description": "Your novel description",
        "arcs": [
            {
                "title": "Arc 1: Beginning",
                "chapters": [
                    {"id": "chapter-1", "title": "Chapter 1: The Start"},
                    {"id": "prologue", "title": "Prologue"},
                    {"id": "chapter-2", "title": "Chapter 2: The Journey"},
                ]
            },
            # Add more arcs...
        ]
    }
    return novel_data
```

### 3. Add Chapter Content

For each chapter, you can either:

**Option A: Modify the generator to load from files**
Create markdown files in `content/novel_title/chapters/` and modify the generator to read them.

**Option B: Edit the generator directly**
Modify the chapter content generation in the `build_site()` function.

### 4. Add Images

Place images in the `static/images/` directory and reference them in your chapter content:

```markdown
![Description](static/images/your-image.jpg)
```

### 5. Generate the Site

```bash
python generate.py
```

The generated site will be in the `build/` directory.

### 6. Test Locally

```bash
cd build
python -m http.server 8000
```

Visit `http://localhost:8000` to preview your site.

## GitHub Pages Deployment

### Automatic Deployment

1. Push this generator to a GitHub repository
2. The included GitHub Actions workflow will automatically:
   - Build the site when you push changes
   - Deploy to GitHub Pages

### Manual Setup

1. Enable GitHub Pages in your repository settings
2. Set the source to "GitHub Actions"
3. Push changes to trigger deployment

## Customization

### Styling

Edit `static/style.css` to customize the appearance:
- Colors and fonts
- Layout and spacing
- Responsive breakpoints

### Templates

Modify the Jinja2 templates in the `templates/` directory:
- `index.html`: Front page layout
- `toc.html`: Table of contents structure
- `chapter.html`: Chapter page layout

### Chapter Sorting

Chapters are displayed in the order they appear in the `chapters` array within each arc. You can manually sort them by reordering the array:

```python
"chapters": [
    {"id": "prologue", "title": "Prologue"},
    {"id": "chapter-1", "title": "Chapter 1"},
    {"id": "interlude-1", "title": "Interlude 1"},
    {"id": "chapter-2", "title": "Chapter 2"},
    {"id": "epilogue", "title": "Epilogue"},
]
```

## Advanced Features

### Loading Content from Files

To load chapter content from markdown files, modify the `build_site()` function:

```python
def load_chapter_content(chapter_id):
    chapter_file = os.path.join(CONTENT_DIR, "novel_title", "chapters", f"{chapter_id}.md")
    if os.path.exists(chapter_file):
        with open(chapter_file, 'r', encoding='utf-8') as f:
            return f.read()
    return f"# {chapter_id}\n\nContent not found."
```

### YAML Front Matter

You can add YAML front matter to chapter files for metadata:

```markdown
---
title: "Chapter 1: The Beginning"
arc: "Arc 1: The Start"
order: 1
---

# Chapter 1: The Beginning

Your chapter content here...
```

### Multiple Novels

To support multiple novels, create subdirectories in `content/` and modify the generator to process multiple novel configurations.

## Dependencies

- `jinja2`: Template engine
- `markdown`: Markdown to HTML conversion
- `pyyaml`: YAML parsing (if using YAML front matter)

## License

This generator is provided as-is for creating web novel sites. Customize as needed for your project.

## Troubleshooting

### Images Not Displaying
- Ensure images are in the `static/images/` directory
- Check that image paths in content use `static/images/filename.jpg`
- Verify images are copied to the build directory

### GitHub Actions Failing
- Check that `requirements.txt` includes all dependencies
- Ensure the workflow has proper permissions for GitHub Pages
- Verify the repository has GitHub Pages enabled

### Styling Issues
- Clear browser cache after CSS changes
- Check that `static/style.css` is being copied to the build directory
- Verify CSS paths in templates are correct

## Contributing

Feel free to extend this generator with additional features:
- Search functionality
- Reading progress tracking
- Dark/light theme toggle
- Chapter bookmarking
- RSS feeds for updates

