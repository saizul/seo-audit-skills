# Example llms.txt and curation guide

## A complete example

```markdown
# Acme Sync

> Acme Sync is a command-line tool and API that keeps local folders in sync with S3-compatible object storage.

Acme Sync has two parts: the `acme` CLI (open source, MIT) and Acme Cloud (hosted dashboard, paid).
Version 3 is current; version 2 docs are archived. "Bucket" always means an S3 bucket, "space" means an Acme Cloud workspace.

## Docs

- [Quickstart](https://acme.example/docs/quickstart.md): install the CLI and run a first sync in five minutes
- [Configuration](https://acme.example/docs/config.md): every option in acme.toml with defaults
- [Conflict resolution](https://acme.example/docs/conflicts.md): what happens when both sides change a file

## API

- [REST API reference](https://acme.example/api/reference.md): endpoints, authentication and rate limits
- [Webhooks](https://acme.example/api/webhooks.md): event types and signature verification

## Policies

- [Pricing and limits](https://acme.example/pricing.md): plans, storage and transfer limits
- [Security](https://acme.example/security.md): encryption at rest and in transit, reporting vulnerabilities

## Optional

- [Changelog](https://acme.example/changelog.md): release notes since v3.0
- [Blog: migrating from v2](https://acme.example/blog/v2-to-v3.md)
```

## Curation guidelines

- **Answer-first selection.** Include a page if an assistant would need it to
  answer a real user question correctly. Exclude pages that only exist for
  marketing, navigation or SEO.
- **Short notes.** One sentence per link saying what the page answers. No
  keyword lists, no superlatives.
- **Stable URLs.** Link canonical URLs (or their `.md` twins), never tracking
  links, redirects or session URLs.
- **Context paragraph.** Disambiguate names, state the current version, define
  terms the product uses differently from the rest of the world.
- **Size.** A few kilobytes is typical. If the docs are large, link section
  index pages and consider separate files per subtree (`/docs/llms.txt`), since
  agents use the most specific file covering a URL.
- **Keep it current.** Generate it in the build, or add a checklist item to the
  release process; a stale llms.txt is worse than none.

## Markdown page versions

The llms.txt proposal suggests a clean Markdown copy of each important page at
the same URL with `.md` appended (`/docs/quickstart.html.md`), or with the
extension replaced (`/docs/quickstart.md`); directory URLs use `index.md`.
Static-site generators can emit these from the source Markdown at build time.
Pages can advertise their Markdown version with
`<link rel="alternate" type="text/markdown" href="...">`.
