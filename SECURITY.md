# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | yes |

## Scope

The skills are instructions plus small Python scripts that read local files.
Please report:

- A script that executes, imports or evaluates content from the files it audits
  (HTML, XML, JSON, CSV, robots.txt)
- XML parsing that can be abused (entity expansion, external entities) or a crafted
  input that hangs a script or exhausts memory
- A script making a network request without the explicit opt-in flag (`--fetch`)
- Path traversal: a script reading or writing outside the paths it was given
- Skill instructions that would lead an agent to leak secrets, send data to third
  parties, or run destructive commands without asking the user

Wrong SEO advice or a false positive is a bug, not a vulnerability - please open a
normal issue for those.

## Reporting

Please **do not** open a public issue. Use
[GitHub private vulnerability reporting](https://github.com/saizul/seo-audit-skills/security/advisories/new)
with the affected skill and script, the version, the impact and a minimal input
that reproduces the problem.

You will get an answer within 5 working days. Fixes are released as soon as
possible and credited in the changelog unless you prefer otherwise.

## Design rules the scripts follow

- Python standard library only; no third-party dependencies to compromise.
- Read-only by default; files are written only to the path passed with `-o`.
- No network access unless a flag explicitly allows it (`onpage_review.py --fetch`).
- XML with a DOCTYPE is rejected before parsing.
- Scripts never ask for, store or print credentials.
