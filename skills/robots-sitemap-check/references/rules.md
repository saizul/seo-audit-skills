# robots.txt and sitemap rules

## robots.txt (RFC 9309 plus Google's documented behaviour)

**Location.** Only `/robots.txt` at the root of each host and protocol counts
(`https://example.com/robots.txt` does not cover `https://shop.example.com/` or
`http://example.com/`).

**Status codes.** 2xx: rules apply. 4xx (except 429): treated as "no
restrictions". 5xx and 429: Google treats the site as fully disallowed for a
while, then falls back to a cached copy; a long outage of robots.txt hurts crawling.

**Size.** Google reads the first 500 KiB; rules after that are ignored.

**Groups.** A group starts with one or more `User-agent` lines followed by rules.
A crawler uses the single most specific group whose token matches its name
(case-insensitive); all groups for that same token are merged. If no group
matches, it uses `User-agent: *`. A specific group fully replaces `*` - rules are
not inherited. Google's specialised crawlers (for example `Googlebot-Image`) fall
back to the `Googlebot` group when they have no group of their own.

**Rules.** `Allow` and `Disallow` take a path that starts with `/`. Matching is
against the path plus query string, case-sensitive.

- `*` matches any sequence of characters; `$` anchors the end of the URL.
- The longest matching pattern wins. On a tie, `Allow` wins.
- An empty `Disallow:` means nothing is disallowed.
- `/robots.txt` itself is always allowed.

| Pattern | Matches | Does not match |
| --- | --- | --- |
| `/fish` | `/fish`, `/fish.html`, `/fishheads/x`, `/fish?id=1` | `/Fish`, `/catfish` |
| `/fish/` | `/fish/`, `/fish/salmon` | `/fish`, `/fish.html` |
| `/*.php` | `/index.php`, `/a/b.php?x=1` | `/` |
| `/*.php$` | `/index.php` | `/index.php?x=1` |
| `/*?sort=` | `/list?sort=asc` | `/list?page=2&sort=asc` (needs `/*sort=`) |

**Other directives.** `Sitemap:` (absolute URL, may appear anywhere, applies to
all agents). Google ignores `Crawl-delay`, `Host`, `Clean-param`, `Noindex`,
`Nofollow` and `Noarchive`; other crawlers may honour some of them.

### Checks in `robots_check.py`

| Check | Severity | Why |
| --- | --- | --- |
| Larger than 500 KiB | error | rules beyond the limit are silently ignored |
| Line without `:` | error | not a directive; usually a broken edit |
| Allow/Disallow before any User-agent | error | belongs to no group, ignored |
| `User-agent: *` + `Disallow: /` with no Allow | error | blocks the whole site |
| Sitemap URL not absolute | error | the protocol requires a full URL |
| Pattern not starting with `/` or `*` | warning | Google prefixes `/`; usually a mistake |
| Disallow on .css/.js or asset folders | warning | blocks rendering resources |
| Named group drops `*` Disallow rules | warning | a `Googlebot` (or any named) group replaces `*`, so those paths become crawlable for it; skipped when `*` is `Disallow: /` (bot allow-listing) |
| Misspelt `useragent` / `disalow` | warning | tolerated by Google, not by every crawler |
| Unknown directive | warning | probably a typo |
| Directive ignored by Google | notice | it has no effect on Google |
| No Sitemap line, no groups | notice | missed discovery hint / allow-all file |

## XML sitemaps (sitemaps.org protocol plus Google guidance)

- Root `<urlset>` or `<sitemapindex>` in namespace `http://www.sitemaps.org/schemas/sitemap/0.9`, UTF-8.
- At most 50,000 URLs and 50 MB (52,428,800 bytes) uncompressed per file; gzip is allowed.
- `<loc>` is required, absolute, at most 2,048 characters, entity-escaped (`&amp;`), and on the same host and protocol as the sitemap (unless cross-submitted via Search Console or robots.txt).
- `<lastmod>` uses W3C Datetime: `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, or `YYYY-MM-DDThh:mm[:ss[.s]]TZD`. Google uses it only if it is consistently accurate.
- `<changefreq>` and `<priority>` are ignored by Google.
- Sitemap indexes may list up to 50,000 sitemaps; indexes cannot nest.
- hreflang may be given with `<xhtml:link rel="alternate" hreflang="..." href="...">` children (namespace `http://www.w3.org/1999/xhtml`).

### Checks in `sitemap_check.py`

| Check | Severity |
| --- | --- |
| Not well-formed XML, DOCTYPE present, wrong root or namespace | error |
| More than 50,000 entries or 50 MB uncompressed | error |
| `<loc>` missing, relative, > 2,048 chars, contains whitespace | error |
| URL on another host/scheme than `--base-url`, or several hosts | error |
| `<lastmod>` not W3C Datetime | error |
| `<priority>` outside 0.0-1.0 | error |
| Malformed `xhtml:link` | error |
| URL blocked by `--robots` for `--user-agent` | error |
| URL in `--exclude-list` | error |
| `<lastmod>` in the future, all `<lastmod>` identical | warning |
| Duplicate `<loc>`, `#fragment`, tracking parameters, mixed schemes | warning |
| No `<lastmod>` at all, `<changefreq>`/`<priority>` used | notice |
