---
title: "Chapter Recent: Just Published"
author: "Original Author"
published: "2025-07-20"
tags: ["recent", "test", "demo"]
translation_notes: "This chapter should appear since it has yesterday's date"

# Social media embed settings
social_embeds:
  description: "A test chapter with a recent publish date to demonstrate the scheduled publishing feature."
  keywords: ["recent", "published", "test"]

# SEO settings
seo:
  allow_indexing: true
  meta_description: "Test chapter with recent publish date - should be visible immediately"
---

# Chapter Recent: Just Published

This chapter has a publish date of January 23rd, 2025, which is in the recent past. It should always appear in builds.

This demonstrates that the scheduled publishing feature only affects chapters with **future** publish dates.

## Comparison

| Chapter | Publish Date | Status |
|---------|-------------|--------|
| Chapter Recent | 2025-01-23 | ✅ Always included |
| Chapter Future | 2025-08-01 | ❌ Excluded until August 1st |
| Regular chapters | No date or past dates | ✅ Always included |

## Testing Results

- Normal build: This chapter appears
- `--include-scheduled` build: This chapter still appears 
- Future chapters: Only appear with `--include-scheduled`