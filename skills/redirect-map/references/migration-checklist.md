# Site migration checklist

## Before launch

- [ ] Benchmark: export Search Console performance (pages and queries, 16 months), analytics landing pages, and top linked pages from a backlink tool.
- [ ] Build the old URL inventory from every source (sitemaps, crawl, Search Console, analytics, backlinks, paid campaign URLs, URLs printed offline).
- [ ] Build the new URL inventory from the staging sitemap or crawl.
- [ ] Generate and review the redirect map (`scripts/redirect_map.py`); every URL with traffic or links has a decision.
- [ ] One hop only: old URL -> final new URL. Update older redirect rules that now point at moved URLs.
- [ ] Staging is protected (auth) and not indexable; the production build has no staging `noindex` or `Disallow: /`.
- [ ] Canonicals, hreflang, internal links, navigation, sitemaps and structured data use the new URLs.
- [ ] Titles, meta descriptions, headings and body content of top pages carried over (or improved on purpose).
- [ ] Analytics and tag manager installed on the new site; conversions still tracked.
- [ ] Test a sample of redirects on staging with the real server config.

## Launch day

- [ ] Deploy redirects together with the new site.
- [ ] Spot-check top 50 old URLs: `curl -sI <old-url>` shows `301` and the right `Location`, followed by `200`.
- [ ] Submit the new sitemap in Search Console; keep the old sitemap submitted for a few weeks so Google recrawls old URLs and sees the redirects.
- [ ] Domain change: use Search Console's Change of Address tool after redirects are live.

## After launch (weeks 1-8)

- [ ] Crawl the full old URL list against production; fix every 404 and chain.
- [ ] Watch Search Console: Pages report (404s, "Page with redirect"), crawl stats, performance by page.
- [ ] Compare traffic of top pages against the benchmark; investigate pages that lost more than expected.
- [ ] Update important external links (profiles, partners, ads) to the new URLs.
- [ ] Keep redirects for at least one year; ideally forever.

## Server snippets

nginx (map in `http {}`, check in `server {}`):

```nginx
map $uri $redirect_target {
    default "";
    "/old-page.html" "/new-page/";
}
server {
    if ($redirect_target) { return 301 $redirect_target; }
}
```

For very large maps, raise `map_hash_bucket_size` / `map_hash_max_size` if nginx refuses to start.

Apache (`.htaccess` or vhost):

```apache
RedirectMatch 301 ^/old-page\.html$ /new-page/
# Query-string based URLs need mod_rewrite:
RewriteEngine On
RewriteCond %{QUERY_STRING} (^|&)p=123(&|$)
RewriteRule ^$ /new-page/? [R=301,L]
```

Netlify / Cloudflare Pages (`_redirects` in the publish directory):

```
/old-page.html /new-page/ 301
```

Vercel (`vercel.json`):

```json
{ "redirects": [{ "source": "/old-page.html", "destination": "/new-page/", "permanent": true }] }
```

Note: Vercel's `permanent: true` sends 308, which Google treats like 301.
