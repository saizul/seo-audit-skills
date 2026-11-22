---
name: redirect-map
description: Build a 301 redirect map for a site migration, redesign, CMS or URL-structure change by matching old URLs to new URLs (exact, slug, fuzzy and parent-directory matching with confidence scores and review flags), then export ready-to-deploy rules for nginx, Apache, Netlify, Cloudflare Pages, Vercel or Cloudflare Bulk Redirects and check for chains and loops. Use when the user is migrating or relaunching a site, changing permalinks or domains, merging content, or asks for a redirect plan, redirect map or .htaccess/nginx redirects.
license: MIT
---

# Redirect map

Make sure every old URL that has traffic, links or rankings lands on its best
new equivalent with a single 301, and that nothing important is left to 404.

Paths below are relative to this skill's directory.

## When to use

- Site migration, redesign, platform move (WordPress -> headless, Shopify, Webflow...), domain or HTTPS change
- Changing permalink structure, merging or pruning content
- "Write redirects for these URLs", "generate .htaccess / nginx redirects"

## When not to use

- Checking an existing site's redirect chains from a crawl: `technical-seo-audit csv`.
- A single redirect: just write the rule.

## Inputs to collect

1. **Old URL list** - the union of: old sitemap(s), a crawl of the old site, Search Console/analytics top landing pages (last 12-16 months), and pages with backlinks. Missing sources are the main cause of lost traffic after a migration.
2. **New URL list** - the new sitemap or a crawl of staging.
3. The server or platform that will serve redirects (nginx, Apache, Netlify, Cloudflare Pages, Vercel, CMS plugin).

## Workflow

1. **Generate the report:**
   `python3 scripts/redirect_map.py old-urls.txt new-urls.csv > redirect-report.csv`
   Files can be plain lists or CSV exports (`url`/`address` column or the first column). The summary on stderr counts each method and the rows needing review.
2. **Review in this order:**
   - `none` rows: decide per URL - map manually, restore the content, or let it 404/410 if it has no traffic, links or equivalent.
   - `parent` rows (confidence 0.3): accept only when the parent truly covers the old page's topic; otherwise map to a specific page or 410.
   - `fuzzy` rows with `review=yes`, especially those with a "close alternative" note.
   - Rows noting "target is also an old URL": fix chains so every source points to the final URL.
   Sort by traffic/links first if the user has that data; the top 20% of URLs carry most of the value.
3. **Encode decisions** by editing the CSV (or ask the user to), then export rules from a final two-column list, or export directly when the automatic matches are good enough:
   `python3 scripts/redirect_map.py old.txt new.csv --format nginx --min-confidence 0.7 -o redirects.conf`
   Formats: `nginx` (map block for `$uri`), `apache` (anchored `RedirectMatch 301`), `netlify` (`_redirects`, also used by Cloudflare Pages), `vercel` (`{"redirects": [...]}` to merge into `vercel.json`; path-to-regexp characters are escaped), `cloudflare-bulk` (headerless CSV to upload to a Bulk Redirects list; sources are `host/path`, targets absolute; pass `--host www.example.com` when the URL lists are relative paths), `csv`, `json`. Add `--absolute-targets` for cross-domain moves.
4. **Check before launch:** no chains or loops, no redirects to 404s, internal links and canonicals updated to the new URLs, the new sitemap lists only new URLs. Use `--fail-on-unmatched` in CI to block a launch while rows still need review.
5. **After launch:** crawl the old URL list against production (`technical-seo-audit csv` on the crawl export) and watch Search Console for 404 spikes for several weeks. Keep redirects in place for at least a year; permanently is better.

## Decision points

- **301 vs 410.** Redirect only to a genuinely equivalent or closely related page. Redirecting everything to the homepage is treated as a soft 404 and wastes the signals; use 410 for content that is gone for good.
- **Query strings.** nginx `$uri` and Apache `RedirectMatch` ignore the query string; if old URLs differ only by parameters (`?p=123`), write those rules by hand on `$args` / `RewriteCond %{QUERY_STRING}`.
- **Case and trailing slashes.** Normalise site-wide with one rule (or platform setting) instead of thousands of per-URL rules. Netlify normalises trailing slashes before matching rules and Cloudflare Pages manages trailing slashes itself, so the `netlify` and `vercel` formats skip slash-only rules (they would loop).
- **Large maps.** nginx `map` handles tens of thousands of entries efficiently; Apache `RedirectMatch` lists slow down beyond a few thousand - use a `RewriteMap` instead.
- **Platform limits.** Some hosts cap the number of redirect rules (Netlify, Vercel, Cloudflare Pages have documented limits); check before deploying very large maps.

## Output

- `redirect-report.csv` with method, confidence, review flag and notes.
- The deployable rules file for the user's server.
- A short summary: counts by method, rows still needing a decision, chains found, and the launch checklist above.

## Files

- `scripts/redirect_map.py` - matcher and exporter (`--format`, `--threshold`, `--review-margin`, `--min-confidence`, `--absolute-targets`, `--fail-on-unmatched`, `-o`).
- [references/migration-checklist.md](references/migration-checklist.md) - full pre- and post-launch migration checklist and server snippets.
