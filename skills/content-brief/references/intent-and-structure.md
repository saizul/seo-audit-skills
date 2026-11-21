# Intent, page types and structure

## Intent signals used by `keyword_intent.py`

| Intent | Modifiers (examples) | Best page type |
| --- | --- | --- |
| informational | how, what, why, guide, tutorial, tips, examples, meaning, checklist, template, can/does/is | guide, how-to, glossary, FAQ |
| commercial | best, top, review(s), vs, compare, alternative(s), pros and cons, worth it | comparison, "best X" list, review |
| transactional | buy, price, pricing, cost, cheap, deal, coupon, discount, sale, shop, download, free trial, quote, booking | product, category, pricing page |
| local | near me, nearby, open now, directions, hours | location / service-area page |
| navigational | login, sign in, dashboard, official site, contact, customer service, a brand name alone | homepage, login, support |

Priority when several match: local > navigational > transactional > commercial >
informational. A brand plus a commercial or informational modifier ("acme vs
globex", "acme pricing") is not navigational. A bare head term with no modifier
("trail running shoes") is labelled commercial with low confidence: these
results are usually mixed (category pages, lists, guides), so check them.

**The results page is the ground truth.** If eight of ten results are category
pages, the intent is transactional regardless of the wording.

## Clustering

Keywords cluster when they share intent and most of their core terms (stop
words and modifiers removed, simple plural folding). One cluster = one page.
Split a cluster when the top results for two members are different pages; merge
clusters when the same URLs rank for both.

## Outline patterns

- **How-to:** answer/summary -> what you need -> steps (H2 per step or numbered list) -> common mistakes -> FAQ.
- **What is / explainer:** one-sentence definition -> why it matters -> how it works -> types/examples -> related concepts -> FAQ.
- **Best X / listicle:** who it is for and how you tested -> quick picks table -> one H2 per item (pros, cons, best for) -> how to choose -> FAQ.
- **X vs Y:** verdict up front -> comparison table -> section per decision factor -> who should pick which.
- **Product/category:** benefit headline -> key specs -> social proof -> details -> FAQ about shipping/returns/sizing.
- **Local page:** service + location in H1 -> NAP (name, address, phone) -> services -> area served -> reviews -> map and directions.

## E-E-A-T checklist (experience, expertise, authoritativeness, trust)

- Named author with relevant experience and an author page.
- First-hand evidence: original photos, test data, screenshots, case details.
- Cited primary sources for facts, numbers and health/finance/legal claims.
- Clear dates ("updated on") when freshness matters, and the content actually updated.
- Contact and about information reachable from the page.
- For YMYL topics (health, money, safety, legal): expert review noted on the page.

## Length

Use the median word count of ranking pages only as a sanity range. Cover every
must-have subtopic and question, then stop. Padding to hit a number lowers quality.
