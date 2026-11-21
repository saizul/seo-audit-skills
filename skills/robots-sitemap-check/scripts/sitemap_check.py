#!/usr/bin/env python3
"""Validate an XML sitemap or sitemap index from a local file (.xml or .xml.gz).

  sitemap_check.py sitemap.xml
  sitemap_check.py sitemap.xml.gz --base-url https://example.com
  sitemap_check.py sitemap.xml --robots robots.txt          # flag URLs robots.txt blocks
  sitemap_check.py sitemap.xml --exclude-list noindex.txt   # flag URLs that must not be listed

Checks the sitemaps.org protocol (namespace, <loc>, 50,000 URL / 50 MB limits,
W3C datetime <lastmod>, priority range), Google-specific advice (lastmod quality,
ignored changefreq/priority), duplicates, host/scheme consistency, and optional
cross-checks against robots.txt and a list of noindex/redirected URLs.

Exit status: 0 = no errors, 1 = errors (or warnings with --strict), 2 = input error.
Python 3.9+ standard library only. No network access: child sitemaps of an index
are listed, not fetched.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robots_check import Robots  # noqa: E402

NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
XHTML = "http://www.w3.org/1999/xhtml"
MAX_URLS = 50_000
MAX_BYTES = 50 * 1024 * 1024
W3C_DATETIME = re.compile(r"^\d{4}(-\d{2}(-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2}))?)?)?$")


def read_text(path: str, encoding: str = "utf-8", errors: str = "strict") -> str:
    with open(path, encoding=encoding, errors=errors) as fh:
        return fh.read()


def parse_lastmod(value: str) -> dt.datetime | None:
    v = value.strip()
    if not W3C_DATETIME.match(v):
        return None
    if len(v) == 4:
        return dt.datetime(int(v), 1, 1, tzinfo=dt.timezone.utc)
    if len(v) == 7:
        return dt.datetime(int(v[:4]), int(v[5:7]), 1, tzinfo=dt.timezone.utc)
    if len(v) == 10:
        return dt.datetime.strptime(v, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    v = v.replace("Z", "+00:00")
    if re.search(r"T\d{2}:\d{2}[+-]", v):
        v = v[:16] + ":00" + v[16:]
    try:
        parsed = dt.datetime.fromisoformat(re.sub(r"\.\d+", "", v))
    except ValueError:
        return None
    return parsed


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        data = fh.read(MAX_BYTES * 4 + 1)
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def check(
    data: bytes,
    base_url: str = "",
    robots: Robots | None = None,
    user_agent: str = "Googlebot",
    exclude: set[str] | None = None,
    now: dt.datetime | None = None,
) -> dict:
    issues: list[dict] = []

    def add(sev: str, msg: str, url: str = "") -> None:
        issues.append({"severity": sev, "url": url, "message": msg})

    now = now or dt.datetime.now(dt.timezone.utc)
    result: dict = {"type": None, "count": 0, "bytes": len(data), "issues": issues, "children": []}
    if len(data) > MAX_BYTES:
        add("error", f"Uncompressed size {len(data)} bytes exceeds the 50 MB (52,428,800 bytes) limit.")
    head = data[:2048].decode("utf-8", errors="replace")
    if "<!DOCTYPE" in head.upper():
        add("error", "Sitemap contains a DOCTYPE; refusing to parse (sitemaps must not declare one).")
        return result
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        add("error", f"Not well-formed XML: {exc}. Escape & as &amp; inside <loc>.")
        return result

    tag = root.tag
    ns, _, local = tag[1:].partition("}") if tag.startswith("{") else ("", "", tag)
    if local not in ("urlset", "sitemapindex"):
        add("error", f"Root element is <{local}>; expected <urlset> or <sitemapindex>.")
        return result
    result["type"] = local
    if ns != NS:
        add("error", f"Root namespace is '{ns or '(none)'}'; expected {NS}.")
    q = (lambda name: f"{{{ns}}}{name}") if ns else (lambda name: name)

    entries = root.findall(q("url") if local == "urlset" else q("sitemap"))
    result["count"] = len(entries)
    if len(entries) > MAX_URLS:
        add(
            "error",
            f"{len(entries)} entries exceed the 50,000 per-file limit; split into several sitemaps plus an index.",
        )
    if not entries:
        add("warning", "Sitemap has no entries.")

    base = urlsplit(base_url) if base_url else None
    hosts: Counter = Counter()
    schemes: Counter = Counter()
    seen: Counter = Counter()
    lastmods: list[str] = []
    hreflang_entries = 0
    changefreq_used = priority_used = False

    for entry in entries:
        loc_el = entry.find(q("loc"))
        loc = (loc_el.text or "").strip() if loc_el is not None else ""
        if not loc:
            add("error", "Entry without <loc>.")
            continue
        seen[loc] += 1
        parts = urlsplit(loc)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            add("error", "<loc> must be an absolute http(s) URL.", loc)
            continue
        if len(loc) > 2048:
            add("error", "<loc> is longer than 2,048 characters.", loc)
        if re.search(r"\s", loc):
            add("error", "<loc> contains whitespace; percent-encode it.", loc)
        if "#" in loc:
            add("warning", "<loc> contains a #fragment; fragments are ignored.", loc)
        if re.search(r"[?&](utm_[a-z]+|gclid|fbclid|sessionid|sid)=", loc, re.I):
            add("warning", "<loc> carries tracking/session parameters; list the canonical URL.", loc)
        hosts[parts.netloc.lower()] += 1
        schemes[parts.scheme] += 1
        if base and (parts.netloc.lower() != base.netloc.lower() or parts.scheme != base.scheme):
            add(
                "error",
                f"URL is not under {base_url}; sitemaps may only list URLs of their own host (and scheme).",
                loc,
            )

        lm_el = entry.find(q("lastmod"))
        if lm_el is not None and (lm_el.text or "").strip():
            lm = lm_el.text.strip()
            parsed = parse_lastmod(lm)
            if parsed is None:
                add("error", f"<lastmod> '{lm}' is not a W3C datetime (YYYY-MM-DD or YYYY-MM-DDThh:mm:ss+hh:mm).", loc)
            else:
                lastmods.append(lm)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.timezone.utc)
                if parsed > now + dt.timedelta(days=1):
                    add("warning", f"<lastmod> {lm} is in the future.", loc)
        if local == "urlset":
            if entry.find(q("changefreq")) is not None:
                changefreq_used = True
            pr = entry.find(q("priority"))
            if pr is not None:
                priority_used = True
                try:
                    pv = float((pr.text or "").strip())
                    if not 0.0 <= pv <= 1.0:
                        add("error", f"<priority> {pv} is outside 0.0-1.0.", loc)
                except ValueError:
                    add("error", f"<priority> '{pr.text}' is not a number.", loc)
            links = entry.findall(f"{{{XHTML}}}link")
            if links:
                hreflang_entries += 1
                for link in links:
                    href = link.get("href", "")
                    if link.get("rel") != "alternate" or not link.get("hreflang"):
                        add("error", 'xhtml:link needs rel="alternate" and an hreflang attribute.', loc)
                    if not href.startswith(("http://", "https://")):
                        add("error", f"xhtml:link href '{href}' must be absolute.", loc)
        else:
            result["children"].append(loc)
            if loc.lower().endswith((".xml", ".xml.gz")) is False and "sitemap" not in loc.lower():
                add("notice", "Child sitemap URL does not look like a sitemap file.", loc)

        if robots is not None and local == "urlset":
            res = robots.check(loc, user_agent)
            if not res["allowed"]:
                add("error", f"Listed URL is blocked by robots.txt ({res['rule']}, line {res['line']}).", loc)
        if exclude and loc in exclude:
            add("error", "Listed URL is in the exclude list (noindex, redirected, canonicalised or removed).", loc)

    for loc, n in seen.items():
        if n > 1:
            add("warning", f"Listed {n} times.", loc)
    if len(hosts) > 1:
        add("error", f"URLs span several hosts: {dict(hosts)}.")
    if len(schemes) > 1:
        add("warning", f"Mixed schemes: {dict(schemes)}; list only the canonical (normally https) URLs.")
    if len(lastmods) >= 5 and len(set(lastmods)) == 1:
        add(
            "warning",
            f"All {len(lastmods)} <lastmod> values are identical ({lastmods[0]}); Google ignores lastmod it cannot trust. Use the real content modification date.",
        )
    if entries and not lastmods:
        add("notice", "No <lastmod> values; add accurate ones to help recrawl scheduling.")
    if changefreq_used or priority_used:
        add("notice", "<changefreq>/<priority> are ignored by Google; harmless but optional.")
    result["hreflang_entries"] = hreflang_entries
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Validate a local XML sitemap / sitemap index.",
        epilog="Exit codes: 0 ok, 1 errors (or warnings with --strict), 2 input error.",
    )
    ap.add_argument("sitemap", help="sitemap file (.xml or .xml.gz)")
    ap.add_argument("--base-url", default="", help="expected scheme+host, e.g. https://example.com")
    ap.add_argument("--robots", default="", help="robots.txt file to cross-check listed URLs against")
    ap.add_argument("--user-agent", default="Googlebot", help="crawler for the robots cross-check")
    ap.add_argument("--exclude-list", default="", help="file with one URL per line that must NOT be in the sitemap")
    ap.add_argument("--now", default="", help="reference date for future-lastmod checks (YYYY-MM-DD; default today)")
    ap.add_argument("--strict", action="store_true", help="warnings also fail")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)
    try:
        data = read_bytes(args.sitemap)
        robots = Robots(read_text(args.robots, errors="replace")) if args.robots else None
        exclude = None
        if args.exclude_list:
            with open(args.exclude_list, encoding="utf-8") as fh:
                exclude = {line.strip() for line in fh if line.strip() and not line.startswith("#")}
        now = dt.datetime.strptime(args.now, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc) if args.now else None
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    res = check(data, args.base_url, robots, args.user_agent, exclude, now)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"{args.sitemap}: <{res['type'] or '?'}> with {res['count']} entries, {res['bytes']} bytes uncompressed")
        if res.get("hreflang_entries"):
            print(f"  {res['hreflang_entries']} entries carry hreflang annotations")
        for child in res["children"]:
            print(f"  child sitemap: {child}")
        order = {"error": 0, "warning": 1, "notice": 2}
        for i in sorted(res["issues"], key=lambda x: order[x["severity"]]):
            print(f"  {i['severity'].upper():<8} {i['url'] + ': ' if i['url'] else ''}{i['message']}")
        if not res["issues"]:
            print("  OK - no issues")
    bad = {"error", "warning"} if args.strict else {"error"}
    return 1 if any(i["severity"] in bad for i in res["issues"]) else 0


if __name__ == "__main__":
    sys.exit(main())
