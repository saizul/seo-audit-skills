---
name: schema-markup
description: Generate and validate schema.org JSON-LD structured data for Article/BlogPosting, Product and Offer, FAQPage, LocalBusiness, Organization, Person, BreadcrumbList, WebSite, Event and VideoObject - from page content or a template - and check it offline against Google rich-result required and recommended properties. Use when the user asks to add structured data, schema markup, JSON-LD or rich snippets, fix Search Console structured-data errors, or wire schema into a CMS or framework template.
license: MIT
---

# Schema markup (JSON-LD)

Write structured data that matches what is visible on the page, wire it into the
template that renders the page, and validate it before it ships.

Paths below are relative to this skill's directory.

## When to use

- "Add schema / structured data / JSON-LD to ..." for a page type or template
- Search Console reports "Missing field", "Invalid value", "Unparsable structured data"
- Choosing which schema type fits a page; reviewing existing markup

## When not to use

- Visible on-page problems (titles, headings): `on-page-seo-review`.
- Marking up content that is not on the page, fake reviews or self-serving ratings on your own organisation: refuse - this violates Google's structured data policies and can trigger a manual action.

## Workflow

1. **Pick the type from the page's main purpose** (one primary entity per page):

   | Page | Primary type | Usually also |
   | --- | --- | --- |
   | Blog post, news, guide | `BlogPosting` / `NewsArticle` / `Article` | `BreadcrumbList`, author `Person` |
   | Product detail | `Product` with `offers` | `AggregateRating`/`Review` only if shown on the page, `BreadcrumbList` |
   | Shop, office, clinic, restaurant | `LocalBusiness` subtype (`Store`, `Dentist`, `Restaurant`...) | `Organization` on the homepage |
   | Homepage | `Organization` + `WebSite` | - |
   | Author / team member | `Person` (or `ProfilePage` with `mainEntity` Person) | - |
   | FAQ section | `FAQPage` | (rich result limited to gov/health sites, still valid) |
   | Event, webinar | `Event` | `Offer` for tickets |
   | Video page | `VideoObject` | - |

2. **Start from a template** in `assets/templates/` (article, product, faqpage, localbusiness, organization, person, breadcrumblist, website). Replace every example value with real data from the page or the CMS fields. Delete properties you cannot fill truthfully rather than inventing values.
3. **Connect entities with `@id`.** Give the Organization `"@id": "https://example.com/#organization"` and reference it from `publisher`, `brand` or `worksFor` as `{"@id": "..."}`. Put several entities in one block with `@graph`.
4. **Wire it into the template**, generating values from the same data the page renders (title, price, dates, author). Patterns for Next.js, Astro, Hugo, Jekyll, WordPress and Django are in [references/implementation.md](references/implementation.md). Escape `<` as `<` when serialising user content into a `<script>` tag.
5. **Validate offline:**
   `python3 scripts/validate_jsonld.py built-page.html --json` (HTML: extracts every `application/ld+json` block)
   `python3 scripts/validate_jsonld.py snippet.json`
   Fix every `error`. Fix `warning`s when the data exists. Use `--strict` in CI.
   `python3 scripts/validate_jsonld.py --list-types` prints the rules.
6. **Final check:** tell the user to run the deployed URL through Google's Rich Results Test and the Schema Markup Validator; the offline validator does not know every Google rule or policy.

## Rules that cause most errors

- Dates are ISO 8601 with a timezone: `2026-01-15T08:00:00+00:00`.
- `price` is a number or numeric string (`"129.00"`), never `"$129"`; `priceCurrency` is ISO 4217 (`USD`).
- `availability` uses full URLs: `https://schema.org/InStock`.
- URLs (`url`, `image`, `logo`, `item`, `sameAs`) are absolute.
- `author` is a `Person`/`Organization` object with `name` (and ideally `url`), not a string.
- A `Review` or `AggregateRating` must sit inside the item it rates or name it in `itemReviewed`.
- BreadcrumbList positions run 1..n; every crumb except the last needs `item`.
- Values must match visible content. Do not mark up hidden text.

More per-type detail: [references/types.md](references/types.md).

## Output

- The JSON-LD (in a fenced `json` block or as a code change to the template).
- The validator result after your fix: `OK - no issues`, or the remaining warnings with a reason each is acceptable.
- Where the markup lives (file and component) and which data source fills each field.
- A one-line reminder to confirm with the Rich Results Test after deploy.

## Files

- `scripts/validate_jsonld.py` - offline validator (HTML or JSON input, `@graph`, nested entities, `--strict`, `--json`, `--list-types`).
- `assets/templates/*.json` - valid starting points for each core type.
- [references/types.md](references/types.md) - required/recommended properties per type and rich-result status.
- [references/implementation.md](references/implementation.md) - how to render JSON-LD in common frameworks and CMSs.
