---
name: on-page-seo-review
description: Score the on-page SEO of a single page (0-100) - title, meta description, H1 and heading outline, canonical, robots, image alt text, internal and anchor links, word count, Open Graph, structured data and target-keyword placement - and rewrite the weak elements. Works on an HTML file, a template's rendered output, or a URL when fetching is allowed. Use when the user asks to review, optimise or "SEO check" a page, post, landing page or template, or asks for better titles and meta descriptions.
license: MIT
---

# On-page SEO review

Measure one page against on-page best practice with a deterministic score, then
give concrete rewrites (titles, descriptions, headings, anchors) the user can paste.

Paths below are relative to this skill's directory.

## When to use

- "Review the SEO of this page / post / template", "optimise this landing page for <keyword>"
- "Write a better title and meta description"
- Checking a template change before it ships (run on the built HTML)

## When not to use

- Site-wide crawl, canonical or redirect problems: `technical-seo-audit`.
- Writing a new article from scratch: start with `content-brief`.
- Validating JSON-LD in depth: `schema-markup`.
- Page speed: `core-web-vitals-triage`.

## Inputs to collect

1. The page: a local HTML file (preferred), built output of a template, or a URL.
2. The primary keyword or topic (ask if not given; the score works without it but keyword checks are skipped).
3. The public URL, if the file is local (`--url`), so links and the canonical can be classified.

## Workflow

1. **Get rendered HTML.** For a framework project, build or render the page first (static export, SSR output, or save the page from the browser). For a URL, only fetch if the user asked you to look at that live page:
   `python3 scripts/onpage_review.py https://example.com/page --fetch --keyword "..." --json`
   Otherwise:
   `python3 scripts/onpage_review.py page.html --url https://example.com/page --keyword "..." --json`
2. **Read the result.** `score` is weighted; each check is `pass`, `warn` or `fail` with a `fix`. Exit code 1 means the score is under `--min-score` (default 70).
3. **Check what the script cannot judge** (see [references/scoring.md](references/scoring.md)):
   - Does the content satisfy the search intent behind the keyword? Look at what currently ranks if the user can share it.
   - Is the title compelling, not just keyword-correct? Is the H1 specific?
   - Is the main content unique, current and demonstrably expert (author, sources, first-hand detail)?
   - Are internal links pointing to the most relevant pages, with descriptive anchors?
4. **Write fixes** in priority order: indexability, title, H1, meta description, content gaps, internal links, images, social and schema.
5. **When editing code**, change the template or component that produces the element (layout `<head>`, CMS field, frontmatter), not just one rendered file. Re-run the script on the rebuilt output to confirm the score moved.

## Writing rules

- **Title (30-60 characters):** primary topic first, one differentiator (year, number, audience, benefit), brand last if space allows. Unique per page.
- **Meta description (70-160 characters):** answer the query, add a reason to click, match the page. Google may rewrite it; a good one still wins more often.
- **H1:** one per page, states the topic in plain words; may differ from the title.
- **Headings:** H2s mirror the sub-questions searchers have; never skip levels for styling.
- **Keyword use:** in title, H1, first 100 words and naturally in a subheading. Density targets are a myth; over ~3% reads as stuffing.
- **Anchors:** describe the destination ("trail shoe sizing guide"), never "click here".
- **Images:** descriptive alt on informative images, `alt=""` on decorative ones; set width and height.

Offer 2-3 title and description options when rewriting, each with its character count.

## Output

```
## On-page review: <URL or file> - score <N>/100 (keyword: "<kw>")

### Fix first
1. <issue> -> <exact fix or rewritten text>
...

### Suggested title / meta description
| Option | Title (chars) | Meta description (chars) |

### Heading outline (current -> suggested)

### Content and intent notes
<gaps vs. intent, missing subtopics, E-E-A-T signals>

### Passing checks
<one line>
```

Quote the script's numbers (lengths, counts, score) exactly. If you could not
render JavaScript content, say so.

## Files

- `scripts/onpage_review.py` - scoring script (`--keyword`, `--url`, `--fetch`, `--min-score`, `--json`; reads a file, `-` for stdin, or a URL with `--fetch`).
- [references/scoring.md](references/scoring.md) - check weights, thresholds and the reasoning behind them.
