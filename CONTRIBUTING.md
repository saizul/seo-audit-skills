# Contributing to SEO Audit Skills

Thank you for helping! New skills, sharper rules, extra fixtures and clearer
instructions are all welcome.

- [Ways to contribute](#ways-to-contribute)
- [Good first issues](#good-first-issues)
- [Development setup](#development-setup)
- [Project layout](#project-layout)
- [Write a new skill](#write-a-new-skill)
- [Script guidelines](#script-guidelines)
- [Pull request process](#pull-request-process)

## Ways to contribute

| Size | Idea |
| --- | --- |
| 10 minutes | Fix a typo, clarify a step in a `SKILL.md`, add a FAQ entry |
| 30 minutes | Add a fixture for a real-world edge case and a test for it |
| 1-2 hours | Add a rule to a script, or one of the good first issues below |
| Larger | A new skill (open a "New skill proposal" issue first) |

Comment on an issue before you start so nobody else picks the same one.

## Good first issues

Each is self-contained and touches one skill.

1. **Recipe rules in `schema-markup`.** Add `Recipe` to `RULES` in
   `validate_jsonld.py` (required: name, image; recommended: recipeIngredient,
   recipeInstructions, totalTime as ISO 8601 duration, nutrition.calories) plus a
   template in `assets/templates/` and tests.
2. **JobPosting rules in `schema-markup`.** Required: title, description,
   datePosted, hiringOrganization, jobLocation (or `jobLocationType: TELECOMMUTE`
   with `applicantLocationRequirements`); check `validThrough` is ISO 8601.
3. **Image sitemap support in `robots-sitemap-check`.** Recognise the
   `image:image` namespace, count images per URL, require absolute `image:loc`.
4. **Vercel output for `redirect-map`.** Add `--format vercel` that writes a
   `vercel.json` `redirects` array (`permanent: true`), with a test.
5. **`hreflang-check` HTTP header input.** Accept a CSV of `url,link_header` and
   parse `Link: <...>; rel="alternate"; hreflang="..."` values.
6. **Generic anchor list in `on-page-seo-review`.** Move the generic anchor
   phrases to a constant, add common non-English ones (`hier klicken`,
   `cliquez ici`, `haga clic aquí`), with tests.
7. **`technical-seo-audit` X-Robots-Tag from headers file.** Let `html` mode read an
   optional `_headers` (Netlify/Cloudflare) file and apply `X-Robots-Tag` rules.
8. **`content-brief` stop words per language.** Add `--lang de|fr|es` with stop-word
   lists for `competitor_outline.py` and `keyword_intent.py` modifiers.
9. **`llms-txt` `--md-urls`.** Option to link the `.md` twin of each page
   (`/page/` -> `/page/index.md`, `/page.html` -> `/page.html.md`) per the llms.txt proposal.
10. **`core-web-vitals-triage` budgets.** `--budget LCP=2500,CLS=0.1` to fail CI on
    lab metrics over a custom budget.

## Development setup

```sh
git clone https://github.com/saizul/seo-audit-skills.git
cd seo-audit-skills
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

ruff check . && ruff format --check .
python tools/validate_skills.py
pytest
```

All four must pass; CI runs them on Python 3.11, 3.12 and 3.13. The scripts
themselves also support Python 3.9 and 3.10, so do not use `match` statements or
other syntax newer than 3.9.

To try your changes in Claude Code without publishing, add your checkout as a
local marketplace: `/plugin marketplace add ./path/to/seo-audit-skills`, then
`/plugin install seo-audit@seo-audit-skills`. Or copy a skill folder into
`~/.claude/skills/`.

## Project layout

```text
skills/<skill-name>/
  SKILL.md            frontmatter + instructions (under 400 lines)
  scripts/            deterministic helpers (Python 3.9+ stdlib)
  references/         long tables and rules, loaded on demand
  assets/             templates the agent copies
tests/
  conftest.py         load_script() helper; blocks network access
  test_<skill>.py     tests for that skill's scripts
  fixtures/<skill>/   input files for the tests
tools/validate_skills.py   repository validator (also tested)
templates/skill/SKILL.md   starting point for a new skill
.claude-plugin/            marketplace.json and plugin.json
```

## Write a new skill

1. **Propose it** with the "New skill proposal" issue template: the problem, the
   trigger phrases, what the script would check, and why existing skills do not
   cover it.
2. **Copy the template:** `cp -R templates/skill skills/<skill-name>` and edit
   `SKILL.md`. The folder name and `name` must match: lowercase letters, digits and
   single hyphens, at most 64 characters.
3. **Write the description** (max 1024 characters) as what it does plus
   "Use when ..." with the words users actually type. This is the only text the
   agent sees before choosing a skill, so be concrete.
4. **Write the body** with the required sections: `## When to use`,
   `## When not to use`, `## Workflow`, `## Output`. Imperative steps, exact
   commands, decision points, and a fixed output format. Move long tables and
   rule lists to `references/` and link them.
5. **Add a script** when a step can be checked deterministically (see below), with
   fixtures in `tests/fixtures/<skill-name>/` and tests in `tests/test_<skill_name>.py`
   that call `load_script("<skill-name>", "<script>")`.
6. **Register it:** add `./skills/<skill-name>` to the `skills` list in
   `.claude-plugin/marketplace.json`, and a row to the tables in `README.md` and
   `AGENTS.md`.
7. Run the validator and tests, and add a line under "Unreleased" in `CHANGELOG.md`.

### What makes a good skill

- It encodes judgement the model would not reliably apply on its own: priorities,
  thresholds, platform gotchas, what not to do.
- It names its sources (specs, official documentation) in references.
- It tells the agent what to ask the user for and what it must not do
  (for example, never fetch a live site without being asked).
- It produces the same output shape every time.

## Script guidelines

- Python 3.9+ standard library only (or POSIX shell). No new dependencies.
- `argparse` with a description; `--help` must work (the validator runs it).
- `--json` for machine-readable output; human-readable text by default.
- Exit codes: `0` clean, `1` findings (when the script is a checker), `2` usage or input error.
- Read-only by default. Write files only to an explicit `-o/--output` path.
- No network access unless the skill's purpose requires it, and then only behind
  an explicit opt-in flag. Tests must never touch the network (`conftest.py`
  blocks sockets).
- Never ask for, log or print secrets.
- Reject XML with a DOCTYPE before parsing.
- Keep messages specific: say what is wrong, where, and how to fix it.

## Pull request process

1. Fork, create a branch, make focused commits.
2. Fill in the pull request template; link the issue.
3. Make sure CI is green. A maintainer reviews within a few days.
4. Squash-merge; your change appears in the next release notes.

By contributing you agree that your contribution is licensed under the MIT License.
