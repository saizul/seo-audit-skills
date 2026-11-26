# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `redirect-map`: `--format vercel` (a `redirects` array for `vercel.json`, with
  path-to-regexp characters escaped and slash-only rules skipped) and
  `--format cloudflare-bulk` (headerless CSV for a Cloudflare Bulk Redirects list, with
  `--host` for relative URL lists).
- `robots-sitemap-check`: `robots_check.py` warns when a crawler-specific group (for
  example `User-agent: Googlebot`) does not repeat the `Disallow` rules of the `*` group.
  Named groups replace `*` entirely, so those paths are crawlable for that bot. Agents
  missing the same rules share one warning; files where `*` is `Disallow: /` are skipped.

## [0.1.0] - 2026-11-21

### Added

- Nine skills: `technical-seo-audit`, `on-page-seo-review`, `schema-markup`,
  `robots-sitemap-check`, `hreflang-check`, `core-web-vitals-triage`, `llms-txt`,
  `content-brief`, `redirect-map`.
- Offline helper scripts (Python 3.9+ standard library) with `--help`, `--json`
  and meaningful exit codes, each covered by fixture-based tests.
- Claude Code plugin marketplace (`.claude-plugin/marketplace.json`) and plugin
  manifest; per-skill zip files attached to each GitHub release.
- `tools/validate_skills.py` to check skill frontmatter, sections, file
  references, script tests and the marketplace manifest.

[Unreleased]: https://github.com/saizul/seo-audit-skills/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/saizul/seo-audit-skills/releases/tag/v0.1.0
