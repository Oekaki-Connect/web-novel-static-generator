# Web Novel Static Site Generator

A Python-based static website generator specifically designed for web novels, with support for GitHub Actions and GitHub Pages deployment.

You can see a demo build live on: https://oekaki-connect.github.io/web-novel/

You can see our version of it live on: https://www.ocwn.net/ 

## Why?

* I didn't see an existing static site generator for web novels which already existed
* Didn't want the baggage of trying to modifying an existing generic static site generator
* This generator works out of box fully with GitHub for free, it's easy to use, easy to modify

## Support

* You can open up issues in this repo to request features or improvements and they will be considered
* Do not open support issues if you can't figure out how to use this, this documentation is enough
* Do not join our discord or contact us for questions on how to set this up, read the docs
* If you can't figure it out on your own, ask a dev friend or a friendly AI to help you

## Features

- **Multi-Novel Support**: Host multiple novels from the same repository
- **Translation System**: Full multi-language support with language switching
- **EPUB Downloads**: Generate high-quality EPUB files for offline reading
- **Front Page**: Clean landing page listing all available novels
- **Table of Contents**: Organized by story arcs with manual chapter sorting
- **Chapter Pages**: Individual pages for each chapter with navigation
- **Chapter Navigation**: Dropdown menu for quick chapter jumping and breadcrumb navigation
- **Story Statistics**: Total length display with language-specific units (words/characters)
- **Story Metadata**: Publishing status (ongoing/complete/hiatus) and genre tags
- **Publication Dates**: Chapter publication dates displayed on table of contents
- **Tag System**: Categorize chapters with tags for easy discovery
- **Chapter Images**: Chapter-specific image support with automatic processing
- **Front Matter Support**: Rich metadata including author, translator, tags, and commentary
- **Social Media Integration**: Open Graph and Twitter Card meta tags for rich social sharing
- **SEO Optimization**: Configurable meta descriptions, keywords, and indexing controls
- **Clean URLs**: SEO-friendly URLs without .html extensions
- **Responsive Design**: Mobile-friendly layout
- **GitHub Integration**: Automated deployment via GitHub Actions
- **Password Protection**: Secure premium/beta content with client-side encryption
- **Hidden Chapters**: Chapters accessible only by direct link (not in navigation)
- **Draft Chapters**: Mark chapters as drafts to exclude from generation
- **Footer System**: Consistent footers with story-specific customization
- **Dark Mode Toggle**: System-aware dark/light theme with localStorage persistence
- **RSS Feeds**: Automatic RSS generation for site and individual stories
- **Webring Support**: Cross-promote with fellow authors through RSS-based discovery feeds
- **Asset Minification**: Build-time minification of HTML, CSS, and JavaScript for faster loading
- **Comments System**: Integrated Utterances comments with theme switching
- **robots.txt Generation**: Automatic SEO indexing control
- **Sitemap Generation**: XML sitemaps for search engine optimization
- **Reading Progress Tracking**: Track visited and completed chapters with localStorage
- **Modular Template Extensions**: Novel-specific template overrides for unique styling and branding
- **Scheduled Publishing**: Future-dated chapters automatically publish when their date arrives
- **Story Length Statistics**: Display word counts with language-specific units
- **Story Publishing Status**: Show "ongoing", "complete", or "hiatus" badges
- **Story Genre Tags**: Categorize stories by theme and genre
- **Accessibility Features**: ARIA labels, keyboard navigation, and alt text validation
- **Manga Features**: Supports comic / manga / manhwa too, though could still use some improvement
- **AND MORE!!!**: There are some additional undocumented features... check the examples!

## Project Structure

```
web-novel-generator/
├── .github/
│   └── workflows/
│       └── deploy.yml          # GitHub Actions workflow
├── content/
│   └── novel_title/
│       ├── config.yaml         # Novel configuration
│       ├── templates/          # Novel-specific template overrides (optional)
│       └── chapters/           # Chapter content files
├── templates/
│   ├── index.html             # Front page template
│   ├── toc.html               # Table of contents template
│   ├── chapter.html           # Chapter page template
│   ├── tags_index.html        # Tags index template
│   └── tag_page.html          # Individual tag page template
├── static/
│   ├── style.css              # Main stylesheet
│   ├── theme-toggle.js        # Dark mode toggle functionality
│   └── images/                # Image assets
├── build/                     # Generated site (auto-created)
├── site_config.yaml           # Site-wide configuration
├── webring.yaml               # Webring configuration (optional)
├── generate.py                # Main generator script
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## Quick Start

### 1. Setup

**Prerequisites:**
- Python 3.8 or higher ([Download Python](https://www.python.org/downloads/))
- Git (optional, for cloning the repository)(use GitHub Desktop if you like GUIs https://desktop.github.com/download/ )

**Verify Python is installed:**
```bash
python --version  # Should show Python 3.8 or higher
# On some systems, you may need to use python3 instead
```

**Clone or download this generator and install dependencies:**

```bash
# Clone the repository (if you have git)
git clone https://github.com/Oekaki-Connect/web-novel-static-generator.git
cd web-novel-static-generator

# Or download the ZIP file and extract it, then navigate to the folder

# Or fork it if you plan on contributing changes

# DO NOT fork if you want a private repo, you can't make forks private on GitHub
# If you want a private repo, download the ZIP, then make a new private repo

# Install Python dependencies
pip install -r requirements.txt
# On some systems, you may need to use pip3 instead
```

### 2. Configure Your Site

Create a `site_config.yaml` file in the root directory for global settings:

```yaml
site_name: "Your Web Novel Collection"
site_url: "https://your-username.github.io/your-repo-name"
site_description: "A collection of translated web novels and original stories"

