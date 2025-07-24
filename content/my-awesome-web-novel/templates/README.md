# Novel-Specific Template Overrides

This directory contains custom templates that override the default site templates specifically for "My Awesome Web Novel". The template override system allows each novel to have its own unique styling and layout while maintaining the overall site structure.

## How It Works

1. **Template Detection**: The generator automatically detects `templates/` directories within novel content folders
2. **Override Priority**: Novel-specific templates take precedence over default site templates
3. **Template Loading**: A novel-specific Jinja2 environment is created with access to both custom and default templates
4. **Statistics Tracking**: Template overrides are tracked and reported in the stats report

## Available Template Variables

When creating custom templates, you have access to all the same variables as the default templates, including:

- `novel_slug`: The novel's slug identifier
- `novel_title`: The novel's display title
- `chapter_id`: Current chapter identifier
- `chapter_title`: Current chapter title
- `arcs`: Complete story arc structure
- `language`: Current language code
- `available_languages`: List of available language options
- And many more...

## Example: Custom Chapter Template

The `chapter.html` template in this directory demonstrates:

- **Custom CSS styling** with a purple gradient header
- **Novel-specific branding** with fantasy theme elements
- **Custom chapter introduction** section
- **All standard functionality** preserved (navigation, settings, etc.)

## Benefits

- **Novel-specific branding**: Each novel can have its own unique look and feel
- **Gradual customization**: Override only the templates you want to customize
- **Maintainability**: Changes to default templates still apply unless specifically overridden
- **Multi-novel support**: Different novels can have completely different designs

## File Structure

```
content/
  my-awesome-web-novel/
    templates/
      chapter.html       ← Custom chapter template
      toc.html          ← Custom table of contents (if needed)
      README.md         ← This documentation
    chapters/
      chapter-1.md      ← Chapter content
    config.yaml         ← Novel configuration
```

## Implementation Details

The system works by:

1. Creating novel-specific Jinja2 environments with custom template directories
2. Checking for template overrides before falling back to defaults
3. Maintaining all standard template functionality and variables
4. Providing statistics on template usage in the stats report

This allows for powerful customization while keeping the core generator simple and maintainable.