#!/usr/bin/env python3
"""Build or validate an llms.txt file (https://llmstxt.org) from local inputs.

Build:
  llms_txt.py build --name "Example" --summary "One-line summary." \\
      --sitemap sitemap.xml --section "Docs=/docs/" --section "Blog=/blog/" \\
      --optional Blog -o llms.txt
  llms_txt.py build --name "Example" --pages pages.csv        # url,title,description[,section]
  llms_txt.py build --name "Example" --html-dir public/ --base-url https://example.com

Validate:
  llms_txt.py validate llms.txt

The build step groups URLs into H2 sections by path prefix, uses <title>/meta
descriptions when HTML or a pages file is given, drops pagination/tag/feed URLs by
default, and puts sections passed to --optional under "## Optional".

Exit status: build 0; validate 0 = valid, 1 = errors (or warnings with --strict);
2 = input error. Python 3.9+ standard library only. No network access.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urlsplit

DEFAULT_EXCLUDES = [
    r"/page/\d+/?$",
    r"/tag/",
    r"/tags/",
    r"/author/",
    r"/feed/?$",
    r"/wp-json/",
    r"\?",
    r"/cart/?$",
    r"/checkout/?$",
    r"/my-account/?",
    r"/login/?$",
    r"/search/?$",
]
LINK_ITEM = re.compile(r"^\s*[-*+]\s+\[(?P<name>[^\]]+)\]\((?P<url>[^)\s]+)\)(?P<rest>.*)$")


def read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def read_text(path: str, encoding: str = "utf-8", errors: str = "strict") -> str:
    with open(path, encoding=encoding, errors=errors) as fh:
        return fh.read()


class MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.noindex = False
        self._in_title = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title" and not self.title:
            self._in_title = True
        elif tag == "meta":
            name = a.get("name", "").lower()
            if name == "description" and not self.description:
                self.description = " ".join(a.get("content", "").split())
            elif name == "robots" and "noindex" in a.get("content", "").lower():
                self.noindex = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title = False
            self.title = " ".join("".join(self._buf).split())

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._buf.append(data)


def title_from_url(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1] if path else ""
    slug = re.sub(r"\.(html?|php|aspx?)$", "", slug)
    if not slug:
        return "Home"
    words = re.split(r"[-_]+", slug)
    return " ".join(w.capitalize() if not w.isupper() else w for w in words if w)


def clean_title(title: str, site_name: str) -> str:
    # Drop a trailing " | Site" or " - Site" brand suffix.
    if site_name:
        title = re.sub(rf"\s*[|\-–—:·]\s*{re.escape(site_name)}\s*$", "", title, flags=re.I)
    return title.strip() or site_name


def load_sitemap(path: str) -> list[dict]:
    data = read_file_bytes(path)
    if b"<!DOCTYPE" in data[:2048].upper():
        raise ValueError("sitemap declares a DOCTYPE; refusing to parse")
    root = ET.fromstring(data)
    ns = root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""
    q = (lambda n: f"{{{ns}}}{n}") if ns else (lambda n: n)
    if root.tag.endswith("sitemapindex"):
        raise ValueError("this is a sitemap index; pass one of its child sitemaps (or several --sitemap files)")
    return [
        {"url": (u.findtext(q("loc")) or "").strip(), "title": "", "description": ""}
        for u in root.findall(q("url"))
        if (u.findtext(q("loc")) or "").strip()
    ]


def load_pages(path: str) -> list[dict]:
    if path.endswith(".json"):
        data = json.loads(read_text(path))
        if isinstance(data, dict):
            data = data.get("pages", [])
        return [
            {
                "url": d["url"],
                "title": d.get("title", ""),
                "description": d.get("description", ""),
                "section": d.get("section", ""),
            }
            for d in data
        ]
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if rows and "url" not in {k.lower() for k in rows[0]}:
        raise ValueError("pages CSV needs a 'url' column (optional: title, description, section)")
    out = []
    for r in rows:
        r = {k.lower().strip(): (v or "").strip() for k, v in r.items()}
        if r.get("url"):
            out.append(
                {
                    "url": r["url"],
                    "title": r.get("title", ""),
                    "description": r.get("description", ""),
                    "section": r.get("section", ""),
                }
            )
    return out


def load_html(root: str, base_url: str) -> list[dict]:
    out = []
    for dirpath, _d, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            path = (
                "/"
                if rel == "index.html"
                else "/" + (rel[: -len("index.html")] if rel.endswith("/index.html") else rel)
            )
            p = MetaParser()
            with open(full, encoding="utf-8", errors="replace") as fh:
                p.feed(fh.read())
            if p.noindex:
                continue
            out.append(
                {"url": base_url.rstrip("/") + path, "title": p.title, "description": p.description, "section": ""}
            )
    return out


def build(
    pages: list[dict],
    name: str,
    summary: str,
    details: str,
    sections: list[tuple[str, str]],
    optional: set[str],
    excludes: list[str],
    default_section: str,
) -> str:
    rx = [re.compile(e) for e in excludes]
    seen = set()
    grouped: dict[str, list[dict]] = {}
    order = [s for s, _ in sections]
    for page in pages:
        url = page["url"]
        if url in seen or any(r.search(url) for r in rx):
            continue
        seen.add(url)
        section = page.get("section") or ""
        if not section:
            path = urlsplit(url).path or "/"
            best = ""
            for sec, prefix in sections:
                if path.startswith(prefix) and len(prefix) > len(best):
                    best, section = prefix, sec
        section = section or default_section
        if section not in order:
            order.append(section)
        grouped.setdefault(section, []).append(page)

    lines = [f"# {name}", ""]
    if summary:
        lines += [f"> {summary.strip()}", ""]
    if details:
        lines += [details.strip(), ""]
    ordered = [s for s in order if s in grouped and s not in optional] + [
        s for s in order if s in grouped and s in optional
    ]
    wrote_optional = False
    for sec in ordered:
        if sec in optional:
            if not wrote_optional:
                lines += ["## Optional", ""]
                wrote_optional = True
        else:
            lines += [f"## {sec}", ""]
        for page in sorted(grouped[sec], key=lambda p: (urlsplit(p["url"]).path.count("/"), p["url"])):
            title = (
                clean_title(page.get("title") or title_from_url(page["url"]), name).replace("[", "(").replace("]", ")")
            )
            desc = (page.get("description") or "").strip()
            lines.append(f"- [{title}]({page['url']})" + (f": {desc}" if desc else ""))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def validate(text: str) -> list[dict]:
    issues: list[dict] = []

    def add(sev: str, line: int, msg: str) -> None:
        issues.append({"severity": sev, "line": line, "message": msg})

    lines = text.lstrip("﻿").splitlines()
    content = [(i + 1, line) for i, line in enumerate(lines) if line.strip()]
    if not content:
        add("error", 0, "File is empty.")
        return issues
    first_no, first = content[0]
    if not re.match(r"^# \S", first):
        add("error", first_no, "The first line must be an H1 with the site or project name ('# Name').")
    h1s = [n for n, line in content if re.match(r"^# ", line)]
    if len(h1s) > 1:
        add("error", h1s[1], "Only one H1 is allowed.")
    if len(content) < 2 or not content[1][1].startswith(">"):
        add("warning", first_no + 1, "No blockquote summary after the H1 ('> one or two sentences').")
    in_section = None
    section_links: dict[str, int] = {}
    urls: dict[str, int] = {}
    for n, line in content[1:]:
        if re.match(r"^#{3,6} ", line):
            add("warning", n, "Only H1 and H2 headings are part of the format; use H2 for file-list sections.")
            continue
        if line.startswith("## "):
            in_section = line[3:].strip()
            if in_section in section_links:
                add("warning", n, f"Section '{in_section}' appears twice.")
            section_links.setdefault(in_section, 0)
            continue
        if in_section is None:
            continue  # prose and lists before the first H2 are free-form
        m = LINK_ITEM.match(line)
        if not m:
            if re.match(r"^\s*[-*+]\s", line):
                add(
                    "error",
                    n,
                    "List item in a file-list section must start with a Markdown link: '- [name](url): notes'.",
                )
            else:
                add("warning", n, "Prose inside an H2 file-list section; move it above the first H2.")
            continue
        section_links[in_section] += 1
        url, rest = m.group("url"), m.group("rest").strip()
        if rest and not rest.startswith(":"):
            add("warning", n, "Notes after the link should be introduced with ': '.")
        if not re.match(r"^https?://", url):
            add("warning", n, f"URL '{url}' is relative; absolute URLs are safest for agents.")
        if url in urls:
            add("warning", n, f"URL also listed on line {urls[url]}.")
        urls.setdefault(url, n)
    for sec, count in section_links.items():
        if count == 0:
            add("warning", 0, f"Section '{sec}' has no links.")
    if not section_links:
        add("notice", 0, "No H2 file-list sections; agents get no links to follow.")
    size = len(text.encode("utf-8"))
    if size > 100_000:
        add("warning", 0, f"File is {size} bytes; keep llms.txt concise and move long content to linked .md pages.")
    return issues


def parse_section(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("use NAME=/path/prefix/")
    name, prefix = value.split("=", 1)
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    return name.strip(), prefix.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build or validate llms.txt (llmstxt.org).",
        epilog="Exit codes: 0 ok, 1 validation errors, 2 input error.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="generate llms.txt from a sitemap, a pages CSV/JSON or an HTML build")
    src = b.add_mutually_exclusive_group(required=True)
    src.add_argument("--sitemap", action="append", help="local sitemap.xml (repeatable)")
    src.add_argument("--pages", help="CSV or JSON with url,title,description[,section]")
    src.add_argument("--html-dir", help="directory of built HTML (needs --base-url)")
    b.add_argument("--base-url", default="", help="origin for --html-dir")
    b.add_argument("--name", required=True, help="site or project name (the H1)")
    b.add_argument("--summary", default="", help="one or two sentence summary (blockquote)")
    b.add_argument("--details", default="", help="optional paragraph(s) shown before the sections")
    b.add_argument(
        "--section",
        action="append",
        type=parse_section,
        default=[],
        metavar="NAME=/prefix/",
        help="map a path prefix to a section, in output order",
    )
    b.add_argument("--default-section", default="Pages", help="section for URLs no prefix matches (default Pages)")
    b.add_argument(
        "--optional", action="append", default=[], metavar="NAME", help="section to place under '## Optional'"
    )
    b.add_argument(
        "--exclude", action="append", default=[], metavar="REGEX", help="drop URLs matching REGEX (repeatable)"
    )
    b.add_argument(
        "--no-default-excludes", action="store_true", help="keep pagination, tag, author, feed, cart... URLs"
    )
    b.add_argument("-o", "--output", help="write to file instead of stdout")
    v = sub.add_parser("validate", help="check an llms.txt file against the format")
    v.add_argument("file", help="llms.txt path ('-' for stdin)")
    v.add_argument("--strict", action="store_true", help="warnings also fail")
    v.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)

    if args.cmd == "validate":
        try:
            text = sys.stdin.read() if args.file == "-" else read_text(args.file)
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        issues = validate(text)
        if args.json:
            print(json.dumps({"issues": issues}, indent=2))
        else:
            for i in issues:
                loc = f"line {i['line']}" if i["line"] else "file"
                print(f"{i['severity'].upper():<8} {loc}: {i['message']}")
            if not issues:
                print("OK - valid llms.txt")
        bad = {"error", "warning"} if args.strict else {"error"}
        return 1 if any(i["severity"] in bad for i in issues) else 0

    try:
        if args.sitemap:
            pages = [p for s in args.sitemap for p in load_sitemap(s)]
        elif args.pages:
            pages = load_pages(args.pages)
        else:
            if not args.base_url:
                ap.error("--html-dir needs --base-url")
            pages = load_html(args.html_dir, args.base_url)
    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    excludes = list(args.exclude) + ([] if args.no_default_excludes else DEFAULT_EXCLUDES)
    out = build(
        pages, args.name, args.summary, args.details, args.section, set(args.optional), excludes, args.default_section
    )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"wrote {args.output} ({out.count(chr(10) + '- [')} links)", file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