# Social media embed settings
social_embeds:
  default_image: "https://your-username.github.io/your-repo-name/static/images/site-default-social.jpg"
  title_format: "{title} | Your Web Novel Collection"
  twitter_handle: "your_twitter_handle"

# SEO settings
seo:
  allow_indexing: true

# Footer configuration
footer:
  copyright: "© 2025 Your Web Novel Collection"
  links:
    - text: "Privacy Policy"
      url: "/privacy/"
    - text: "Contact"
      url: "/contact/"

# Comments system (Utterances)
comments:
  enabled: true
  repo: "your-username/your-comments-repo"
  issue_term: "pathname"
  label: "utterance-comment"

# RSS feed settings
rss:
  enabled: true
  max_items: 20

# Webring settings (cross-promotion with fellow authors)
webring:
  enabled: true
  max_items: 20  # Maximum number of recent chapters to display
  sites:
    - name: "Friend's Novel Site"
      url: "http://www.ocwn.net/"
      rss: "http://www.ocwn.net/rss.xml"
      description: "A great fantasy series"

# EPUB generation configuration
epub:
  generate_enabled: true

# NEW! chapter tags configuration
new_chapter_tags:
  enabled: true        # Show (NEW!) tags on recently published chapters
  threshold_days: 7    # Days to consider a chapter "new"

# Accessibility features configuration
accessibility:
  # Enable accessibility features and validation
  enabled: true
  
  # Require alt text for all images (warns about missing ones)
  enforce_alt_text: true
  
  # Automatically add ARIA labels to navigation elements
  auto_aria_labels: true
  
  # Enhance keyboard navigation support
  keyboard_navigation: true
  
  # Generate accessibility reports during build
  build_reports: true
```

### 3. Configure Your Novel

Create `content/your-novel-name/config.yaml`:

```yaml
title: "Your Awesome Novel"
description: "An epic fantasy adventure"
primary_language: "en"
status: "ongoing"  # "ongoing", "complete", or "hiatus"

# Story genre/theme tags
tags: ["fantasy", "adventure", "magic", "prophecy", "hero's journey"]

# Length display configuration
length_display:
  # Default unit for story length display on TOC pages
  default_unit: "words"  # "words" or "characters"
  
  # Language-specific overrides for different languages
  # This is useful because different languages have different conventions:
  # - Western languages (English, Spanish, French) typically use word count
  # - East Asian languages (Japanese, Chinese, Korean) typically use character count
  language_units:
    en: "words"      # English uses words (typical for Western languages)
    jp: "characters" # Japanese uses characters (typical for East Asian languages)

# Story arcs and chapters
arcs:
  - title: "Arc 1: Beginning"
    chapters:
      - id: "chapter-1"
        title: "Chapter 1: The Start"
      - id: "chapter-2"
        title: "Chapter 2: The Journey"

# Social media settings for this story
social_embeds:
  image: "/static/images/your-novel-social.jpg"
  description: "Follow the epic journey in this fantasy adventure"
  keywords: ["fantasy", "adventure", "web novel"]

# SEO settings for this story
seo:
  allow_indexing: true
  meta_description: "Read Your Awesome Novel - an epic fantasy web novel"

# Comments configuration for this story
comments:
  enabled: true  # Enable comments on TOC and chapters

# Downloads configuration  
downloads:
  epub_enabled: true     # Enable EPUB downloads for this story
  include_arcs: true     # Generate individual arc downloads

# Custom footer for this story (optional)
footer:
  copyright: "© 2025 Your Awesome Novel - Original work by Author Name"
  links:
    - text: "Support the Author"
      url: "https://ko-fi.com/pyramid"
    - text: "Source Code"
      url: "https://github.com/Oekaki-Connect/web-novel-static-generator"

# NEW! chapter tags override (optional)
new_chapter_tags:
  enabled: true        # Override site setting for this story
  threshold_days: 14   # Custom threshold (2 weeks instead of site default)
```

### 4. Add Chapter Content

Create markdown files in `content/your-novel-name/chapters/` with front matter:

```markdown
---
title: "Chapter 1: The Beginning"
author: "Original Author"
published: "2025-01-15"
tags: ["adventure", "magic", "prophecy"]
translation_notes: "Cultural context about specific terms"
hidden: false          # Set to true to hide from navigation (accessible by direct link only)
draft: false           # Set to true to exclude from generation (use --include-drafts to include)
password: "secret123"   # Optional: password protect this chapter
password_hint: "Available for beta readers and Patreon supporters. Check your email for the password."
comments: true          # Enable/disable comments for this chapter

# Social media settings for this chapter
social_embeds:
  image: "/static/images/chapter-1-social.jpg"
  description: "The hero begins their epic journey"
  keywords: ["chapter 1", "beginning", "fantasy"]

# SEO settings for this chapter
seo:
  allow_indexing: true
  meta_description: "Chapter 1 - The hero's journey begins"
---

# Chapter 1: The Beginning

Your chapter content here...
```

### 5. Add Images

You have two options for adding images to your novel:

#### Chapter-Specific Images (Recommended)

Place images directly in the chapter's source directory and reference them with simple filenames:

```markdown
![The Ancient Scroll](ancient_scroll.jpg "A mysterious scroll with golden edges")
```

**Directory Structure:**
```
content/
  my-awesome-web-novel/
    chapters/
      chapter-1.md          ← Your chapter file
      ancient_scroll.jpg    ← Your chapter image
      jp/                   ← Japanese translations
        chapter-1.md
        ancient_scroll_jp.jpg  ← Japanese version of the image
