---
name: robots-sitemap-check
description: Lint robots.txt and XML sitemaps (including sitemap indexes and .xml.gz) from local files, test whether specific URLs are allowed or blocked for Googlebot or any crawler using Google's longest-match rules, and cross-check that sitemaps only list crawlable, indexable URLs. Use when the user asks to check, write or fix robots.txt or sitemap.xml, asks "is this URL blocked", sees "Blocked by robots.txt" or "Sitemap could not be read" in Search Console, or wants robots/sitemap checks in CI.
license: MIT
---

# robots.txt and sitemap check

Verify the two files that tell crawlers where to go, with the same matching rules
Google uses, and fix them at their source (static file, framework route, CMS setting).

Paths below are relative to this skill's directory.

## When to use

- Writing, reviewing or debugging `robots.txt`
- "Is /some/url blocked?" for Googlebot, Bingbot, GPTBot or any user-agent
- Validating `sitemap.xml`, a sitemap index, or a generated sitemap before deploy
- Search Console: "Blocked by robots.txt", "Indexed, though blocked by robots.txt", "Couldn't fetch", "Sitemap has errors"

## When not to use

- Whole-site crawl and canonical problems: `technical-seo-audit`.
- hreflang inside sitemaps in depth: `hreflang-check --sitemap`.
- Generating a sitemap from scratch: use the framework's generator (`next-sitemap`, `@astrojs/sitemap`, Hugo/Jekyll built-ins, Yoast/Rank Math); then validate here.

## Workflow

1. **Get the files.** Prefer the repository source (`public/robots.txt`, `static/robots.txt`, `app/robots.ts`, `app/sitemap.ts`) or the build output. If the user wants the live files, ask them to save them (`curl -o robots.txt https://example.com/robots.txt`) or fetch only with their go-ahead.
2. **Lint robots.txt:**
   `python3 scripts/robots_check.py robots.txt --json`
3. **Test the URLs that matter** (homepage, key templates, assets, anything the user asked about):
   `python3 scripts/robots_check.py robots.txt --user-agent Googlebot --test / --test /products/x --test /assets/app.css`
   For CI assertions: `--expect-allowed / --expect-blocked /cart/` (exit 1 if any expectation fails).
4. **Validate each sitemap** and cross-check with robots.txt and the production origin:
   `python3 scripts/sitemap_check.py sitemap.xml --base-url https://example.com --robots robots.txt --json`
   For an index, the child sitemaps are listed; validate each child file too. Use `--exclude-list urls.txt` with known noindex, redirected or canonicalised URLs to catch them in the sitemap.
5. **Fix at the source** and re-run until clean. Show the user a diff of the robots.txt or sitemap generator config.

## Decision points

- **Blocking vs noindex.** robots.txt controls crawling, not indexing. To remove pages from results, allow crawling and serve `noindex`, or return 404/410. Never block a URL you want de-indexed.
- **Specific groups replace `*`.** If a `User-agent: Googlebot` group exists, Googlebot ignores the `*` group entirely. Copy shared rules into every specific group.
- **Never block rendering resources.** CSS, JS, fonts and API endpoints the page needs must stay crawlable.
- **AI crawlers.** To opt out of AI training while staying in search, add groups for the relevant tokens (for example `GPTBot`, `Google-Extended`, `CCBot`, `ClaudeBot`) - confirm each vendor's current token in their docs before writing it.
- **Sitemap contents.** List only canonical, indexable URLs that return 200. Split at 50,000 URLs or 50 MB uncompressed. `<lastmod>` must be the real last significant change; `<priority>` and `<changefreq>` are ignored by Google.
- **Staging.** A staging `Disallow: /` must never ship to production; add `--expect-allowed /` to CI for the production build.

## Output

```
## robots.txt
Status: <OK | N errors, M warnings>
| Line | Severity | Issue | Fix |
URL tests:
| URL | User-agent | Verdict | Matched rule |

## Sitemaps
| File | Type | Entries | Errors | Warnings |
<issue list grouped by type, with example URLs>

## Changes
<diff of robots.txt / sitemap config>
```

## Files

- `scripts/robots_check.py` - robots.txt linter and URL tester (`--test`, `--expect-allowed`, `--expect-blocked`, `--user-agent`, `--strict`, `--json`).
- `scripts/sitemap_check.py` - sitemap/sitemap index validator (`--base-url`, `--robots`, `--exclude-list`, `--now`, `--strict`, `--json`; reads `.xml` and `.xml.gz`).
- [references/rules.md](references/rules.md) - matching rules, limits and the reasoning for each check.
