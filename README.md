# SEO Audit Skills

[![CI](https://github.com/saizul/seo-audit-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/saizul/seo-audit-skills/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/saizul/seo-audit-skills?sort=semver)](https://github.com/saizul/seo-audit-skills/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/saizul/seo-audit-skills?style=social)](https://github.com/saizul/seo-audit-skills/stargazers)

**Nine Agent Skills that turn Claude Code or Codex into a careful technical and
content SEO engineer - with offline, tested scripts instead of guesswork.**

Each skill tells the agent exactly how to audit, decide and fix one SEO area, and
ships a deterministic Python script (standard library only, no API keys, no
network by default) that does the checking. The agent brings judgement; the
script brings reproducible numbers.

## Skills

| Skill | What it does | Try asking |
| --- | --- | --- |
| [technical-seo-audit](skills/technical-seo-audit/SKILL.md) | Crawlability, indexability, canonicals, status codes, redirect chains/loops, broken internal links, orphans and click depth from a build folder or crawl CSV | "Run a technical SEO audit on `dist/` for https://example.com" |
| [on-page-seo-review](skills/on-page-seo-review/SKILL.md) | 0-100 score for title, meta, H1/outline, canonical, alt text, links, word count, OG, schema and keyword placement, plus rewrites | "Review the SEO of `public/pricing/index.html` for 'invoice software'" |
| [schema-markup](skills/schema-markup/SKILL.md) | Generate JSON-LD (Article, Product, FAQPage, LocalBusiness, Organization, Person, BreadcrumbList, Event, VideoObject) and validate required/recommended properties | "Add Product schema to our product template and validate it" |
| [robots-sitemap-check](skills/robots-sitemap-check/SKILL.md) | Lint robots.txt, test URLs with Google's longest-match rules, validate sitemaps and sitemap indexes, cross-check blocked URLs | "Is /checkout/ blocked for Googlebot? Check our sitemap too" |
| [hreflang-check](skills/hreflang-check/SKILL.md) | Validate language/region codes, return links, self-references, x-default and canonical conflicts from HTML, sitemap or CSV | "Audit hreflang on the built site in `out/`" |
| [core-web-vitals-triage](skills/core-web-vitals-triage/SKILL.md) | Rate LCP/INP/CLS from Lighthouse, PageSpeed Insights or CrUX JSON and rank fixes by estimated impact | "Here's `lighthouse.json` - what should we fix first?" |
| [llms-txt](skills/llms-txt/SKILL.md) | Build and validate an llms.txt from a sitemap, page list or HTML build | "Create an llms.txt for our docs" |
| [content-brief](skills/content-brief/SKILL.md) | Keyword intent and clustering, competitor outline/term/question analysis, gap check and a writer-ready brief | "Write a content brief for 'trail running shoes' from these 3 saved pages" |
| [redirect-map](skills/redirect-map/SKILL.md) | Old-to-new URL matching (exact, slug, fuzzy, parent) with confidence and review flags; nginx, Apache, Netlify rules | "Map these old URLs to the new site and give me nginx redirects" |

## Install

### Claude Code (plugin marketplace)

```text
/plugin marketplace add saizul/seo-audit-skills
/plugin install seo-audit@seo-audit-skills
```

Or from your shell:

```sh
claude plugin marketplace add saizul/seo-audit-skills
claude plugin install seo-audit@seo-audit-skills
```

Skills from a plugin are namespaced, for example `/seo-audit:technical-seo-audit`.
Claude also picks them automatically when your request matches a skill's description.
Update later with `/plugin marketplace update seo-audit-skills`.

### Claude Code (manual copy)

Personal skills live in `~/.claude/skills/`, project skills in `.claude/skills/`:

```sh
git clone https://github.com/saizul/seo-audit-skills.git
cp -R seo-audit-skills/skills/* ~/.claude/skills/          # all projects
# or, inside a project (commit it to share with your team):
mkdir -p .claude/skills && cp -R seo-audit-skills/skills/schema-markup .claude/skills/
```

Each [release](https://github.com/saizul/seo-audit-skills/releases) also has one
zip per skill and an all-skills zip; unzip into the same folders.

### OpenAI Codex CLI

Codex loads skills from `~/.agents/skills/` (user) and `.agents/skills/` in your
repository ([Codex skills documentation](https://developers.openai.com/codex/skills)):

```sh
git clone https://github.com/saizul/seo-audit-skills.git
mkdir -p ~/.agents/skills
cp -R seo-audit-skills/skills/* ~/.agents/skills/
```

Restart Codex, then ask for the task in plain words or mention the skill by name
(`$technical-seo-audit`). See [AGENTS.md](AGENTS.md) for agent-specific notes.

### Other agents

The folders follow the open [Agent Skills specification](https://agentskills.io/specification),
so any agent that supports it can load them. Without skill support, point the
agent at a `SKILL.md` file and let it follow the steps.

## Usage examples

```text
> Run a technical SEO audit of our Astro build in dist/ (production is https://example.com)
```

The agent builds the site if needed, runs
`python3 scripts/site_audit.py html dist --base-url https://example.com --json`,
checks `robots.txt` and the sitemap with the companion skill, traces each error to
the template or config that causes it, and writes a prioritised fix list.

```text
> Our Search Console shows 'No return tags' for hreflang. Here's the sitemap.
> We're moving from WordPress to Next.js - here are both URL exports. Build the redirect map.
> PageSpeed says LCP is 4.8 s on mobile. Here's the PSI JSON. What do we change?
```

Every script also works on its own:

```sh
python3 skills/robots-sitemap-check/scripts/robots_check.py robots.txt --test /cart/ --user-agent Googlebot
python3 skills/schema-markup/scripts/validate_jsonld.py dist/products/shoe/index.html --strict
python3 skills/redirect-map/scripts/redirect_map.py old.txt new.txt --format nginx -o redirects.conf
```

Use them in CI: they exit `1` when they find problems (`--fail-on`, `--strict`,
`--min-score`, `--expect-allowed` control the threshold) and `2` on bad input.

## How skills work

A skill is a folder with a `SKILL.md`: YAML frontmatter (`name`, `description`)
and Markdown instructions. The agent loads only the name and description of every
installed skill at startup; when your request matches, it reads the full
`SKILL.md`, and opens `references/` or runs `scripts/` only when the workflow
calls for them. That keeps context small while the detailed rules stay available.

```text
skills/schema-markup/
├── SKILL.md                 # when to use, workflow, decision points, output format
├── scripts/validate_jsonld.py
├── references/types.md      # loaded on demand
└── assets/templates/*.json  # starting points the agent copies
```

## FAQ

**Do the scripts call Google or any SEO API?** No. They read files you provide
(HTML, XML, CSV, JSON). The only network code is `onpage_review.py --fetch`, which
makes one GET when you explicitly pass the flag.

**Do I need to install Python packages?** No. Python 3.9 or newer is enough.
`pytest` and `ruff` are only needed to develop the repo.

**Can this replace Screaming Frog, Lighthouse or Search Console?** No - it reads
their exports and makes them actionable. Use those tools to collect data, and
these skills to interpret and fix.

**Will the agent change my robots.txt or redirects on its own?** The skills tell
the agent to show diffs first because these changes can de-index a site. Review
them like any other code change.

**Are the rules up to date?** They follow Google Search Central documentation and
the relevant specs (RFC 9309, sitemaps.org, llmstxt.org) as of the release date.
Search changes; please open an issue when something drifts.

**Why are FAQ rich results flagged?** Google limited FAQ rich results to
well-known government and health sites in 2023. The markup is still valid; the
validator adds a notice so nobody promises a rich result that will not appear.

## Roadmap

Ideas for new skills and features (good first issues are marked):

- [ ] `internal-linking` - suggest links between pages from a build directory (good first issue)
- [ ] `image-seo` - file names, alt text, dimensions, formats and image sitemaps (good first issue)
- [ ] `log-file-analysis` - Googlebot hits, status codes and crawl waste from access logs
- [ ] `search-console-insights` - CTR outliers, cannibalisation and decaying pages from GSC exports (good first issue)
- [ ] `local-seo` - NAP consistency, LocalBusiness schema and location pages
- [ ] `pagination-faceted-nav` - crawl traps and parameter handling
- [ ] `ecommerce-seo` - category/product templates, out-of-stock handling, merchant listings
- [ ] `schema-markup`: Recipe, JobPosting and SoftwareApplication rules (good first issue)
- [ ] `robots-sitemap-check`: image and video sitemap extensions (good first issue)
- [ ] `redirect-map`: Vercel and Cloudflare Bulk Redirects output formats (good first issue)

## Contributing

Contributions are welcome - new skills, better rules, more fixtures, clearer
instructions. Read [CONTRIBUTING.md](CONTRIBUTING.md), start from
[templates/skill/SKILL.md](templates/skill/SKILL.md), and run the checks:

```sh
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
python tools/validate_skills.py
pytest
```

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md) and report security issues
privately as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) - Saizul Amin