```

**Benefits:**
- Images stay organized with their chapters
- Easy for contributors to manage
- Automatic copying and path resolution during build
- Language-specific images supported

#### Global Images (Legacy)

You can also place images in the `static/images/` directory for site-wide use:

```markdown
![Description](static/images/your-image.jpg)
```

### 6. Generate the Site

See the [Command-Line Reference](#command-line-reference) section below for all available options.

Basic usage:
```bash
python generate.py                  # Standard build
python generate.py --include-drafts # Include draft chapters
```

The generated site will be in the `build/` directory.

### 7. Deploy to GitHub Pages

This generator includes automated deployment to GitHub Pages.

Here's how to set it up:

#### Using Separate Repositories

This method keeps your source code (and unpublished chapters) private while publishing only the built site.

Look up how to setup a domain with a GitHub repo if you want to use a domain. We're doing this with ocwn.net!

1. **Create two repositories:**
   - **Source repository**: Your private repository with the generator code (e.g., `my-novel-source`)
   - **Publishing repository**: Public repository for the built site (e.g., `my-novel-site`)

2. **Generate a Personal Access Token:**
   - Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Click "Generate new token (classic)"
   - Give it a descriptive name (e.g., "Novel Site Deployment")
   - Select scopes:
     - `repo` (Full control of private repositories)
     - `workflow` (Update GitHub Action workflows)
   - Generate and copy the token (you won't see it again!)

3. **Add the token to your source repository:**
   - Go to your source repository's Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `DEPLOY_TOKEN`
   - Value: Paste your personal access token
   - Click "Add secret"

4. **Update the deployment workflow:**
   - Edit `.github/workflows/deploy.yml` in your source repository
   - Update the repository reference:
   ```yaml
   - name: Deploy to GitHub Pages
     uses: peaceiris/actions-gh-pages@v3
     with:
       personal_token: ${{ secrets.DEPLOY_TOKEN }} # DO NOT HARD CODE IT HERE!
       external_repository: your-username/my-novel-site  # Your publishing repo
       publish_branch: main
       publish_dir: ./build
   ```

5. **Enable GitHub Pages on the publishing repository:**
   - Go to the publishing repository's Settings → Pages
   - Under "Source", select "Deploy from a branch"
   - Select "main" branch and "/ (root)" folder
   - Save the settings

6. **Push to trigger deployment:**
   ```bash
   git add .
   git commit -m "Setup deployment"
   git push origin main
   ```

Your site will be built in the source repository and deployed to: `https://your-username.github.io/my-novel-site/`

#### Custom Domain Setup

If you want to use a custom domain (e.g., `www.yournovel.com`) with GitHub Pages:

1. **Create a CNAME file:**
   - Create a file named `CNAME` (no extension) in the root directory of your project (next to `generate.py`)
   - Add your domain name to the file:
   ```
   www.yournovel.com
   ```

2. **The generator will automatically:**
   - Copy the CNAME file to the build directory during generation
   - Include it in the deployed site for GitHub Pages to recognize

3. **Configure your domain:**
   - Set up DNS records with your domain provider to point to GitHub Pages
   - In your GitHub repository, go to Settings → Pages
   - Under "Custom domain", enter your domain name
   - Enable "Enforce HTTPS" (recommended)

4. **Verify the setup:**
   - After deployment, GitHub Pages will automatically use your custom domain
   - Your site will be accessible at both the GitHub Pages URL and your custom domain

**Note:** The CNAME file must be in the root directory of your source repository and will be automatically included in every build.

#### Troubleshooting Deployment

- **403 Forbidden errors**: Check that your DEPLOY_TOKEN has the correct permissions
- **404 Not Found**: Ensure GitHub Pages is enabled and using the correct branch
- **Build failures**: Check the Actions tab for error logs
- **Token issues**: Regenerate the token if it expired or wasn't copied correctly

## Command-Line Reference

The generator supports various command-line options to customize the build process:

### Basic Commands

#### `python generate.py`
**Standard site generation**
- Builds the complete site with all features
- Excludes draft chapters (use `--include-drafts` to include them)
- Generates EPUB downloads
- Updates table of contents with download links

#### `python generate.py --include-drafts`
**Include draft chapters**
- Same as standard build but includes chapters marked with `draft: true`
- Useful for previewing work-in-progress content
- Draft chapters appear in navigation and downloads

### Development Commands

#### `python generate.py --validate`
**Validate configuration and content**
- Checks all config files for errors and missing required fields
- Validates that referenced chapter files exist
- Parses chapter front matter for syntax errors
- Reports warnings for missing optional fields
- Exits without building if validation fails

**Example output:**
```
Validating configuration files and content...
[OK] Site config loaded successfully
[OK] Novel config loaded: my-awesome-web-novel

==================================================
VALIDATION RESULTS
==================================================

[SUCCESS] Validation passed!
[PASSED] All configs and content are valid
```

#### `python generate.py --clean`
**Clean build directory**
- Deletes the entire `build/` directory before generating
- Ensures a completely fresh build without leftover files
- Useful when files have been deleted or renamed
- Can be combined with other options

#### `python generate.py --no-epub`
**Skip EPUB generation**
- Generates the website but skips creating EPUB files
- Significantly faster builds during development
- Useful when only testing website functionality
- Table of contents pages will not show download links

#### `python generate.py --stats`
**Generate statistics report**
- Creates a detailed `stats_report.md` file in the project root
- Shows comprehensive statistics about novels, chapters, and content
- Includes word counts, translation progress, and tag usage
- Useful for tracking project growth and completion

**Report includes:**
- Total novels, chapters, words, and characters
- Per-novel breakdowns with arc statistics
- Translation progress percentages
- Popular tags and usage counts
- Build file counts and language coverage
- Template override usage and statistics

