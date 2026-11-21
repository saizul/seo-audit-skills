## What does this pull request do?

<!-- One or two sentences. Link the issue: "Closes #123". -->

## Type

- [ ] New skill
- [ ] New rule or check in an existing script
- [ ] Skill instructions / references
- [ ] Bug fix
- [ ] Documentation or tooling

## Checklist

- [ ] `ruff check . && ruff format --check .` passes
- [ ] `python tools/validate_skills.py` passes
- [ ] `pytest` passes; new behaviour has tests with fixtures in `tests/fixtures/<skill>/` and no network access
- [ ] Scripts use only the Python 3.9+ standard library, support `--help` and `--json`, and use exit codes 0/1/2
- [ ] SEO rules cite their source (spec or official documentation) in the skill's `references/`
- [ ] New skills are listed in `.claude-plugin/marketplace.json`, `README.md` and `AGENTS.md`
- [ ] No real customer data, credentials or private URLs in fixtures
- [ ] CHANGELOG.md updated under "Unreleased"
