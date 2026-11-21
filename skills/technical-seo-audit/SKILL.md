---
name: technical-seo-audit
description: Run a technical SEO audit of a website - crawlability, indexability, canonicals, status codes, redirects, internal links, orphan pages and click depth - from a static build directory or a crawler CSV export, then produce a prioritised fix list. Use when the user asks for a technical SEO audit, site health check, "why is this page not indexed", crawl errors, canonical or redirect problems, or a pre-launch/post-migration SEO check.
license: MIT
---

# Technical SEO audit

Find the problems that stop search engines from crawling, indexing and
consolidating a site, and turn them into an ordered fix list. The bundled script
does the deterministic checks offline; you add judgement, context and priorities.

Paths below are relative to this skill's directory.

## When to use

- "Audit my site for technical SEO", "site health check", "pre-launch SEO check"
- Pages missing from Google, "Crawled - currently not indexed", "Duplicate without user-selected canonical"
- After a migration, redesign, CMS or framework change, or a domain/HTTPS move
- The user has a static build (`dist/`, `public/`, `_site/`, `out/`) or a crawl export (Screaming Frog, Sitebulb, a custom crawler)

## When not to use

- Scoring the copy and tags of one page: use `on-page-seo-review`.
- Only robots.txt or sitemaps: use `robots-sitemap-check`.
- Speed and Core Web Vitals: use `core-web-vitals-triage`.
- Multi-language annotations: use `hreflang-check`.

## Inputs to collect

1. The production origin (for example `https://example.com`) - needed to resolve links and canonicals.
2. One of:
   - a built HTML directory (run the project's build first, e.g. `npm run build`), or
   - a crawl CSV with at least URL and status columns (Screaming Frog "Internal: All" works as is).
3. If available: robots.txt, sitemap.xml, the Search Console "Pages" report export. Ask for them; do not crawl a live site unless the user explicitly asks and names the site.

## Workflow

1. **Run the deterministic audit.**
   - Build directory:
     `python3 scripts/site_audit.py html <build-dir> --base-url https://example.com [--clean-urls] --json`
     Use `--clean-urls` when `about.html` is served as `/about`.
   - Crawl export:
     `python3 scripts/site_audit.py csv crawl.csv --json`
   Exit code 1 means errors were found; that is expected, not a failure of the tool.
2. **Run the companion checks** when the files exist:
   - `python3 ../robots-sitemap-check/scripts/robots_check.py robots.txt`
   - `python3 ../robots-sitemap-check/scripts/sitemap_check.py sitemap.xml --robots robots.txt --base-url https://example.com`
3. **Read the code for causes, not just symptoms.** For each error class, find where it comes from (template, router, CMS setting, redirect config) so the fix is one change, not hundreds. Search the codebase for the canonical tag, the robots meta tag and redirect rules.
4. **Walk the checklist** in [references/checklist.md](references/checklist.md) for items the script cannot see (server headers, JavaScript rendering, pagination, faceted navigation, soft 404s, parameter handling).
5. **Prioritise** with the rubric below and write the report.

## Decision points

- **noindex vs canonical vs redirect.** Page should not exist: 301 to the closest equivalent, or 404/410. Duplicate that must stay reachable (filters, print views, tracking URLs): canonical to the primary. Page useful to users but not to search (internal search, thank-you pages): `noindex` and keep crawlable so the directive is seen. Never combine `noindex` with a canonical pointing elsewhere.
- **robots.txt is not an index control.** A blocked URL can still be indexed from links. To remove a URL from the index, allow crawling and serve `noindex` (or 404/410).
- **Orphans.** Valuable page: link it from a relevant hub and the sitemap. Leftover page: remove or redirect it.
- **Redirect chains.** Point every source straight to the final URL; update internal links to the final URL too.
- **JavaScript sites.** If links or canonicals only appear after rendering, audit the rendered HTML (prerender, SSR output or a headless crawl export) and flag reliance on client-side rendering.

## Prioritisation rubric

| Priority | Examples |
| --- | --- |
| P0 - blocks indexing site-wide | `Disallow: /` for all agents, sitewide `noindex`, canonical to wrong host, HTTPS pages redirecting to HTTP, 5xx on key templates |
| P1 - loses important pages or signals | 4xx on linked pages, canonical to missing/redirected/noindex URLs, redirect loops, orphaned money pages, conflicting canonicals |
| P2 - wastes crawl and dilutes signals | redirect chains, temporary redirects for permanent moves, duplicate titles, parameter and case duplicates, deep pages (>3 clicks) |
| P3 - hygiene | relative canonicals, uppercase URLs, missing canonicals on unique pages |

Weight by page value: a P2 issue on the top revenue template outranks a P1 on an old tag page.

## Output

Write the report in this shape (Markdown, in chat or as `SEO-AUDIT.md` if the user wants a file):

```
# Technical SEO audit - <site> - <date>
Scope: <input used, page count, what was not checked>

## Summary
<3-5 sentences: overall health, the one or two things that matter most>

## Fix list
| # | Priority | Issue | Affected (count + examples) | Cause | Fix | Effort |

## Details
<one subsection per issue: evidence (script output lines), why it matters, exact fix (code/config diff when you can see the code)>

## Not checked / next steps
<rendering, live headers, logs, Search Console data - whatever was out of scope>
```

Rules: quote real URLs and counts from the script output; never invent numbers;
group repeated findings by root cause; give the exact config or template change
when the codebase is available.

## Files

- `scripts/site_audit.py` - offline audit (`html` and `csv` modes, `--json`, `--fail-on`).
- [references/checklist.md](references/checklist.md) - full technical SEO checklist, including the manual checks.
