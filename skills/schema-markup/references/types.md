# Property rules by type

What `scripts/validate_jsonld.py` enforces. "Required" items are errors when
missing; "recommended" are warnings (checked on top-level entities, and on
nested `Offer`, `AggregateOffer`, `PostalAddress`, `Review` and `Event`).
`a | b` means either property satisfies the rule.

These follow Google Search Central's structured data documentation. Google
changes rich-result eligibility over time - check the current docs for the type
before promising a rich result.

| Type | Required | Recommended | Notes |
| --- | --- | --- | --- |
| Article, NewsArticle, BlogPosting, TechArticle | - | headline, image, datePublished, dateModified, author | Google lists no required properties; author should be a Person/Organization object |
| Product | name; offers \| review \| aggregateRating | image, description, sku \| gtin* \| mpn, brand | Merchant listings need offers with price; product snippets accept review/rating instead |
| Offer | price \| priceSpecification; priceCurrency \| priceSpecification | availability, url, priceValidUntil, itemCondition | price numeric, currency ISO 4217 |
| AggregateOffer | lowPrice, priceCurrency | highPrice, offerCount | for several sellers/variants |
| AggregateRating | ratingValue; ratingCount \| reviewCount | - | ratingValue within worstRating..bestRating (default 1..5); needs itemReviewed when standalone |
| Review | author, reviewRating | datePublished | needs itemReviewed when standalone; no self-serving reviews on your own LocalBusiness/Organization |
| Rating | ratingValue | bestRating, worstRating | |
| FAQPage | mainEntity (Question items) | - | FAQ rich results shown only for well-known government and health sites since August 2023 |
| Question | name; acceptedAnswer \| suggestedAnswer | - | |
| Answer | text | - | |
| LocalBusiness (+ subtypes) | name, address | telephone, url, openingHoursSpecification \| openingHours, geo, image, priceRange | use the most specific subtype |
| PostalAddress | - | streetAddress, addressLocality, postalCode, addressCountry | addressCountry as ISO 3166-1 alpha-2 |
| GeoCoordinates | latitude, longitude | - | at least 5 decimal places |
| Organization (+ subtypes) | name | url, logo, sameAs | logo at least 112x112 px, crawlable |
| Person | name | url \| sameAs | |
| WebSite | name, url | alternateName | used for site names in results; homepage only |
| BreadcrumbList | itemListElement | - | positions 1..n; each ListItem needs name and item (except the last) |
| Event | name, startDate, location | endDate, eventStatus, eventAttendanceMode, image, description, offers, organizer, performer | online events need VirtualLocation; Place needs address |
| VideoObject | name, thumbnailUrl, uploadDate | description, contentUrl \| embedUrl, duration | duration ISO 8601 (PT1M33S) |
| ImageObject | contentUrl \| url | - | |
| HowTo | name, step | - | rich result retired in 2023 |

## Format checks (all types)

| Check | Applies to | Severity |
| --- | --- | --- |
| ISO 8601 date/datetime | datePublished, dateModified, dateCreated, uploadDate, startDate, endDate, validFrom, validThrough, priceValidUntil | error |
| Absolute http(s) URL | url, logo, thumbnailUrl, contentUrl, embedUrl, sameAs, item, image, mainEntityOfPage | warning |
| Numeric | price, lowPrice, highPrice, ratingValue, bestRating, worstRating, ratingCount, reviewCount, latitude, longitude, position | error |
| ISO 4217 currency | priceCurrency | error |
| schema.org ItemAvailability | availability | error (unknown value), warning (short form) |
| `@context` contains schema.org | every top-level object | error |
| Valid JSON | every block | error |

## Choosing between similar types

- **Article vs BlogPosting vs NewsArticle:** all work for Article rich results. Use NewsArticle for news publishers, BlogPosting for blogs, Article otherwise.
- **Organization vs LocalBusiness:** a business customers visit (or that serves an area) is a LocalBusiness subtype; a brand, publisher or online-only company is an Organization (or OnlineStore/OnlineBusiness).
- **Product on category pages:** do not mark every product on a listing page as the main entity; use an `ItemList` of URLs, or mark up products only on their own pages.
- **FAQPage vs QAPage:** FAQPage is for questions answered by the site owner; QAPage is for one user question with community answers.

## Policy reminders

- Markup must describe content visible to users on that page.
- No ratings or reviews you collected about your own business on that business's own pages (self-serving reviews are not eligible).
- One page can carry several types, but each should describe something on the page.
- Structured data never guarantees a rich result.
