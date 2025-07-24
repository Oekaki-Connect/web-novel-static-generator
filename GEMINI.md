# Gemini Project Notes: Web Novel Static Generator

This document contains my notes on the web novel static generator project. It's intended to help me understand the project, work on it effectively, and identify potential areas for improvement.

## Project Overview

This project is a static site generator specifically designed for web novels. It takes content written in Markdown, processes it with a Python script, and generates a static HTML website. The generator is highly customizable through YAML configuration files and uses Jinja2 for templating.

### Key Components:

*   **`generate.py`**: The core Python script that drives the static site generation. It reads configuration files, processes content, and renders HTML pages using Jinja2 templates.
*   **`site_config.yaml`**: The main configuration file for the site. It defines site-wide settings such as the title, author, and navigation links.
*   **`authors.yaml`**: A data file containing information about the authors, which is used to generate author pages.
*   **`content/`**: This directory contains the raw content for the web novels, organized into subdirectories for each novel. Each novel has its own `config.yaml` file for novel-specific settings. The example content demonstrates a wide range of features, including:
    *   **Standard Novels:** The `my-awesome-web-novel` example showcases a traditional web novel with features like drafts, hidden chapters, password-protected content, and scheduled publishing.
    *   **Manga:** The `tower-dungeon` example demonstrates how to configure the generator for manga, with settings for reading direction, page view modes, and image handling.
    *   **Localization:** The presence of a `jp` subdirectory in `my-awesome-web-novel` shows the project's support for multiple languages.
    *   **Custom Templates:** Novels can have their own `templates` directory to override the site-wide templates, allowing for unique themes and layouts per novel.
*   **`templates/`**: This directory contains the Jinja2 templates used to render the HTML pages. The templates are well-structured and include features for displaying novels, chapters, author pages, and more.
*   **`static/`**: This directory holds static assets such as CSS stylesheets, JavaScript files, and images.
*   **`pages/`**: This directory contains Markdown files for static pages like "About" or "Privacy Policy."

## My Workflow

Here's how I'll approach common tasks when working on this project:

*   **Git Commits:** I will not commit any changes to the Git repository. The user will be responsible for all `git commit` actions.

*   **Development Environment:** I will be mindful that the primary development OS is Windows. I will use Windows-style paths and commands where appropriate, but I will also ensure that any changes I make to `generate.py` are cross-platform and will work on macOS and Linux as well.

*   **Adding a New Chapter**:
    1.  Create a new Markdown file in the `content/<novel_name>/chapters/` directory.
    2.  Add the chapter content in Markdown format, including any necessary front matter.
    3.  Run `python generate.py` to build the site with the new chapter. For faster development, I can use `python generate.py --no-epub` to skip EPUB generation.

*   **Creating a New Page**:
    1.  Create a new Markdown file in the `pages/` directory.
    2.  Add the page content in Markdown format.
    3.  The generator will automatically pick up the new page and create a corresponding HTML file in the `build/` directory.

*   **Modifying the Site's Appearance**:
    1.  To make style changes, I'll edit the `static/style.css` file.
    2.  For layout or structural changes, I'll modify the Jinja2 templates in the `templates/` directory.
    3.  To create a unique theme for a specific novel, I'll add custom templates to the `content/<novel_name>/templates/` directory.
    4.  After making changes, I'll run `python generate.py` to see the updates. I can use the `python generate.py --serve` command to start a local development server with live reloading for a faster feedback loop.

*   **Workflow Commands:**
    *   `python generate.py --clean`: I will use this command to ensure a fresh build, especially when deleting or renaming files.
    *   `python generate.py --validate`: Before committing changes, I will run this command to check for configuration errors and other issues.
    *   `python generate.py --stats`: I will use this command to generate a report with statistics about the novels, chapters, and translations.
    *   `python generate.py --check-links`: Before deploying, I will run this command to check for broken links.
    *   `python generate.py --check-accessibility`: I will use this command to ensure that the site is accessible.

## Potential Improvements

Based on my analysis, here are some areas where I think the project could be improved:

*   **Code Refactoring**: The `generate.py` script could be refactored to improve its structure and readability. For example, breaking down the main function into smaller, more specialized functions would make the code easier to maintain.
*   **Content Management**: The current system of managing chapters as individual Markdown files is functional, but it could be enhanced. A more structured approach, such as using a headless CMS or a database, could make it easier to manage large numbers of chapters and novels.
*   **Live Reloading**: During development, it would be beneficial to have a live-reloading server that automatically rebuilds the site and refreshes the browser when changes are made. This would speed up the development workflow.
*   **Improved Theming**: While the current theming system is flexible, it could be made more powerful. Adding support for theme inheritance or a more modular CSS architecture (like SCSS or PostCSS) would allow for more advanced customizations.
*   **Plugin System**: A plugin system would allow for extending the generator's functionality without modifying the core codebase. This could be used to add features like search, comments, or analytics.
*   **Asset Pipeline**: The project could benefit from a more robust asset pipeline for managing static assets. This could include features like CSS and JavaScript minification, image optimization, and cache busting.
*   **Testing**: Adding a suite of automated tests would help ensure the stability of the generator as new features are added and existing code is refactored.
