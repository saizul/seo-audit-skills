# hreflang rules

## Code format

`language[-Script][-REGION]` or `x-default`.

- **language:** ISO 639-1, two letters (`en`, `de`, `ja`, `zh`). The script warns
  on three-letter codes because Google asks for ISO 639-1 where one exists.
- **Script (optional):** ISO 15924, four letters (`Hans`, `Hant`, `Latn`, `Cyrl`).
- **REGION (optional):** ISO 3166-1 alpha-2 (`GB`, `US`, `BR`, `TW`). UN M.49
  numeric regions such as `419` are not supported by Google.
- Hyphen separator, case-insensitive.

| Wrong | Right | Why |
| --- | --- | --- |
| `en-UK` | `en-GB` | UK is not an ISO 3166-1 code |
| `jp`, `cn`, `cz`, `dk`, `gr`, `ua`, `vn` | `ja`, `zh`, `cs`, `da`, `el`, `uk`, `vi` | country codes used as languages |
| `GB`, `US` | `en-GB`, `en-US` | a region alone is not valid |
| `en_US` | `en-US` | underscore |
| `es-419` | `es-MX`, `es-AR`, ... or plain `es` | numeric regions unsupported |
| `kr`, `se`, `br`, `si`, `my`, `ee` | usually `ko`, `sv`, `pt-BR`, `sl`, `ms`, `et` | valid but rare languages (Kanuri, Sami, Breton, Sinhala, Burmese, Ewe) - the script warns |
| `iw`, `in`, `ji` | `he`, `id`, `yi` | withdrawn ISO codes |

## The rules Google applies

1. **Absolute URLs** with protocol in every `href`.
2. **Self-reference:** each page lists itself.
3. **Return links:** if A lists B, B must list A. Without the return link Google may ignore the pair.
4. **One URL per code** within a page.
5. **Canonical targets only:** every `href` is the canonical URL of an indexable page that returns 200.
6. **Same set everywhere:** every page in the cluster carries the same list.
7. **x-default** for the fallback (optional, recommended).
8. **One method** per page: HTML `<link>`, HTTP `Link:` header, or sitemap `xhtml:link`. All three are equivalent.

## Implementation methods

HTML head:

```html
<link rel="alternate" hreflang="en" href="https://example.com/page/" />
<link rel="alternate" hreflang="de" href="https://example.com/de/seite/" />
<link rel="alternate" hreflang="x-default" href="https://example.com/page/" />
```

HTTP header (non-HTML files):

```
Link: <https://example.com/file.pdf>; rel="alternate"; hreflang="en", <https://example.com/de/file.pdf>; rel="alternate"; hreflang="de"
```

Sitemap:

```xml
<url>
  <loc>https://example.com/page/</loc>
  <xhtml:link rel="alternate" hreflang="en" href="https://example.com/page/"/>
  <xhtml:link rel="alternate" hreflang="de" href="https://example.com/de/seite/"/>
</url>
```

(The `urlset` element needs `xmlns:xhtml="http://www.w3.org/1999/xhtml"`, and
every language URL needs its own `<url>` entry with the full set.)

## Framework notes

- **Next.js App Router:** `export const metadata = { alternates: { canonical: url, languages: { en: enUrl, de: deUrl, "x-default": enUrl } } }`. Build the `languages` map from one locale table so every page emits the same set.
- **Nuxt i18n:** `useLocaleHead()` emits alternates; set `baseUrl` so URLs are absolute.
- **Astro:** `@astrojs/sitemap` with the `i18n` option writes sitemap alternates; or render `<link>` tags from `Astro.currentLocale` and a locale map.
- **Hugo:** loop `.AllTranslations` in the head partial and use `.Permalink` (absolute).
- **WordPress:** WPML and Polylang output hreflang; check that untranslated posts are not linked to fallback pages and that the language-switcher URLs are canonical.
- **Shopify Markets:** hreflang is automatic per market; check for `en` vs `en-XX` duplication when several English markets exist.

## What the script reports

| Issue | Severity |
| --- | --- |
| Invalid code, region-only code, underscore, unsupported region | error |
| Relative or empty `href` | error |
| Same code pointing to two URLs | error |
| Missing return link (target in the dataset does not link back) | error |
| Page with hreflang that canonicalises elsewhere | error |
| `href` target canonicalises elsewhere | error |
| Three-letter or suspicious language code | warning |
| No self-reference | warning |
| Target not in the dataset (missing page or not crawled) | warning |
| Cluster pages carry different annotation sets | warning |
| `<html lang>` disagrees with the page's own hreflang | warning |
| No x-default | notice |
