# Rendering JSON-LD in common stacks

Generate the object from the same data the page renders, serialise it once, and
output it in the server-rendered HTML (not only after client-side JavaScript).
Escape `<` so content cannot close the `<script>` tag.

## Next.js (App Router)

```tsx
// app/blog/[slug]/page.tsx
export default async function Post({ params }) {
  const post = await getPost(params.slug);
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    headline: post.title,
    datePublished: post.publishedAt,   // ISO 8601 with offset
    dateModified: post.updatedAt,
    image: [post.coverUrl],            // absolute URL
    author: { "@type": "Person", name: post.author.name, url: post.author.url },
  };
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }}
      />
      <article>...</article>
    </>
  );
}
```

## Astro

```astro
---
const jsonLd = { "@context": "https://schema.org", "@type": "Product", name: product.name, offers: { "@type": "Offer", price: product.price.toFixed(2), priceCurrency: "USD", availability: "https://schema.org/InStock" } };
---
<script type="application/ld+json" set:html={JSON.stringify(jsonLd).replace(/</g, "\\u003c")} />
```

## Hugo

```go-html-template
{{/* layouts/partials/schema-article.html */}}
{{ $ld := dict
  "@context" "https://schema.org"
  "@type" "BlogPosting"
  "headline" .Title
  "datePublished" (.PublishDate.Format "2006-01-02T15:04:05-07:00")
  "dateModified" (.Lastmod.Format "2006-01-02T15:04:05-07:00")
  "author" (dict "@type" "Person" "name" .Params.author)
}}
<script type="application/ld+json">{{ $ld | jsonify | safeJS }}</script>
```

## Jekyll / Liquid

```liquid
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  "headline": {{ page.title | jsonify }},
  "datePublished": {{ page.date | date_to_xmlschema | jsonify }},
  "author": { "@type": "Person", "name": {{ page.author | default: site.author | jsonify }} }
}
</script>
```

Always pass values through `jsonify`, never interpolate raw strings into JSON.

## WordPress

- If an SEO plugin (Yoast, Rank Math, SEOPress) already outputs a `@graph`, extend it with the plugin's filters instead of adding a second, conflicting block (for Yoast: `wpseo_schema_graph`; for Rank Math: `rank_math/json_ld`).
- Without a plugin:

```php
add_action('wp_head', function () {
    if (!is_singular('post')) return;
    $data = [
        '@context' => 'https://schema.org',
        '@type' => 'BlogPosting',
        'headline' => get_the_title(),
        'datePublished' => get_the_date('c'),
        'dateModified' => get_the_modified_date('c'),
        'author' => ['@type' => 'Person', 'name' => get_the_author()],
    ];
    echo '<script type="application/ld+json">' . wp_json_encode($data, JSON_UNESCAPED_SLASHES | JSON_HEX_TAG) . '</script>';
});
```

## Django / Jinja

```django
{{ schema|json_script:"page-schema" }}
```

`json_script` escapes safely but renders `<script id="page-schema" type="application/json">`; change the type with a small custom tag, or build the string with `json.dumps(schema).replace("<", "\\u003c")` and mark it safe.

## Checking the output

1. Build or render the page.
2. `python3 scripts/validate_jsonld.py path/to/rendered.html --strict`
3. Add that command to CI on a few representative built pages (one per template).