#### `python generate.py --check-links`
**Check for broken links**
- Validates all internal links, images, and resources
- Creates `broken_links_report.md` if issues are found
- Checks social media preview images (og:image, twitter:image)
- Verifies CSS and JavaScript file references
- Should be run before deployment

#### `python generate.py --check-accessibility`
**Check accessibility compliance**
- Validates all images have alt text attributes
- Creates `images_missing_alt_text_report.md` if issues are found
- Skips report generation in GitHub Actions (detected automatically)
- Part of comprehensive accessibility feature set
- Helps ensure content is accessible to screen readers

### Performance Commands

#### `python generate.py --serve [PORT]`
**Local development server with live reload**
- Starts a local web server (default port 8000)
- Automatically rebuilds when files change
- Refreshes browser pages via websocket connection
- Injects live reload script into HTML pages
- Skips EPUB generation and image optimization for faster rebuilds
- Watches `content/`, `templates/`, `static/`, and `pages/` directories

**Usage examples:**
```bash
python generate.py --serve           # Start on port 8000
python generate.py --serve 3000      # Start on custom port
python generate.py --serve --include-drafts  # Include draft chapters
```

**Features:**
- **Live reload**: Browser automatically refreshes when files change
- **WebSocket connection**: Fast communication between server and browser
- **Smart rebuilding**: Only rebuilds when relevant files are modified
- **Development optimized**: Skips slow operations for faster iteration

#### `python generate.py --watch`
**Watch and rebuild without server**
- Monitors content files for changes
- Automatically rebuilds when changes detected
- No web server (use your own server setup)
- Useful with external development servers or static hosts

**Usage examples:**
```bash
python generate.py --watch                    # Basic watching
python generate.py --watch --include-drafts   # Include drafts
```

**Use cases:**
- External server setups (Apache, Nginx, etc.)
- Integration with other development tools
- Automated deployment workflows
- Continuous integration environments

#### `python generate.py --optimize-images`
**Convert images to WebP format**
- Converts JPEG, PNG, BMP, and TIFF images to WebP format
- Preserves original files alongside optimized versions
- Can be enabled permanently in site config or used as one-time flag
- Configurable compression quality (0-100, default: 100 = no compression)
- Shows compression statistics and space savings
- Significantly reduces site size and loading times

**Configuration in `site_config.yaml`:**
```yaml
image_optimization:
  enabled: true    # Enable automatic optimization
  quality: 85     # WebP quality (0-100)
```

**Example output:**
```
Optimizing images to WebP (quality: 85%)...
  Converted 2 images to WebP
  Original size: 298.9 KB
  WebP size: 22.9 KB
  Space saved: 92.4%
```

#### NEW! Chapter Tags

**Enable (NEW!) tags for recently published chapters**
- Shows a prominent (NEW!) indicator next to recently published chapters on table of contents
- Configurable threshold for how many days to consider chapters "new"
- Can be disabled globally or per-story for different content strategies

**Configuration in `site_config.yaml`:**
```yaml
new_chapter_tags:
  enabled: true        # Enable/disable (NEW!) tags globally
  threshold_days: 7    # Days to show NEW! tag (default: 7)
```

**Per-story override in `content/story/config.yaml`:**
```yaml
new_chapter_tags:
  enabled: true        # Override global setting
  threshold_days: 14   # Custom threshold (e.g., 2 weeks for this story)
```

**Example display:**
- `Chapter 5: The Climax (NEW!) 2025-07-22` - Published 1 day ago
- `Chapter 4: Building Tension 2025-07-15` - Published 8 days ago (no tag with 7-day threshold)

**Use Cases:**
- **Serial releases**: Highlight the latest chapters for returning readers
- **Story updates**: Draw attention to recently updated translations
- **Multi-story sites**: Different NEW! thresholds per story genre/audience
- **Seasonal content**: Longer thresholds for infrequently updated stories
- **Clean TOCs**: Disable entirely for completed stories or archives

### Combined Usage

Commands can be combined for complex workflows:

```bash
# Clean build with validation and stats
python generate.py --clean --validate --stats

# Fast development build without EPUBs
python generate.py --clean --no-epub --include-drafts

# Production build with link checking
python generate.py --clean --check-links

# Complete development workflow with live reload
python generate.py --clean --serve --include-drafts

# Watch-only mode for external servers
python generate.py --clean --watch --include-drafts
```

### Command-Line Help

Get help and see all available options:
```bash
python generate.py --help
```

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

### Modular Template Extensions

Create novel-specific template overrides for unique styling and branding:

**Directory Structure:**
```
content/
  your-novel-name/
    templates/
      chapter.html      ← Custom chapter template for this novel
      toc.html         ← Custom table of contents (optional)
    chapters/
      chapter-1.md     ← Chapter content
    config.yaml        ← Novel configuration
```

**Features:**
- **Novel-specific branding**: Each novel can have its own unique look and feel
- **Template inheritance**: Falls back to default templates seamlessly
- **Gradual customization**: Override only the templates you want to customize
- **Multi-novel support**: Different novels can have completely different designs
- **Statistics tracking**: Monitor template override usage in stats reports

**Example Custom Template:**
```html
<!-- Custom styling in content/my-novel/templates/chapter.html -->
<style>
.custom-novel-header {
    background: linear-gradient(135deg, #4a5568 0%, #2d3748 100%);
    color: white;
    padding: 20px;
    text-align: center;
    border-radius: 8px;
}
</style>

<div class="custom-novel-header">
    <h1>{{ novel_title }}</h1>
    <div>Custom Story Template</div>
</div>

<!-- All standard template functionality preserved -->
```

