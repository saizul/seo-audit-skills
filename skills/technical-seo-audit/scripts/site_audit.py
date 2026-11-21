#!/usr/bin/env python3
"""Technical SEO audit for a static site build or a crawler CSV export.

Two input modes, both offline:

  site_audit.py html DIR --base-url https://example.com [--clean-urls]
      Scan every *.html file in a build directory (Hugo, Jekyll, Astro, Next export,
      a wget mirror...). Checks indexability, canonicals, broken internal links,
      orphan pages, duplicate titles and click depth.

  site_audit.py csv crawl.csv
      Read a crawl export (Screaming Frog, Sitebulb, a custom crawler) with at least
      a URL and a status column. Checks status codes, redirect chains and loops,
      canonicals pointing at non-200 URLs, noindex and URL hygiene.

Exit status: 0 = no findings at or above --fail-on, 1 = findings, 2 = usage error.
Python 3.9+ standard library only. No network access.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict, deque
from html.parser import HTMLParser
from urllib.parse import unquote, urldefrag, urljoin, urlsplit, urlunsplit

SEVERITIES = ("error", "warning", "notice")
SEVERITY_RANK = {"error": 3, "warning": 2, "notice": 1}


class Finding:
    __slots__ = ("severity", "code", "url", "message")

    def __init__(self, severity: str, code: str, url: str, message: str) -> None:
        self.severity = severity
        self.code = code
        self.url = url
        self.message = message

    def as_dict(self) -> dict:
        return {"severity": self.severity, "code": self.code, "url": self.url, "message": self.message}


# --------------------------------------------------------------------------- HTML parsing


class PageParser(HTMLParser):
    """Collect the handful of tags a technical audit needs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.titles: list[str] = []
        self.canonicals: list[str] = []
        self.robots: list[str] = []
        self.links: list[tuple[str, str]] = []  # (href, rel)
        self._in_title = False
        self._title_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
            self._title_buf = []
        elif tag == "meta":
            name = a.get("name", "").lower()
            if name in ("robots", "googlebot"):
                self.robots.append(a.get("content", "").lower())
        elif tag == "link":
            rels = a.get("rel", "").lower().split()
            if "canonical" in rels:
                self.canonicals.append(a.get("href", "").strip())
        elif tag == "a" and "href" in a:
            self.links.append((a["href"].strip(), a.get("rel", "").lower()))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title = False
            self.titles.append(" ".join("".join(self._title_buf).split()))

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_buf.append(data)


def robots_flags(values: list[str]) -> set[str]:
    flags: set[str] = set()
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part == "none":
                flags.update({"noindex", "nofollow"})
            elif part:
                flags.add(part)
    return flags


# --------------------------------------------------------------------------- URL helpers


def page_key(path: str) -> str:
    """Normalise a URL path so /a, /a/, /a.html and /a/index.html compare equal."""
    path = unquote(path or "/")
    if path.endswith("/index.html"):
        path = path[: -len("index.html")]
    elif path.endswith(".html"):
        path = path[: -len(".html")]
    if len(path) > 1:
        path = path.rstrip("/")
    return path or "/"


def file_to_url(rel_path: str, base_url: str, clean_urls: bool) -> str:
    rel = rel_path.replace(os.sep, "/")
    if rel == "index.html":
        path = "/"
    elif rel.endswith("/index.html"):
        path = "/" + rel[: -len("index.html")]
    elif clean_urls and rel.endswith(".html"):
        path = "/" + rel[: -len(".html")]
    else:
        path = "/" + rel
    return base_url.rstrip("/") + path


def strip_fragment(url: str) -> str:
    return urldefrag(url)[0]


