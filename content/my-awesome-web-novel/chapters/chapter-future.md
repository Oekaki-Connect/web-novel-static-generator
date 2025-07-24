---
title: "Chapter Future: Scheduled Release"
author: "Original Author"
published: "2025-08-01"
tags: ["future", "scheduled", "test"]
translation_notes: "This chapter should not appear until August 1st, 2025"

# Social media embed settings (optional)
social_embeds:
  image: "/static/images/chapter-future-social.jpg"
  description: "A test chapter scheduled for future release to demonstrate the scheduled publishing feature."
  keywords: ["scheduled publishing", "future release", "automation"]

# SEO settings for this chapter
seo:
  allow_indexing: true
  meta_description: "Test chapter for scheduled publishing feature - should not be visible until publish date"

# Comments settings for this chapter
comments:
  enabled: true
---

# Chapter Future: Scheduled Release

This is a test chapter with a future publish date. It should not appear in the generated site until August 1st, 2025.

This chapter demonstrates the scheduled publishing feature:

- **Publish Date**: 2025-08-01
- **Current Behavior**: Should be excluded from builds (like draft chapters)
- **Future Behavior**: Will automatically appear when the publish date arrives
- **Automation**: GitHub Actions cron job will rebuild the site to include it

## Testing the Feature

To test this feature:

1. **Build normally**: This chapter should be excluded
2. **Build with `--include-scheduled`**: This chapter should be included
3. **Wait until August 1st, 2025**: This chapter will automatically appear

## Benefits

- Authors can write chapters in advance
- Consistent publishing schedule
- No manual intervention required
- Perfect for serial web novel releases