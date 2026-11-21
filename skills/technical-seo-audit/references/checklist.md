# Technical SEO checklist

Use this after running `scripts/site_audit.py`. Items marked (script) are covered
automatically; the rest need a manual look, the codebase, server config or
Search Console data.

## 1. Crawlability

- [ ] robots.txt returns 200 (a 5xx makes Google pause crawling; a 404 means "allow all").
- [ ] No `Disallow` on CSS, JS, images or API routes the page needs to render.
- [ ] robots.txt lists the XML sitemap(s) with absolute URLs.
- [ ] Internal links are real `<a href>` elements, not `onclick` handlers or `<span>`s. (script: only `<a href>` is counted)
- [ ] No internal links to 4xx/5xx URLs. (script: `broken-internal-link`, `client-error`, `server-error`)
- [ ] Important pages are within 3 clicks of the homepage. (script: `deep-page`)
- [ ] No orphan pages that matter. (script: `orphan-page`, `unreachable-from-home`)
- [ ] Faceted navigation and infinite calendars do not create unbounded crawlable URL spaces (block parameter patterns in robots.txt or avoid linking them).
- [ ] Pagination uses plain linked URLs (`?page=2` or `/page/2/`), each self-canonical; `rel=next/prev` is optional (Google no longer uses it).
- [ ] Server responds quickly and consistently (check crawl stats in Search Console: host status, average response time).

## 2. Indexability

- [ ] Pages meant to rank have no `noindex` in meta robots **or** the `X-Robots-Tag` header. (script: meta and, in csv mode, header)
- [ ] `noindex` pages are not blocked in robots.txt (Google must crawl them to see the directive).
- [ ] No soft 404s: empty search results, out-of-stock pages with no content, or "not found" pages returning 200.
- [ ] Error pages return real 404/410 status codes.
- [ ] Staging/preview hosts are password-protected or `noindex` and never linked from production.
- [ ] Rendered HTML (after JavaScript) contains the main content, title, canonical and links. Compare view-source with the rendered DOM (Search Console URL Inspection > View crawled page).

## 3. Canonicalisation

- [ ] Every indexable page has exactly one absolute, self-referencing canonical, or a canonical to its true primary. (script: `canonical-missing`, `canonical-multiple`, `canonical-relative`)
- [ ] Canonical targets return 200, are indexable and are not redirected. (script: `canonical-target-missing`, `canonical-to-redirect`, `canonical-to-error`, `canonical-to-noindex`)
- [ ] No canonical chains (A -> B -> C). (script: `canonical-chain`)
- [ ] One preferred host and protocol: `http://`, `www`/non-www and trailing-slash variants 301 to the preferred form. (script: `http-page-served`, `duplicate-url-variant`)
- [ ] Tracking and session parameters are not linked internally. (script: `tracking-parameter-url`)
- [ ] Canonical, internal links, sitemap URLs and hreflang all use the same preferred URL form.

## 4. Status codes and redirects

- [ ] Permanent moves use 301 or 308, not 302/307. (script: `temporary-redirect`)
- [ ] No redirect chains longer than one hop; no loops. (script: `redirect-chain`, `redirect-loop`)
- [ ] Redirect targets return 200. (script: `redirect-to-error`)
- [ ] Internal links point at final URLs, not at redirects.
- [ ] Old URLs from previous site versions still redirect (check backlinks and analytics landing pages; see the `redirect-map` skill).
- [ ] No meta-refresh or JavaScript redirects where a server redirect is possible.

## 5. Site architecture and internal links

- [ ] Hubs/category pages link to their children and children link back.
- [ ] Anchor text describes the target.
- [ ] Breadcrumbs reflect the hierarchy (and carry BreadcrumbList schema - see `schema-markup`).
- [ ] Unique, descriptive titles on indexable pages. (script: `title-missing`, `title-duplicate`)
- [ ] No `nofollow` on internal links or page-level `nofollow` on pages whose links matter. (script: `nofollow-page`)

## 6. Sitemaps

- [ ] Only canonical, indexable, 200-status URLs are listed (run `robots-sitemap-check`).
- [ ] `<lastmod>` reflects real content changes.
- [ ] Sitemaps are submitted in Search Console and processed without errors.

## 7. HTTPS and security

- [ ] Valid certificate on every host variant; HTTP 301s to HTTPS.
- [ ] No mixed content (HTTP images, scripts or iframes on HTTPS pages).
- [ ] HSTS header on the preferred host once HTTPS is stable.

## 8. Mobile and rendering

- [ ] `<meta name="viewport">` present; content parity between mobile and desktop (Google indexes the mobile version).
- [ ] Lazy-loaded content and links are present in the rendered HTML without scrolling or clicking.
- [ ] Interstitials do not cover the main content on load.

## 9. International (if applicable)

- [ ] hreflang is valid and reciprocal (run `hreflang-check`).
- [ ] Each language version is self-canonical (never canonicalise one language to another).

## 10. Monitoring

- [ ] Search Console "Pages" report: review "Not indexed" reasons monthly.
- [ ] Server logs: check that Googlebot hits important templates and is not stuck in parameter loops.
- [ ] Re-run `site_audit.py` in CI on the build output (`--fail-on error`) so regressions fail the build.

## Common root causes

| Symptom | Usual cause |
| --- | --- |
| Canonical points to the homepage on every page | Hard-coded canonical in the layout template |
| Canonical to `http://` or staging host | Site URL setting or env var wrong in production |
| Sitewide `noindex` after launch | "Discourage search engines" (WordPress) or a staging header left on |
| Thousands of parameter URLs crawled | Filter/sort links in navigation without crawl controls |
| Redirect chains | New redirect rules added on top of old ones instead of updating them |
| Orphaned blog posts | Pagination or "load more" implemented with JavaScript only |
