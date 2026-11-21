---
name: llms-txt
description: Create, update and validate an llms.txt file (the llmstxt.org proposal) that gives AI assistants and agents a curated Markdown map of a website or documentation - H1 name, blockquote summary, and H2 sections of annotated links, with an Optional section - built from a sitemap, a page list or a static HTML build. Use when the user asks for llms.txt, an AI-readable site index, "make my docs readable for LLMs/agents", or wants to check an existing llms.txt.
license: MIT
---

# llms.txt

Write a short, curated index that tells language models what the site is and
which pages matter, in the format proposed at llmstxt.org.

Paths below are relative to this skill's directory.

## When to use

- "Create an llms.txt for my site/docs", "update llms.txt after we added pages"
- Validating an existing `/llms.txt`
- Deciding which pages to expose to AI assistants and in what order

## When not to use

- Controlling AI crawler access: that is `robots.txt` (see `robots-sitemap-check`). llms.txt grants nothing and blocks nothing.
- Expecting a search ranking effect: llms.txt is a proposal for AI tools, not a Google ranking signal. Say so if the user assumes otherwise.

## Format (in order)

1. `# Name` - the only required part.
2. `> Summary` - one or two sentences on what the site/project is.
3. Optional free-form paragraphs or lists (no headings) with context: who it is for, how docs are organised, key terms.
4. `## Section` blocks, each a list of `- [Title](https://url): optional notes`.
5. `## Optional` - secondary links agents may skip when context is short.

Place it at `/llms.txt` (or `/docs/llms.txt` for a docs subtree). The proposal
also suggests offering clean Markdown versions of pages at the same URL plus
`.md` (or `index.md` for directory URLs); link those `.md` URLs when they exist.

## Workflow

1. **Collect inputs:** site name, one-sentence summary, the audience, and a page source - `sitemap.xml`, a CSV/JSON page list (`url,title,description,section`), or a built HTML directory.
2. **Generate a draft:**
   `python3 scripts/llms_txt.py build --name "Example" --summary "..." --sitemap sitemap.xml --section "Docs=/docs/" --section "API=/api/" --section "Blog=/blog/" --optional Blog -o llms.txt`
   - From HTML (uses `<title>` and meta descriptions, skips `noindex` pages): `--html-dir dist --base-url https://example.com`
   - Pagination, tag, author, feed, cart, login and query-string URLs are dropped by default (`--no-default-excludes` keeps them); add `--exclude REGEX` for more.
3. **Curate - this is the real work.** Cut it down to the pages an assistant needs to answer questions about the product: getting started, core concepts, API reference, pricing/limits, policies. Order sections from most to least important. Rewrite link notes as one plain sentence about what the page answers. Move changelogs, old posts and marketing pages to `## Optional` or drop them. Aim for tens of links, not thousands.
4. **Add context paragraphs** under the summary: product names, versions, terminology, what not to confuse it with.
5. **Validate:**
   `python3 scripts/llms_txt.py validate llms.txt --strict`
6. **Ship it** from the site's static root (`public/llms.txt`, `static/llms.txt`) or a route that renders it with `Content-Type: text/plain; charset=utf-8` (Markdown also works). Regenerate it in the build if pages change often.

## Output

- The final `llms.txt` content in a fenced `markdown` block (or written to the static folder if the user asked for a file).
- The validator result.
- A short note listing what you left out and why, and whether `.md` page versions exist.

## Files

- `scripts/llms_txt.py` - `build` (sitemap, CSV/JSON pages, or HTML dir; sections by path prefix; Optional section; default excludes) and `validate` (structure, link list syntax, absolute URLs, duplicates).
- [references/example.md](references/example.md) - a complete example and curation guidelines.
