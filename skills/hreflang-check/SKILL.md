---
name: hreflang-check
description: Audit and fix hreflang annotations for multilingual or multi-regional sites - validates language, script and region codes, absolute URLs, self-references, reciprocal return links, x-default, duplicate codes, canonical conflicts and html lang mismatches - from an HTML build, an XML sitemap with xhtml:link entries, or a CSV export, and generates correct annotation sets. Use when the user works on international SEO, translations or country sites, sees "no return tags" or wrong-language pages ranking, or asks to add or validate hreflang.
license: MIT
---

# hreflang check

Make every language/region version of a page point at all the others (and
itself) with valid codes, so search engines show the right version to each user.

Paths below are relative to this skill's directory.

## When to use

- Adding hreflang to a site with translations or country versions
- "Wrong country/language version ranks", "No return tags" or "Unknown language code" reports
- Reviewing i18n routing in Next.js, Nuxt, Astro, Hugo, WordPress (WPML/Polylang), Shopify Markets

## When not to use

- A single-language site: hreflang is unnecessary (an `<html lang>` attribute is enough).
- General canonical problems: `technical-seo-audit`.

## Workflow

1. **Find where hreflang is produced** - `<link rel="alternate" hreflang>` in the head template, `xhtml:link` entries in the sitemap generator, or HTTP `Link:` headers (for PDFs). Use one method per page set; mixing makes conflicts likely.
2. **Run the audit** on whatever you have:
   - Built HTML: `python3 scripts/hreflang_check.py --html-dir dist --base-url https://example.com [--clean-urls] --json`
   - Sitemap: `python3 scripts/hreflang_check.py --sitemap sitemap.xml --json`
   - Crawl export (one row per annotation): `python3 scripts/hreflang_check.py --csv hreflang.csv --json` with columns `url,hreflang,href`
   - Single codes: `python3 scripts/hreflang_check.py --code en-UK --code pt-BR`
3. **Fix in this order:** invalid codes -> relative or wrong URLs -> missing return links -> non-canonical targets -> missing self-references -> x-default -> html lang mismatches.
4. **Generate annotations from one shared mapping** (a locale table or the CMS translation links), so every page in a cluster emits the identical set. See [references/hreflang-rules.md](references/hreflang-rules.md) for code rules and framework notes.
5. Re-run until there are no errors; add the command to CI against the build output.

## Decision points

- **Language only vs language-region.** Use `en`, `de` when content differs by language only. Add a region (`en-GB`, `en-US`) only when content really differs (prices, spelling, legal). A region-only code like `GB` is invalid.
- **x-default.** Point it at the language selector or the global/fallback version. Recommended, not required.
- **Canonicals.** Each language version is self-canonical. Never canonicalise translations to one "main" language; that cancels hreflang.
- **Partial translations.** Only list versions that exist. Do not point a code at the homepage of that language as a fallback.
- **Codes are case-insensitive**, but write them conventionally: `en-GB`, `zh-Hant`, `pt-BR`.
- **Common wrong codes:** `en-UK` (use `en-GB`), `jp` (use `ja`), `cn` (use `zh`), `es-419` (Latin America is not supported by Google; list countries), underscores (`en_US`).

## Output

```
## hreflang audit - <site> (<pages> pages, <annotated> annotated)
| Severity | Page | Issue | Fix |

## Corrected annotation set (example cluster)
<link rel="alternate" hreflang="en" href="https://example.com/" />
<link rel="alternate" hreflang="de" href="https://example.com/de/" />
<link rel="alternate" hreflang="x-default" href="https://example.com/" />

## Code changes
<the template / sitemap config / locale mapping change>
```

## Files

- `scripts/hreflang_check.py` - offline audit (`--html-dir`, `--sitemap`, `--csv`, `--code`, `--strict`, `--json`).
- [references/hreflang-rules.md](references/hreflang-rules.md) - code format, implementation methods, framework notes.