def without_query(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


# --------------------------------------------------------------------------- html mode


def audit_html(root: str, base_url: str, clean_urls: bool, max_depth: int) -> tuple[list[Finding], dict]:
    base = urlsplit(base_url)
    if base.scheme not in ("http", "https") or not base.netloc:
        raise ValueError("--base-url must be an absolute http(s) URL, e.g. https://example.com")
    host = base.netloc.lower()

    pages: dict[str, dict] = {}  # key -> info
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not name.lower().endswith((".html", ".htm")):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            url = file_to_url(rel, base_url, clean_urls)
            parser = PageParser()
            with open(full, encoding="utf-8", errors="replace") as fh:
                parser.feed(fh.read())
            key = page_key(urlsplit(url).path)
            pages[key] = {"url": url, "file": rel, "p": parser, "flags": robots_flags(parser.robots)}

    findings: list[Finding] = []
    inlinks: dict[str, set[str]] = defaultdict(set)
    graph: dict[str, set[str]] = defaultdict(set)
    titles: dict[str, list[str]] = defaultdict(list)

    def internal_key(abs_url: str) -> str | None:
        p = urlsplit(abs_url)
        if p.scheme not in ("http", "https") or p.netloc.lower() != host:
            return None
        return page_key(p.path)

    def asset_exists(abs_url: str) -> bool:
        rel = unquote(urlsplit(abs_url).path).lstrip("/")
        candidate = os.path.normpath(os.path.join(root, rel))
        if not candidate.startswith(os.path.normpath(root)):
            return False
        return os.path.isfile(candidate) or os.path.isfile(os.path.join(candidate, "index.html"))

    for key, info in sorted(pages.items()):
        url, p, flags = info["url"], info["p"], info["flags"]

        # Titles
        if not p.titles or not p.titles[0]:
            findings.append(Finding("error", "title-missing", url, "Page has no <title>."))
        else:
            if len(p.titles) > 1:
                findings.append(Finding("warning", "title-multiple", url, f"{len(p.titles)} <title> tags."))
            if "noindex" not in flags:
                titles[p.titles[0].lower()].append(url)

        # Indexability
        if "noindex" in flags:
            findings.append(Finding("notice", "noindex", url, "Page is noindex (meta robots)."))
        if "nofollow" in flags:
            findings.append(
                Finding("warning", "nofollow-page", url, "Meta robots nofollow: links on this page are not followed.")
            )
        if len(p.robots) > 1 and len({tuple(sorted(robots_flags([r]))) for r in p.robots}) > 1:
            findings.append(Finding("warning", "robots-conflict", url, f"Conflicting robots meta tags: {p.robots}"))

        # Canonicals
        canon_abs = None
        if not p.canonicals:
            findings.append(Finding("warning", "canonical-missing", url, "No rel=canonical."))
        else:
            distinct = {c for c in p.canonicals}
            if len(distinct) > 1:
                findings.append(
                    Finding(
                        "error",
                        "canonical-multiple",
                        url,
                        f"Multiple different canonicals {sorted(distinct)}: Google may ignore all of them.",
                    )
                )
            raw = p.canonicals[0]
            if not raw:
                findings.append(Finding("error", "canonical-empty", url, "rel=canonical with an empty href."))
            else:
                if not urlsplit(raw).scheme:
                    findings.append(
                        Finding(
                            "warning", "canonical-relative", url, f"Canonical '{raw}' is relative; use an absolute URL."
                        )
                    )
                canon_abs = strip_fragment(urljoin(url, raw))
                ck = internal_key(canon_abs)
                if ck is None:
                    findings.append(
                        Finding(
                            "warning", "canonical-cross-domain", url, f"Canonical points to another host: {canon_abs}"
                        )
                    )
                elif ck != key:
                    target = pages.get(ck)
                    if target is None:
                        findings.append(
                            Finding(
                                "error",
                                "canonical-target-missing",
                                url,
                                f"Canonical target {canon_abs} does not exist in the build.",
                            )
                        )
                    else:
                        if "noindex" in target["flags"]:
                            findings.append(
                                Finding(
                                    "error", "canonical-to-noindex", url, f"Canonical target {canon_abs} is noindex."
                                )
                            )
                        tc = target["p"].canonicals
                        if tc and internal_key(strip_fragment(urljoin(target["url"], tc[0]))) not in (ck, None):
                            findings.append(
                                Finding(
                                    "warning",
                                    "canonical-chain",
                                    url,
                                    f"Canonical target {canon_abs} canonicalises elsewhere ({tc[0]}).",
                                )
                            )
                    if "noindex" in flags:
                        findings.append(
                            Finding(
                                "warning",
                                "noindex-and-canonical",
                                url,
                                "Page is noindex and canonicalises elsewhere: send one signal, not both.",
                            )
                        )
                elif (
                    canon_abs != url
                    and without_query(canon_abs).rstrip("/") == url.rstrip("/")
                    and canon_abs.endswith("/") != url.endswith("/")
                ):
                    findings.append(
                        Finding(
                            "notice",
                            "canonical-slash-mismatch",
                            url,
                            f"Canonical {canon_abs} differs from the served URL only by a trailing slash.",
                        )
                    )

        # Links
        follow_links = "nofollow" not in flags
        for href, rel in p.links:
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
                continue
            abs_url = strip_fragment(urljoin(url, href))
            tk = internal_key(abs_url)
            if tk is None:
                continue
            if tk in pages:
                if tk != key:
                    inlinks[tk].add(key)
                    if follow_links and "nofollow" not in rel:
                        graph[key].add(tk)
                if urlsplit(abs_url).scheme != base.scheme:
                    findings.append(
                        Finding(
                            "warning",
                            "link-scheme-mismatch",
                            url,
                            f"Internal link uses {urlsplit(abs_url).scheme}: {href}",
                        )
                    )
            elif not asset_exists(abs_url):
                findings.append(
                    Finding("error", "broken-internal-link", url, f"Link to {abs_url} has no matching page or file.")
                )

    for title, urls in titles.items():
        if len(urls) > 1:
            for u in urls:
                findings.append(
                    Finding(
                        "warning",
                        "title-duplicate",
                        u,
                        f"Title '{title[:70]}' is shared by {len(urls)} indexable pages.",
                    )
                )

    home = "/"
    depth: dict[str, int] = {}
    if home in pages:
        depth[home] = 0
        queue = deque([home])
        while queue:
            cur = queue.popleft()
            for nxt in graph.get(cur, ()):
                if nxt not in depth:
                    depth[nxt] = depth[cur] + 1
                    queue.append(nxt)
    else:
        findings.append(
            Finding(
                "warning", "homepage-missing", base_url, "No index.html at the build root; click depth not computed."
            )
        )

    for key, info in sorted(pages.items()):
        if key == home or "noindex" in info["flags"]:
            continue
        if not inlinks.get(key):
            findings.append(Finding("warning", "orphan-page", info["url"], "No internal links point to this page."))
        elif home in pages and key not in depth:
            findings.append(
                Finding(
                    "warning",
                    "unreachable-from-home",
                    info["url"],
                    "Linked only from pages that cannot be reached from the homepage via followed links.",
                )
            )
        elif depth.get(key, 0) > max_depth:
            findings.append(
                Finding(
                    "notice",
                    "deep-page",
                    info["url"],
                    f"Click depth {depth[key]} from the homepage (limit {max_depth}).",
                )
            )

    stats = {
        "pages": len(pages),
        "indexable": sum(1 for i in pages.values() if "noindex" not in i["flags"]),
        "max_click_depth": max(depth.values()) if depth else None,
    }
    return findings, stats


# --------------------------------------------------------------------------- csv mode

COLUMN_ALIASES = {
    "url": ("url", "address", "page", "loc"),
    "status": ("status", "status code", "status_code", "http status", "response code"),
    "canonical": ("canonical", "canonical link element 1", "canonical_url", "canonical url"),
    "meta_robots": ("meta robots", "meta_robots", "meta robots 1", "robots"),
    "x_robots": ("x-robots-tag", "x_robots_tag", "x-robots-tag 1", "x robots tag"),
    "redirect": ("redirect", "redirect url", "redirect_url", "location", "redirect target", "redirect uri"),
}


def map_columns(header: list[str]) -> dict[str, str]:
    lower = {h.strip().lower(): h for h in header}
    out = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower:
                out[field] = lower[alias]
                break
    return out


def audit_csv(path: str, max_chain: int) -> tuple[list[Finding], dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        cols = map_columns(reader.fieldnames or [])
        if "url" not in cols or "status" not in cols:
            raise ValueError(f"CSV needs a URL column and a status column; found {reader.fieldnames}")
        rows = list(reader)

    def get(row: dict, field: str) -> str:
        col = cols.get(field)
        return (row.get(col) or "").strip() if col else ""

    records: dict[str, dict] = {}
    for row in rows:
        url = get(row, "url")
        if not url:
            continue
        try:
            status = int(float(get(row, "status") or 0))
        except ValueError:
            status = 0
        records[url] = {
            "status": status,
            "canonical": get(row, "canonical"),
            "robots": robots_flags([get(row, "meta_robots"), get(row, "x_robots")]),
            "redirect": get(row, "redirect"),
        }

    findings: list[Finding] = []
    seen_norm: dict[str, str] = {}
    schemes: set[str] = set()

    for url, r in records.items():
        st = r["status"]
        parts = urlsplit(url)
        schemes.add(parts.scheme)
        if st == 0:
            findings.append(Finding("error", "no-response", url, "No status code (timeout, DNS or connection error)."))
        elif st >= 500:
            findings.append(Finding("error", "server-error", url, f"HTTP {st}."))
        elif st >= 400:
            findings.append(Finding("error", "client-error", url, f"HTTP {st}."))
        elif 300 <= st < 400:
            if st in (302, 303, 307):
                findings.append(
                    Finding(
                        "warning",
                        "temporary-redirect",
                        url,
                        f"HTTP {st} temporary redirect; use 301/308 for permanent moves.",
                    )
                )
            if not r["redirect"]:
                findings.append(
                    Finding("warning", "redirect-no-target", url, f"HTTP {st} without a redirect target in the export.")
                )
            else:
                chain = [url]
                cur = urljoin(url, r["redirect"])
                loop = False
                while cur in records and 300 <= records[cur]["status"] < 400 and records[cur]["redirect"]:
                    if cur in chain:
                        loop = True
                        break
                    chain.append(cur)
                    cur = urljoin(cur, records[cur]["redirect"])
                    if len(chain) > 20:
                        break
                if loop or cur in chain:
                    findings.append(
                        Finding("error", "redirect-loop", url, "Redirect loop: " + " -> ".join(chain + [cur]))
                    )
                elif len(chain) > max_chain:
                    findings.append(
                        Finding("warning", "redirect-chain", url, f"{len(chain)} hops: " + " -> ".join(chain + [cur]))
                    )
                elif cur in records and records[cur]["status"] >= 400:
                    findings.append(
                        Finding(
                            "error",
                            "redirect-to-error",
                            url,
                            f"Redirects to {cur} which returns {records[cur]['status']}.",
                        )
                    )

        if 200 <= st < 300:
            if "noindex" in r["robots"]:
                findings.append(Finding("notice", "noindex", url, "200 page marked noindex (meta or X-Robots-Tag)."))
            canon = r["canonical"]
            if canon:
                cabs = urljoin(url, canon)
                target = records.get(cabs)
                if cabs != url and target is not None:
                    tst = target["status"]
                    if 300 <= tst < 400:
                        findings.append(
                            Finding("error", "canonical-to-redirect", url, f"Canonical {cabs} redirects ({tst}).")
                        )
                    elif tst >= 400 or tst == 0:
                        findings.append(
                            Finding(
                                "error", "canonical-to-error", url, f"Canonical {cabs} returns {tst or 'no response'}."
                            )
                        )
                    elif "noindex" in target["robots"]:
                        findings.append(Finding("error", "canonical-to-noindex", url, f"Canonical {cabs} is noindex."))
                if "noindex" in r["robots"] and cabs != url:
                    findings.append(
                        Finding(
                            "warning",
                            "noindex-and-canonical",
                            url,
                            "noindex plus a canonical to another URL sends mixed signals.",
                        )
                    )
            elif "noindex" not in r["robots"]:
                findings.append(Finding("warning", "canonical-missing", url, "Indexable page without a canonical."))

            if parts.path != parts.path.lower() and re.search(r"[A-Z]", parts.path):
                findings.append(Finding("notice", "uppercase-url", url, "URL path contains uppercase letters."))
            if parts.query and re.search(r"(^|&)(utm_[a-z]+|gclid|fbclid|sessionid|sid)=", parts.query, re.I):
                findings.append(
                    Finding(
                        "warning", "tracking-parameter-url", url, "Crawled URL carries tracking/session parameters."
                    )
                )
            norm = (parts.netloc.lower(), parts.path.lower().rstrip("/") or "/", parts.query)
            nkey = "|".join(norm)
            if nkey in seen_norm and seen_norm[nkey] != url:
                findings.append(
                    Finding(
                        "warning",
                        "duplicate-url-variant",
                        url,
                        f"Same page as {seen_norm[nkey]} apart from case or trailing slash.",
                    )
                )
            else:
                seen_norm[nkey] = url

    if {"http", "https"} <= schemes:
        http_200 = [u for u, r in records.items() if u.startswith("http://") and 200 <= r["status"] < 300]
        for u in http_200[:50]:
            findings.append(
                Finding("error", "http-page-served", u, "HTTP (not HTTPS) URL returns 200; redirect it to HTTPS.")
            )

    counts: dict[str, int] = defaultdict(int)
    for r in records.values():
        counts[f"{r['status'] // 100}xx" if r["status"] else "no-response"] += 1
    stats = {"urls": len(records), "status_classes": dict(sorted(counts.items()))}
    return findings, stats


# --------------------------------------------------------------------------- output


def render_text(findings: list[Finding], stats: dict) -> str:
    lines = ["Technical SEO audit", "=" * 19, ""]
    lines.append("Stats: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    by_sev = defaultdict(list)
    for f in findings:
        by_sev[f.severity].append(f)
    lines.append("Findings: " + ", ".join(f"{s}={len(by_sev[s])}" for s in SEVERITIES))
    for sev in SEVERITIES:
        if not by_sev[sev]:
            continue
        lines.append("")
        lines.append(f"[{sev.upper()}]")
        for f in sorted(by_sev[sev], key=lambda x: (x.code, x.url)):
            lines.append(f"  {f.code:<26} {f.url}")
            lines.append(f"  {'':<26} {f.message}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Offline technical SEO audit of a static build directory or a crawl CSV export.",
        epilog="Exit codes: 0 clean, 1 findings at or above --fail-on, 2 usage or input error.",
    )
    sub = ap.add_subparsers(dest="mode", required=True)
    h = sub.add_parser("html", help="audit a directory of built HTML files")
    h.add_argument("directory")
    h.add_argument("--base-url", required=True, help="production origin, e.g. https://example.com")
    h.add_argument("--clean-urls", action="store_true", help="about.html is served as /about")
    h.add_argument("--max-depth", type=int, default=3, help="click depth that triggers a notice (default 3)")
    c = sub.add_parser("csv", help="audit a crawler CSV export")
    c.add_argument("csv_file")
    c.add_argument("--max-chain", type=int, default=1, help="redirect hops allowed before a warning (default 1)")
    for p in (h, c):
        p.add_argument("--json", action="store_true", help="print machine-readable JSON")
        p.add_argument("--fail-on", choices=("error", "warning", "notice", "never"), default="error")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.mode == "html":
            if not os.path.isdir(args.directory):
                raise ValueError(f"not a directory: {args.directory}")
            findings, stats = audit_html(args.directory, args.base_url, args.clean_urls, args.max_depth)
        else:
            findings, stats = audit_csv(args.csv_file, args.max_chain)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"stats": stats, "findings": [f.as_dict() for f in findings]}, indent=2))
    else:
        print(render_text(findings, stats))

    if args.fail_on == "never":
        return 0
    threshold = SEVERITY_RANK[args.fail_on]
    return 1 if any(SEVERITY_RANK[f.severity] >= threshold for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