**Template Variables Available:**
- `novel_slug`: Novel identifier
- `novel_title`: Novel display title  
- `chapter_id`: Current chapter ID
- `chapter_title`: Current chapter title
- `arcs`: Complete story arc structure
- `language`: Current language code
- `available_languages`: Available language options
- All other standard template variables

**Benefits:**
- Create unique themes for different story genres
- Maintain consistent branding across novel chapters
- Easy to implement and maintain
- Full access to all template functionality
- Tracked in statistics reports

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

### Password Protection

If you use password protection, you should not have your main repo public. This static generator wants you to have two different GitHub repos one for the source code and your project files, and another which you publish to. Although you're not required to publish to a GitHub repo. It's a static site generator, you can upload the static files to any server.

Secure premium or beta content with client-side encryption:

```markdown
---
title: "Premium Chapter: Early Access"
password: "your-secret-password"
password_hint: "Available for beta readers and Patreon supporters. Check your email for the password."
---

Your premium content here...
```

**Features:**
- Client-side XOR encryption with SHA256 password hashing
- Custom password hints for users
- Encrypted content is never sent to unauthorized users
- Works without server-side processing

### Hidden Chapters

Create chapters accessible only by direct link:

```markdown
---
title: "Secret Chapter"
hidden: true
---

This chapter won't appear in navigation but can be accessed directly.
```

**Use Cases:**
- Easter eggs and bonus content
- Beta reader exclusive chapters
- Special event content
- Author notes or behind-the-scenes content

Note: If you are hosting on GitHub on a public repo anyone can discover hidden pages easily.

### Draft Chapters

Mark work-in-progress chapters as drafts to exclude them from generation:

```markdown
---
title: "Chapter 10: Work in Progress"
draft: true
published: "2025-02-01"
---

This chapter is still being written and won't be included in the generated site.
```

**Features:**
- Completely excluded from generation by default
- Not included in TOC, EPUB downloads, RSS feeds, or sitemaps
- Use `--include-drafts` flag to include them: `python generate.py --include-drafts`
- Console output shows skipped drafts: "Skipping draft chapter: chapter-10 - Chapter 10: Work in Progress"
- Perfect for work-in-progress content or scheduled releases

**Use Cases:**
- Work-in-progress chapters
- Scheduled content releases (see Scheduled Publishing)
- Beta testing new chapters
- Collaborative editing before publication

### Scheduled Publishing

Publish chapters automatically when their scheduled date arrives:

```markdown
---
title: "Chapter 10: The Big Reveal"
published: "2025-08-01"
tags: ["plot-twist", "reveal", "climax"]
---

This chapter will automatically appear on the site on August 1st, 2025.
```

**How It Works:**
- Chapters with future `published` dates are excluded from normal builds
- Use `--include-scheduled` flag to preview: `python generate.py --include-scheduled`
- GitHub Actions workflows automatically rebuild when content becomes available
- Supports multiple date formats (ISO, RFC, plain dates)
- Time zone aware - uses UTC if no timezone specified

**Date Format Examples:**
```yaml
published: "2025-08-01"                    # Simple date (midnight UTC)
published: "2025-08-01 14:30:00"           # Date and time
published: "2025-08-01T14:30:00"           # ISO format
published: "2025-08-01T14:30:00Z"          # UTC timezone
published: "2025-08-01T14:30:00-05:00"     # With timezone offset
```

**GitHub Actions Automation:**

You can remove these files if you only intend to update when you push changes / you do not want future scheduled releases.

1. **Daily Scheduled Rebuild** (`.github/workflows/scheduled-rebuild.yml`):
   - Runs daily at midnight UTC
   - Rebuilds entire site for general maintenance and newly available content
   - Provides reliable daily updates for future features
   - Can be disabled if daily rebuilds aren't needed

2. **Smart Hourly Rebuild** (`.github/workflows/smart-scheduled-rebuild.yml`):
   - Runs every hour from 1 AM to 11 PM UTC (skips midnight)
   - Checks if any scheduled content is ready for publishing
   - Only rebuilds when chapters have actually become available
   - More efficient for sites with frequent scheduled releases

**Workflow Schedule:**
```yaml
# Daily rebuild at midnight
schedule:
  - cron: '0 0 * * *'      # Daily at midnight UTC

# Smart hourly rebuild (skips midnight to avoid conflicts)
schedule:
  - cron: '0 1-23 * * *'   # Every hour from 1 AM to 11 PM UTC

# Custom schedule examples:
  - cron: '0 */12 * * *'   # Every 12 hours
  - cron: '0 9 * * MON'    # Weekly on Monday at 9 AM
  - cron: '0 6,18 * * *'   # Twice daily at 6 AM and 6 PM
```

**How the Dual System Works:**
- **Midnight (00:00)**: Daily rebuild runs for maintenance and batch updates
- **1 AM - 11 PM**: Smart rebuild checks hourly for new scheduled content
- **No conflicts**: Workflows are designed to never overlap
- **Flexibility**: Either workflow can be disabled independently

**Use Cases:**
- **Serial releases**: Schedule chapters weeks in advance
- **Timed reveals**: Coordinate story events with real-world dates
- **Buffer management**: Upload multiple chapters but release gradually
- **Event tie-ins**: Release special chapters on holidays or anniversaries
- **Time zone releases**: Schedule for specific regions

**Chapter Publishing Logic:**
- **No `published` date**: Always included in builds (traditional behavior)
- **Past/current `published` date**: Always included in builds  
- **Future `published` date**: Excluded until the date arrives (unless `--include-scheduled` is used)

