# On-page scoring model

`scripts/onpage_review.py` scores each check `pass` (full weight), `warn` (half)
or `fail` (zero). The score is the weighted share of the total, 0-100. Keyword
checks only exist when `--keyword` is passed, so scores with and without a
keyword are not directly comparable.

| Check | Weight | Pass | Warn | Fail |
| --- | --- | --- | --- | --- |
| `indexable` | 10 | no `noindex`/`none` in meta robots | - | noindex |
| `title` | 10 | one title, 30-60 chars | too short/long, several titles | missing |
| `h1` | 8 | exactly one non-empty H1 | several H1s | none or empty |
| `meta-description` | 6 | one, 70-160 chars | length outside range, several | missing |
| `canonical` | 6 | one absolute canonical (self when `--url` given) | relative, or points elsewhere | missing or conflicting |
| `word-count` | 6 | >= 300 words of body text | 150-299 | < 150 |
| `internal-links` | 6 | >= 3 | 1-2 | 0 |
| `mixed-content` | 4 | no `http://` subresources (only checked when the page URL or canonical is https) | `http://` images, `srcset`, video posters, audio/track | `http://` scripts, stylesheets, iframes, objects |
| `heading-outline` | 4 | H2s present, no skipped levels | skipped levels, empty headings, no H2 | - |
| `image-alt` | 4 | every `<img>` has an alt attribute | some missing, or no images | more than half missing |
| `viewport` | 3 | viewport meta | - | missing |
| `anchor-text` | 3 | no generic anchors | "click here", "read more"... | - |
| `open-graph` | 3 | og:title, og:description, og:image | any missing | - |
| `structured-data` | 3 | at least one JSON-LD block | none | - |
| `lang` | 2 | `<html lang>` set | - | missing |
| `title-h1-distinct` | 2 | (only reported when identical) | identical | - |
| `external-links` | 1 | at least one | none | - |
| `keyword-title` | 6 | phrase in title | - | absent |
| `keyword-h1` | 4 | phrase in an H1 | - | absent |
| `keyword-first-100-words` | 3 | phrase in first 100 body words | - | absent |
| `keyword-meta-description` | 2 | phrase in meta description | - | absent |
| `keyword-stuffing` | 3 | (only reported when > 3% density) | stuffed | - |

Keyword matching is whole-word and case-insensitive (`"trail running shoes"`
matches "Trail Running Shoes" but "rest" does not match "restaurant"). Treat a
miss as a prompt to check for a natural variant, not as a demand for an exact match.

## Why these thresholds

- **Title 30-60 characters.** Google truncates by pixel width (~600 px); 60
  characters is a safe proxy. Short titles waste the most prominent ranking and
  click signal on the results page.
- **Meta description 70-160 characters.** Not a ranking factor, but it is the
  default snippet. Google rewrites many descriptions; matching the query and page
  content makes yours more likely to be used.
- **One H1.** HTML allows several, and Google copes; one clear H1 keeps the topic
  unambiguous for users, assistive tech and parsers.
- **300 words.** Not a ranking rule; a heuristic for "thin". Product, tool and
  category pages can be fine with less if they satisfy the intent - say so in the
  review instead of padding the page.
- **3+ internal links.** Internal links spread discovery and context; pages with
  none are hard to crawl from and leave users at a dead end.
- **Body text** excludes `<head>`, `<script>`, `<style>`, `<noscript>`,
  `<template>` and `<svg>`; navigation and footer text is counted, so word counts
  on template-heavy pages run high.

## What the score does not measure

- Whether the page satisfies search intent better than the current top results.
- Content quality, originality, accuracy, author expertise, freshness.
- Rendered content that only appears after JavaScript runs (unless you feed the rendered HTML).
- Speed and layout stability (`core-web-vitals-triage`).
- Backlinks and site-level authority.
