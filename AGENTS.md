# AGENTS.md

Guidance for coding agents (OpenAI Codex, Claude Code, Cursor, Gemini CLI and
others) that use or work on this repository.

## Using the skills

Each folder in `skills/` is a self-contained [Agent Skill](https://agentskills.io/specification):
a `SKILL.md` with YAML frontmatter (`name`, `description`) and instructions, plus
optional `scripts/`, `references/` and `assets/`.

1. Pick the skill whose `description` matches the task (table below).
2. Read its `SKILL.md` fully and follow the workflow in order.
3. Run scripts from the skill folder (`python3 scripts/<name>.py --help` shows every option). They need only Python 3.9+, read local files, and print JSON with `--json`.
4. Open files in `references/` only when the workflow points to them.
5. Exit code 1 from a checker means "findings", not a crash. Exit code 2 means bad input.

| Skill | Use it for |
| --- | --- |
| `technical-seo-audit` | crawlability, indexability, canonicals, status codes, redirects, orphans (build dir or crawl CSV) |
| `on-page-seo-review` | 0-100 on-page score of one page plus title/description/heading rewrites |
| `schema-markup` | generate and validate JSON-LD (Article, Product, FAQPage, LocalBusiness, Organization, Person, BreadcrumbList...) |
| `robots-sitemap-check` | lint robots.txt, test URLs with Google's rules, validate sitemaps |
| `hreflang-check` | validate hreflang codes, return links, self-references, canonical conflicts |
| `core-web-vitals-triage` | Lighthouse / PSI / CrUX JSON to a ranked fix list |
| `llms-txt` | build and validate an llms.txt file |
| `content-brief` | keyword intent, clustering, competitor outline analysis, brief template |
| `redirect-map` | old-to-new URL mapping with fuzzy matching; nginx/Apache/Netlify rules |

### Installing for Codex

Codex reads skills from `.agents/skills/` in the repository (and parent folders up
to the repo root) and from `~/.agents/skills/` for the user
([Codex skills docs](https://developers.openai.com/codex/skills)). Copy or
symlink the skill folders there:

```sh
git clone https://github.com/saizul/seo-audit-skills.git
mkdir -p ~/.agents/skills
cp -R seo-audit-skills/skills/* ~/.agents/skills/
```

If your Codex version uses a different folder, follow its docs; the skill folders
themselves need no changes.

### Safety rules for agents

- Do not fetch live sites unless the user asked you to and named the site. Prefer
  local files, build output and exports the user provides.
- Never ask the user to paste API keys or passwords into the chat.
- Show diffs for robots.txt, redirects and canonical changes before applying them;
  these can de-index a site.

## Working on this repository

- Layout: `skills/<name>/SKILL.md` (+ `scripts/`, `references/`, `assets/`),
  `tests/` (pytest, fixtures in `tests/fixtures/<skill>/`), `tools/validate_skills.py`,
  `.claude-plugin/marketplace.json` and `plugin.json`, `templates/skill/SKILL.md`.
- Scripts: Python 3.9+ standard library only, `argparse` with `--help`, `--json`
  output, exit codes 0/1/2, no network unless behind an explicit flag, no secrets.
- Every script needs tests that use fixtures and never touch the network
  (`tests/conftest.py` blocks sockets).
- `SKILL.md` stays under 400 lines; long material goes to `references/`.
- A new skill must be added to `.claude-plugin/marketplace.json` (`skills` list),
  `README.md` and this file.

Before you finish, run:

```sh
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
python tools/validate_skills.py
pytest
```