**Console Output:**
```
⏳ Skipping future chapter: chapter-10 - Chapter 10: The Big Reveal (publishes: 2025-08-01)
⏳ Skipping future chapter: chapter-11 - Chapter 11: Aftermath (publishes: 2025-08-08)
```

**Best Practices:**
- Chapters without dates work like traditional static content (always published)
- Set publish dates in UTC to avoid timezone confusion
- Test scheduled content with `--include-scheduled` before the release date
- Monitor GitHub Actions runs to ensure successful rebuilds
- Consider using smart rebuilds for efficiency with many scheduled chapters

### Comments System

Integrated Utterances comments that automatically sync with your dark mode:

**Site Configuration:**
```yaml
comments:
  enabled: true
  repo: "your-username/your-comments-repo"
  issue_term: "pathname"
  label: "utterance-comment"
```

**Chapter Control:**
```markdown
---
comments: false  # Disable comments for this chapter
---
```

**Features:**
- GitHub-based comment system
- Automatic theme switching (light/dark)
- Story-level and chapter-level control
- No comments on password-protected content

### Dark Mode Toggle

System-aware dark/light theme with user preference persistence:

**Features:**
- Detects system theme preference automatically
- Footer text toggle: "[ light mode | dark mode ]"
- Active mode shown in bold
- Saves preference in localStorage
- Switches Utterances comment themes automatically
- Optimized dark mode styling for all UI elements

### RSS Feeds

Automatic RSS feed generation for content syndication:

**Generated Files:**
- `/rss.xml` - Site-wide feed with latest chapters from all stories
- `/story-name/rss.xml` - Story-specific feeds

**Features:**
- Configurable maximum items per feed
- Proper RSS 2.0 format with metadata
- Automatic chapter descriptions and links
- Story-specific feeds for targeted subscriptions

### Webring Support

Build community and cross-promote with fellow authors through RSS-based discovery feeds:

**What is a Webring?**
A webring is a collection of websites linked together for mutual promotion and discovery. In web novel communities, webrings help authors support each other by featuring recent chapter releases from trusted authors on their front pages.

You can also set this only on your own RSS to show your most recent updates!

**How it Works:**
1. Authors maintain a `webring.yaml` file listing RSS feeds of other authors they recommend
2. At build time, the generator fetches recent chapters from these RSS feeds
3. A clean "Recent Updates from the Webring" section appears on your front page
4. Readers discover new content from authors you trust and recommend

**Configuration (`webring.yaml`):**
```yaml
webring:
  enabled: true
  max_items: 20  # Number of recent items to display
  cache_duration: 3600  # Cache feeds for 1 hour
  
  sites:
    - name: "Fantasy Author A"
      url: "http://www.ocwn.net/novel/"
      rss: "http://www.ocwn.net/novel/rss.xml" 
      description: "Epic fantasy adventure series"
    
    - name: "Sci-Fi Author B"
      url: "http://www.ocwn.net/"
      rss: "http://www.ocwn.net/rss.xml"
      description: "Space opera with great characters"

You can see an example of a site RSS here: https://oekaki-connect.github.io/web-novel/rss.xml
And a story RSS here: https://oekaki-connect.github.io/web-novel/my-awesome-web-novel/rss.xml

If you want to promote an entire site of someone else you can, otherwise you can promote a specific story.

# Display customization
display:
  title: "Recent Updates from the Webring"
  subtitle: "Check out recent chapters from fellow authors we recommend"
  show_descriptions: true
  show_dates: true
  date_format: "%B %d, %Y"
```

**Features:**
- **Build-time fetching**: RSS feeds are fetched during site generation for fast loading
- **Torrent tracker inspired design**: Clean, information-dense layout showing [SITE] Chapter Title - Date
- **Responsive layout**: Works perfectly on mobile and desktop
- **Failure resilient**: If a feed is unavailable, other feeds still work
- **Automatic sorting**: Recent chapters from all sites sorted by publication date
- **Trust-based**: You control which authors appear on your site

**Why Webrings Are Cool:**
- **Community building**: Support indie authors and translators
- **Reader discovery**: Help your readers find great content from authors you trust
- **Reciprocal promotion**: Authors can feature each other's work
- **Quality curation**: Only recommend authors whose work you genuinely enjoy
- **Decentralized**: No central authority - each author controls their own webring
- **SEO benefits**: External links and fresh content help with search rankings
- **Nostalgic**: Brings back the community spirit of the early web

**Setting Up Your Webring:**
1. Create `webring.yaml` in your project root
2. Add RSS feeds of authors you want to promote
3. Rebuild your site - the webring section appears automatically
4. Reach out to fellow authors to join their webrings too!

**Best Practices:**
- Only include authors whose work you've read and genuinely recommend
- Keep descriptions brief and appealing
- Update your webring periodically as you discover new authors
- Consider genre compatibility with your audience
- Reciprocate when other authors add you to their webrings

### Front Page Novel Sorting

Control how novels appear on your site's front page with flexible sorting options:

**Configuration in `site_config.yaml`:**
```yaml
front_page:
  # Sort novels by most recent chapter update
  sort_by_recent_update: true
  
  # Manual sort order for featured novels (by slug)
  featured_order:
    - tower-dungeon     # Always appears first
    - my-featured-novel # Always appears second
```

**Sorting Behavior:**
1. **Featured novels** appear first in the exact order specified in `featured_order`
2. **Non-featured novels** follow after, sorted by:
   - Most recent chapter update (if `sort_by_recent_update: true`)
   - Original order (if `sort_by_recent_update: false`)

