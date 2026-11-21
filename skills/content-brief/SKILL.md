---
name: content-brief
description: Build an SEO content brief for a new or refreshed page - classify keyword intent, cluster keywords into one-page topics, analyse saved top-ranking competitor pages for shared subtopics, entities, questions and length, find gaps in an existing draft, and produce an outline with title options, FAQ and internal links ready for a writer. Use when the user asks for a content brief, article outline, keyword clustering or intent analysis, "what should this page cover", or a plan to refresh a page that lost rankings.
license: MIT
---

# Content brief

Turn a keyword (or keyword list) into a brief a writer can execute: the intent,
the angle, the outline, the entities and questions to cover, and how the page
fits into the site.

Paths below are relative to this skill's directory.

## When to use

- "Write a content brief / outline for <keyword>"
- "Group these keywords into pages", "what is the intent of these keywords"
- Refreshing a page that dropped: compare it against what ranks now

## When not to use

- Writing the full article without research: you can, but do the brief first.
- Auditing tags of an existing page: `on-page-seo-review`.
- Live keyword volumes or rankings: these scripts do not call SEO APIs. Use the user's exports (Search Console, Ahrefs, Semrush, Keyword Planner CSV).

## Inputs to collect

1. Primary keyword, audience, and the business goal of the page (sign-ups, sales, leads, awareness).
2. Optional keyword list (CSV with `keyword,volume` or one per line) - Search Console queries are ideal.
3. 3-5 saved top-ranking pages for the primary keyword (HTML files). If the user cannot provide them and asks you to, you may fetch the result URLs they give you; never scrape search results pages.
4. The existing page or draft (for refreshes), and a list of related site URLs for internal links.

## Workflow

1. **Intent and clusters:**
   `python3 scripts/keyword_intent.py keywords.csv --brand "<brand>" --json`
   Each cluster is one page candidate. Low-confidence rows need a look at what ranks: if results are product pages, a blog post will not rank, whatever the rules say.
2. **Competitor analysis:**
   `python3 scripts/competitor_outline.py rank1.html rank2.html rank3.html --ours draft.html --json`
   Use `common_subtopics` (covered by 2+ ranking pages) as the must-cover list, `common_terms` as the entity/vocabulary list, `questions` for the FAQ, `median_word_count` as a sanity range (not a target), and `ours.missing_*` for refresh gaps.
3. **Choose the angle.** Decide what this page adds that the ranking pages lack: first-hand testing, original data, a tool, a better structure, a clearer answer for a specific audience. A brief without an angle produces a copy of what already ranks.
4. **Write the brief** with [assets/brief-template.md](assets/brief-template.md). Order H2s to follow the reader's questions; put the direct answer near the top for informational queries.
5. **Plan internal links:** 3-5 links out to related pages and 2-3 existing pages that should link in (with suggested anchors).
6. **Sanity-check:** one primary intent per page; no cannibalisation with an existing URL (if one exists, refresh it instead); all claims that need sources are marked.

Intent rules, page-type mapping and E-E-A-T guidance: [references/intent-and-structure.md](references/intent-and-structure.md).

## Output

The completed brief from `assets/brief-template.md`, plus:

- the keyword cluster table (keyword, volume, intent) for this page
- a list of keywords you moved to other pages, and why
- what you could not verify (volumes, live results) and assumptions made

## Files

- `scripts/keyword_intent.py` - rule-based intent classification and same-intent clustering (`--brand`, `--threshold`, `--kw`, `--json`).
- `scripts/competitor_outline.py` - outlines, shared subtopics, terms (1-3 word phrases), questions and gaps from saved HTML (`--ours`, `--min-docs`, `--top`, `--json`).
- `assets/brief-template.md` - the brief format.
- [references/intent-and-structure.md](references/intent-and-structure.md) - intent signals, page types, outline patterns, E-E-A-T checklist.
