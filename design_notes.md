# Web Novel Static Site Generator Design Notes

## 1. Data Structures

To represent the web novel content, I will define the following data structures:

### Novel
- `title`: String, the title of the novel.
- `description`: String, a brief description of the novel (for the front page).
- `arcs`: List of `Arc` objects, representing the different story arcs.

### Arc
- `title`: String, the title of the arc.
- `chapters`: List of `Chapter` objects, representing the chapters within this arc. This list will be ordered manually.

### Chapter
- `id`: String, a unique identifier for the chapter (e.g., 


chapter-XX).
- `title`: String, the title of the chapter.
- `content`: String, the HTML content of the chapter, including embedded images.
- `previous_chapter_id`: String (optional), ID of the previous chapter for navigation.
- `next_chapter_id`: String (optional), ID of the next chapter for navigation.

## 2. Generator Logic

The generator will follow these steps:

1.  **Content Parsing**: Read novel content from a structured source (e.g., Markdown files with YAML front matter for metadata). Each chapter will be a separate file.
2.  **Image Handling**: Images referenced in chapter content will be copied to the build directory.
3.  **HTML Generation**: 
    - **Front Page**: Render a main `index.html` using the `Novel`'s title and description.
    - **Table of Contents Page**: Render a `toc.html` page, iterating through `Arc`s and their `Chapter`s. Manual sorting will be handled by the order in the data structure.
    - **Chapter Pages**: For each `Chapter`, render a dedicated HTML file (`chapter-XX.html`) with its content, and navigation links to previous/next chapters.
4.  **Static Assets**: Copy CSS, JavaScript, and other static assets to the build directory.

## 3. GitHub Actions / GitHub Pages Integration

The generated static site will be pushed to a separate GitHub repository. A GitHub Actions workflow will be configured to:

1.  Trigger on push to the source repository (where the generator and content reside).
2.  Run the Python generator script.
3.  Commit the generated `build` directory content to the `gh-pages` branch of the target repository (or a separate `docs` folder in the `main` branch).

## 4. Image Embedding

Images will be embedded directly within the chapter's HTML content using `<img>` tags. The generator will ensure that image paths are relative to the generated HTML files and that the image files themselves are copied to the correct location in the build directory.