**Use Cases:**
- **Feature new releases**: Pin a new novel to the top during launch period
- **Promote completed stories**: Feature finished novels to attract new readers
- **Activity-based discovery**: Let active stories naturally rise to the top
- **Curated experience**: Manually control the exact order for optimal presentation

**Example Configurations:**

*Activity-focused site (default):*
```yaml
front_page:
  sort_by_recent_update: true
  featured_order: []  # No pinned novels
```

*Curated recommendations:*
```yaml
front_page:
  sort_by_recent_update: false
  featured_order:
    - editors-pick-1
    - editors-pick-2
    - new-release
```

### robots.txt and Sitemap

Automatic SEO optimization files:

**robots.txt:**
- Controls search engine indexing
- Respects `allow_indexing` settings in config files
- Links to sitemap for better discovery

**sitemap.xml:**
- Comprehensive XML sitemap
- All public pages included
- Proper priority and change frequency settings
- Supports search engine optimization

### Footer System

Consistent footers with story-specific customization:

**Site-level Footer:**
```yaml
footer:
  copyright: "© 2025 Your Website"
  links:
    - text: "Privacy Policy"
      url: "/privacy/"
```

**Story-level Override:**
```yaml
footer:
  copyright: "© 2025 Story Title - Original work by Author"
  links:
    - text: "Support the Author"
      url: "https://ko-fi.com/pyramid"
```

### Chapter Front Matter

Add metadata to your chapters using YAML front matter:

```markdown
---
title: "Chapter 1: The Beginning"
author: "Original Author"
translator: "Translator Name"
published: "2025-01-15"
tags: ["adventure", "magic", "prophecy"]
translation_notes: "Cultural context about specific terms used"
translator_commentary: |
  This chapter establishes the fantasy setting beautifully. I chose to 
  translate certain terms to maintain the magical atmosphere while 
  keeping them accessible to readers.
---

# Chapter 1: The Beginning

Your chapter content here...
```

**Supported Fields:**
- `title`: Override chapter title
- `author`: Original author name
- `translator`: Translator credit (for translations)
- `published`: Publication date
- `tags`: Array of tags for categorization
- `translation_notes`: Cultural/linguistic context
- `translator_commentary`: Extended commentary displayed at chapter end
- `hidden`: Hide chapter from navigation (accessible by direct link only)
- `draft`: Mark chapter as draft (excluded from generation unless --include-drafts is used)
- `password`: Password protect the chapter content
- `password_hint`: Hint text shown to users for password-protected content
- `comments`: Enable/disable comments for this specific chapter
- `social_embeds`: Social media sharing configuration
  - `image`: Custom social media image
  - `description`: Social media description
  - `keywords`: Keywords for SEO and social sharing
- `seo`: SEO configuration
  - `allow_indexing`: Control search engine indexing
  - `meta_description`: Custom meta description

### Tag System

Tags automatically create browsable indexes:
- **All Tags Page**: `/novel/language/tags/` - Lists all tags with chapter counts
- **Tag Pages**: `/novel/language/tags/tag-name/` - Shows all chapters with that tag
- **Clickable Tags**: All tags in chapter metadata are clickable links

Perfect for organizing content by theme, genre, or story elements.

### Multi-Language Support

**URL Structure:**
- English: `/my-awesome-web-novel/en/chapter-1/`
- Japanese: `/my-awesome-web-novel/jp/chapter-1/`
- Tags: `/my-awesome-web-novel/jp/tags/予言/` (supports Unicode)

**Translation Workflow:**
1. Create language subdirectory: `chapters/jp/`
2. Add translated chapters with front matter
3. Language switcher appears automatically
4. Missing translations show helpful notices

### Social Media Integration

The generator automatically creates rich social media previews:

**Open Graph Tags** (Facebook, LinkedIn, Discord):
- `og:title`, `og:description`, `og:image`
- `og:url`, `og:type`, `og:site_name`
- Article-specific tags for chapters

**Twitter Cards**:
- `twitter:card`, `twitter:title`, `twitter:description`
- `twitter:image`, `twitter:site`, `twitter:creator`

**Hierarchical Configuration**:
- Site-wide defaults in `site_config.yaml`
- Story-level settings in `content/novel/config.yaml`
- Chapter-level overrides in front matter
- Chapter settings override story settings, story settings override site defaults

### SEO Optimization

**Meta Tags**:
- Configurable meta descriptions and keywords
- Robots meta tag for indexing control
- Canonical URLs for all pages

**Structured Data**:
- Article metadata for chapters
- Publication dates and author information
- Tag-based content organization

### Multiple Novels

The generator automatically detects and processes multiple novels:
1. Create subdirectories in `content/` for each novel
2. Add a `config.yaml` file in each novel directory
3. The front page will list all available novels

### Story Publishing Status

Display the current status of your story on the table of contents:

```yaml
# In your story config.yaml
status: "ongoing"  # "ongoing", "complete", or "hiatus"
```

**Features:**
- Shows "Ongoing", "Complete", or "Hiatus" badge on TOC page
- Color-coded badges (blue for ongoing, green for complete, orange for hiatus)
- Automatic dark mode styling

### Story Length Statistics

Display total story length with culturally appropriate units:

```yaml
# In your story config.yaml
length_display:
  default_unit: "words"  # Default for all languages
  language_units:
    en: "words"      # English shows word count
    jp: "characters" # Japanese shows character count
    zh: "characters" # Chinese shows character count
    es: "words"      # Spanish shows word count
```

**Features:**
- Automatically calculates total length from all visible chapters
- Excludes hidden and password-protected content
- Language-specific display (words for Western languages, characters for East Asian)
- Formatted with comma separators (e.g., "12,345 words")

### Story Genre Tags

Add genre and theme tags to your stories:

