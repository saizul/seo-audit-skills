# From Lighthouse audit to fix

Audit IDs as they appear in Lighthouse JSON. Newer Lighthouse versions report many
of these as "insights" (IDs ending in `-insight`); the fix is the same.

## LCP (Largest Contentful Paint)

| Audit / insight | Typical cause | Fix |
| --- | --- | --- |
| `server-response-time`, `document-latency-insight` | slow backend, no HTML caching, cold serverless starts | cache HTML at the CDN/edge, cache DB queries, static or ISR rendering, keep functions warm, avoid redirects to the document |
| `redirects` | `http -> https -> www -> /path/` hops | link and canonicalise to the final URL; one server-side hop at most |
| `render-blocking-resources`, `render-blocking-insight` | large CSS, synchronous `<script>` in `<head>` | inline critical CSS, load the rest with `media` swap or split per route; `defer`/`async` scripts |
| `lcp-discovery-insight`, `prioritize-lcp-image` | LCP image set via CSS background or JS, or not in the initial HTML | put the image in the HTML as `<img>`; add `fetchpriority="high"`; `<link rel="preload" as="image">` for CSS backgrounds |
| `lcp-lazy-loaded` | `loading="lazy"` on the hero image | remove lazy loading from above-the-fold images (framework image components often default to lazy: set `priority` / `loading="eager"`) |
| `lcp-breakdown-insight` / `lcp-phases-insight` | shows which phase is slow | TTFB -> server; load delay -> discovery; load time -> image weight; render delay -> blocking JS/CSS or client rendering |
| `uses-responsive-images`, `image-delivery-insight`, `modern-image-formats`, `uses-optimized-images` | oversized or unoptimised images | `srcset`/`sizes`, AVIF/WebP, compress, serve from an image CDN |
| `uses-rel-preconnect` | late connection to a CDN or font host | `<link rel="preconnect" href="https://cdn.example.com" crossorigin>` for 1-3 critical origins |
| `unused-css-rules`, `uses-text-compression`, `total-byte-weight` | heavy payloads | purge unused CSS, enable Brotli/gzip, trim bundles |
| `uses-long-cache-ttl`, `cache-insight` | short cache lifetimes on static assets | fingerprinted filenames + `Cache-Control: public, max-age=31536000, immutable` |

Client-side rendered pages: the LCP element only exists after JavaScript runs.
Server-render or pre-render the above-the-fold content.

## INP (Interaction to Next Paint) and TBT

| Audit / insight | Typical cause | Fix |
| --- | --- | --- |
| `unused-javascript`, `legacy-javascript(-insight)`, `duplicated-javascript(-insight)` | large bundles, polyfills for old browsers, duplicate libraries | code-split by route, dynamic `import()` for below-the-fold widgets, modern build targets, dedupe dependencies |
| `bootup-time`, `mainthread-work-breakdown`, `long-tasks` | heavy script evaluation and hydration | reduce hydration (islands, server components), defer non-critical work, break long tasks with `scheduler.yield()` / `setTimeout` |
| `third-party-summary`, `third-parties-insight` | tag managers, chat widgets, A/B testing, ads | remove unused tags, load on interaction or after `load`, use facades for embeds (YouTube, maps, chat) |
| `dom-size`, `dom-size-insight` | very large DOM (>1,500 nodes) | paginate or virtualise long lists, simplify markup |
| `forced-reflow-insight` | reading layout (`offsetHeight`) right after writing styles | batch reads before writes, use `requestAnimationFrame` |
| `inp-breakdown-insight` | input delay, processing time or presentation delay | input delay -> main thread busy (see above); processing -> optimise handler; presentation -> smaller DOM updates, `content-visibility` |

## CLS (Cumulative Layout Shift)

| Audit / insight | Typical cause | Fix |
| --- | --- | --- |
| `unsized-images` | `<img>`/`<video>`/`<iframe>` without width and height | set `width` and `height` attributes (or CSS `aspect-ratio`) |
| `layout-shifts`, `layout-shift-elements`, `cls-culprits-insight` | late banners, ads, embeds, injected content | reserve space with `min-height`; insert below the viewport; use transforms for animations |
| `font-display(-insight)` | font swap changes text size | `font-display: optional` or `swap` with a size-adjusted fallback (`size-adjust`, `ascent-override`) and preload the main font |
| `non-composited-animations` | animating `top`/`left`/`width` | animate `transform` and `opacity` only |

## Framework notes

- **Next.js:** `next/image` with `priority` on the LCP image; `next/font` for fonts; `next/script` with `strategy="lazyOnload"` for third parties; prefer Server Components to cut hydration.
- **Nuxt:** `<NuxtImg preload>`; `@nuxtjs/fontaine` for fallback font metrics; lazy components (`<LazyMyWidget>`).
- **Astro:** islands with `client:visible`/`client:idle`; `<Image>` with `loading="eager"` and `fetchpriority="high"` on the hero.
- **WordPress:** core adds `loading="lazy"` to images and tries to skip the first content image; themes and page builders often defeat that, so check the hero image in the rendered HTML. Remove unused plugins' assets per page, use page caching and an image CDN.
- **Shopify:** fewer apps (each injects scripts), `image_url` with `width` + `srcset`, preload the hero in `theme.liquid`.

## Measuring

- Lab: run Lighthouse 3-5 times and compare medians; use the same device preset.
- Field: CrUX/PSI p75 over 28 days; Search Console groups similar URLs.
- In production: the `web-vitals` JavaScript library sends real-user LCP/INP/CLS to analytics, with attribution builds naming the culprit element.