```yaml
# In your story config.yaml
tags: ["fantasy", "adventure", "magic", "prophecy", "hero's journey"]
```

**Features:**
- Non-clickable genre tags displayed on TOC page
- Clean tag styling with dark mode support
- Helps readers understand story themes at a glance

### Accessibility Features

Comprehensive accessibility support for improved usability and compliance:

**ARIA Labels:**
- Semantic navigation labeling for screen readers
- Breadcrumb navigation: `aria-label="Breadcrumb"`
- Chapter navigation: `aria-label="Chapter navigation"`
- Language switchers: `role="group" aria-label="Language selection"`
- Reading settings: `role="group" aria-label="Reading settings"`
- Footer links: `aria-label="Footer links"`

**Keyboard Navigation:**
- **Navigation shortcuts**: `←/h` (previous chapter), `→/l` (next chapter), `t` (table of contents)
- **Scrolling shortcuts**: `↑/k` (scroll up), `↓/j` (scroll down), `Home/g` (go to top), `End/G` (go to bottom)
- **Reading controls**: `+/=` (increase text size), `-` (decrease text size), `0` (reset settings)
- **Help system**: `?` (show keyboard shortcuts modal), `Esc` (close modals)
- Smart detection to avoid conflicts with form inputs
- Comprehensive help modal with organized shortcut display

**Alt Text Validation:**
- Automated checking of all generated HTML files
- Detects images missing alt attributes using BeautifulSoup4
- Generates `images_missing_alt_text_report.md` for local builds
- Skips report generation in GitHub Actions (detected automatically)
- Configurable enforcement levels

**Configuration:**
```yaml
# In site_config.yaml
accessibility:
  enabled: true              # Enable all accessibility features
  enforce_alt_text: true     # Validate alt text on images
  auto_aria_labels: true     # Add ARIA labels to navigation
  keyboard_navigation: true  # Enable keyboard shortcuts
  build_reports: true        # Generate accessibility reports
```

**Features:**
- Works across both main templates and story-specific template overrides
- Respects site theme preferences (light/dark mode support)
- Mobile-responsive keyboard help modal
- No conflicts with existing JavaScript functionality
- Comprehensive accessibility reporting

**Usage:**
```bash
# Check accessibility compliance
python generate.py --check-accessibility

# Standard build includes accessibility checks if enabled
python generate.py
```

### EPUB Downloads

Generate high-quality EPUB files for offline reading:

**Features:**
- Full story EPUB downloads
- Individual arc EPUB downloads  
- Multi-language support (separate EPUBs per language)
- Embedded images with proper centering
- Cover art integration for stories and arcs
- Clean chapter pagination and formatting
- Compatible with all major e-readers

**Configuration:**
```yaml
# In site_config.yaml
epub:
  generate_enabled: true

# In story config.yaml  
downloads:
  epub_enabled: true
  include_arcs: true
```

**Generated Files:**
- `/static/epub/story-name.epub` - Full story download
- `/static/epub/story-name_jp.epub` - Japanese version (if available)
- `/static/epub/story-name-arc-1-title.epub` - Individual arc/volume downloads

### Chapter Navigation Enhancements

**Chapter Dropdown:** Quick navigation dropdown on chapter pages
- Organized by story arcs
- Shows current chapter as selected
- Excludes hidden chapters
- JavaScript-powered navigation

**Breadcrumb Navigation:** Clear page hierarchy navigation
- Chapter pages: Home > Story > Chapter
- TOC pages: Home > Story
- Mobile-friendly responsive design

**Publication Dates:** Chapter publication dates displayed on TOC
- Shows publication date next to each chapter title
- Desktop: side-by-side layout
- Mobile: stacked layout
- Only shows if `published` date is set in chapter front matter

### Reading Progress Tracking

Automatically track reader progress with localStorage:

**Features:**
- Mark chapters as visited when opened
- Mark chapters as completed when scrolled to bottom
- Visual indicators on table of contents (○ for visited, ✓ for completed)
- "Continue Reading" section showing last completed chapter
- Persists across browser sessions
- Per-story tracking (multiple novels supported)
- Note: Reading is only tracked per browser, not on any server

### Enhanced Navigation Structure

**URL Structure with Breadcrumbs:**
```
Home (/) 
  └── Story (/story/en/toc/)
      └── Chapter (/story/en/chapter-1/)
```

**Chapter Page Features:**
- Jump to Chapter dropdown for quick navigation
- Previous/Next chapter links
- Table of Contents link
- Breadcrumb navigation showing current location

## Dependencies

- `jinja2`: Template engine for HTML generation
- `markdown`: Markdown to HTML conversion
- `pyyaml`: YAML configuration file parsing
- `ebooklib`: EPUB generation and manipulation
- `Pillow`: Image processing for WebP optimization (optional)
- `watchdog`: File system monitoring for live reload (optional)
- `websockets`: WebSocket server for live reload (optional)

## Troubleshooting

### Getting Help

For a complete list of available commands and options:
```bash
python generate.py --help
```

Use `--validate` to check for configuration errors before building:
```bash
python generate.py --validate
```

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
- Search functionality (using offline database)
- Chapter bookmarking (using localStorage)
- Improve the manga reader (better page transitions, double vertical scroll)
- Break the current monolith generate.py into sub dependencies
- Maybe convert the webring feature into something dynamic done when someone visits front pages
- Something you think it needs! If you make pull requests please know what you're doing
- If you're a Firefox user and a dev, please fix any CSS that's Firefox specific
- Full screen single image mode on mobile 2:3 jumps around in a weird way when changing images
- Need to make the entire site text easier to localize, if the site lang is on a certain lang it should default to chapters of that lang if available