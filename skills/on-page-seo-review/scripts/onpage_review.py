#!/usr/bin/env python3
"""Score the on-page SEO of one HTML document (0-100) and list concrete fixes.

  onpage_review.py page.html [--keyword "running shoes"] [--url https://example.com/p]
  onpage_review.py - < page.html
  onpage_review.py https://example.com/page --fetch      # network is opt-in

Checks title, meta description, H1 and heading outline, canonical, robots, lang,
viewport, image alt text, internal/external links, word count, Open Graph,
structured data and mixed content (http:// scripts, styles, frames and media on an
https page), plus keyword placement when --keyword is given.

Exit status: 0 = score >= --min-score, 1 = below, 2 = usage or input error.
Python 3.9+ standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

TITLE_MIN, TITLE_MAX = 30, 60
DESC_MIN, DESC_MAX = 70, 160
MIN_WORDS = 300
SKIP_TEXT = {"script", "style", "noscript", "template", "svg"}
# Subresources a browser loads; active ones are blocked as mixed content, passive ones
# are auto-upgraded or flagged "Not secure".
ACTIVE_TAGS = {"script", "iframe", "frame", "object", "embed"}
PASSIVE_TAGS = {"img", "source", "video", "audio", "track"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class OnPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.titles: list[str] = []
        self.descriptions: list[str] = []
        self.robots: list[str] = []
        self.canonicals: list[str] = []
        self.viewport = False
        self.og: dict[str, str] = {}
        self.twitter: dict[str, str] = {}
        self.headings: list[tuple[int, str]] = []
        self.images: list[dict] = []
        self.links: list[dict] = []
        self.jsonld_blocks = 0
        self.resources: list[tuple[str, str]] = []  # (kind, absolute or relative URL)
        self.text_parts: list[str] = []
        self._stack: list[str] = []
        self._capture: str | None = None
        self._buf: list[str] = []
        self._link: dict | None = None
        self._in_jsonld = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang", "").strip()
        elif tag == "meta":
            name = a.get("name", "").lower()
            prop = a.get("property", "").lower()
            content = a.get("content", "").strip()
            if name == "description":
                self.descriptions.append(content)
            elif name in ("robots", "googlebot"):
                self.robots.append(content.lower())
            elif name == "viewport":
                self.viewport = True
            elif prop.startswith("og:"):
                self.og.setdefault(prop, content)
            elif name.startswith("twitter:"):
                self.twitter.setdefault(name, content)
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonicals.append(a.get("href", "").strip())
        elif tag == "img":
            self.images.append({"src": a.get("src", ""), "alt": a.get("alt"), "has_alt": "alt" in a})
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self.jsonld_blocks += 1
        self._collect_resources(tag, a)
        if tag in ("title", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._capture = tag
            self._buf = []
        if tag == "a":
            self._link = {"href": a.get("href", "").strip(), "rel": a.get("rel", "").lower(), "text": []}
        if tag not in VOID:
            self._stack.append(tag)

    def _collect_resources(self, tag: str, a: dict) -> None:
        rel = a.get("rel", "").lower().split()
        if tag in ACTIVE_TAGS:
            src = a.get("src") or a.get("data") or ""
            if src:
                self.resources.append(("active", src.strip()))
        elif tag == "link" and ("stylesheet" in rel or "modulepreload" in rel):
            self.resources.append(("active", a.get("href", "").strip()))
        elif tag in PASSIVE_TAGS:
            for key in ("src", "poster"):
                if a.get(key):
                    self.resources.append(("passive", a[key].strip()))
            for candidate in a.get("srcset", "").split(","):
                first = candidate.strip().split(" ")[0]
                if first:
                    self.resources.append(("passive", first))

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag == self._capture:
            text = " ".join("".join(self._buf).split())
            if tag == "title":
                self.titles.append(text)
            else:
                self.headings.append((int(tag[1]), text))
            self._capture = None
        if tag == "a" and self._link is not None:
            self._link["text"] = " ".join(" ".join(self._link["text"]).split())
            self.links.append(self._link)
            self._link = None
        if tag in self._stack:
            while self._stack:
                if self._stack.pop() == tag:
                    break

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)
        if self._link is not None:
            self._link["text"].append(data)
        if any(t in SKIP_TEXT for t in self._stack) or "head" in self._stack:
            return
        if self._capture == "title":
            return
        self.text_parts.append(data)


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", text.lower())


def contains_phrase(haystack: str, phrase: str) -> bool:
    hw, pw = words(haystack), words(phrase)
    if not pw:
        return False
    n = len(pw)
    return any(hw[i : i + n] == pw for i in range(len(hw) - n + 1))


class Report:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, cid: str, weight: int, status: str, message: str, fix: str = "") -> None:
        self.checks.append({"id": cid, "weight": weight, "status": status, "message": message, "fix": fix})

    def score(self) -> int:
        total = sum(c["weight"] for c in self.checks)
        if not total:
            return 0
        got = sum(c["weight"] * {"pass": 1.0, "warn": 0.5}.get(c["status"], 0.0) for c in self.checks)
        return round(100 * got / total)


def review(html: str, url: str = "", keyword: str = "") -> dict:
    p = OnPageParser()
    p.feed(html)
    p.close()
    r = Report()

    # Title
    if not p.titles or not p.titles[0]:
        r.add(
            "title", 10, "fail", "No <title>.", "Add a unique title of 30-60 characters that leads with the main topic."
        )
    else:
        t = p.titles[0]
        n = len(t)
        if len(p.titles) > 1:
            r.add("title", 10, "warn", f"{len(p.titles)} <title> tags; the first is used.", "Keep exactly one <title>.")
        elif n < TITLE_MIN:
            r.add(
                "title",
                10,
                "warn",
                f"Title is {n} chars (<{TITLE_MIN}): '{t}'.",
                "Expand with the primary topic and a differentiator.",
            )
        elif n > TITLE_MAX:
            r.add(
                "title",
                10,
                "warn",
                f"Title is {n} chars (>{TITLE_MAX}) and may be truncated: '{t}'.",
                "Move the key phrase to the front and trim.",
            )
        else:
            r.add("title", 10, "pass", f"Title length {n}: '{t}'.")

    # Meta description
    if not p.descriptions or not p.descriptions[0]:
        r.add(
            "meta-description",
            6,
            "fail",
            "No meta description.",
            "Write a 70-160 character summary that answers the query and invites the click.",
        )
    else:
        d = p.descriptions[0]
        n = len(d)
        if len(p.descriptions) > 1:
            r.add("meta-description", 6, "warn", f"{len(p.descriptions)} meta descriptions.", "Keep one.")
        elif n < DESC_MIN or n > DESC_MAX:
            r.add(
                "meta-description",
                6,
                "warn",
                f"Meta description is {n} chars (aim for {DESC_MIN}-{DESC_MAX}).",
                "Rewrite to 70-160 characters.",
            )
        else:
            r.add("meta-description", 6, "pass", f"Meta description length {n}.")

    # H1
    h1s = [h for lvl, h in p.headings if lvl == 1]
    if not h1s:
        r.add("h1", 8, "fail", "No <h1>.", "Add one H1 that states the page topic.")
    elif len(h1s) > 1:
        r.add("h1", 8, "warn", f"{len(h1s)} H1 elements: {h1s[:3]}.", "Use a single H1; demote the others to H2.")
    elif not h1s[0]:
        r.add("h1", 8, "fail", "The H1 is empty (image without alt text or blank).", "Put the topic in the H1 as text.")
    else:
        r.add("h1", 8, "pass", f"One H1: '{h1s[0]}'.")
    if p.titles and h1s and p.titles[0] and h1s[0] and p.titles[0].strip().lower() == h1s[0].strip().lower():
        r.add(
            "title-h1-distinct",
            2,
            "warn",
            "Title and H1 are identical.",
            "Fine for many pages; consider a click-focused title and a descriptive H1.",
        )

    # Heading outline
    skips = []
    prev = 0
    for lvl, text in p.headings:
        if prev and lvl > prev + 1:
            skips.append(f"H{prev} -> H{lvl} ('{text[:40]}')")
        prev = lvl
    empty = sum(1 for _lvl, text in p.headings if not text)
    if skips or empty:
        msg = []
        if skips:
            msg.append("skipped levels: " + "; ".join(skips[:5]))
        if empty:
            msg.append(f"{empty} empty heading(s)")
        r.add(
            "heading-outline",
            4,
            "warn",
            ", ".join(msg) + ".",
            "Nest headings in order (H2 under H1, H3 under H2) and remove empty ones.",
        )
    elif len([1 for lvl, _ in p.headings if lvl == 2]) == 0:
        r.add(
            "heading-outline",
            4,
            "warn",
            "No H2 subheadings.",
            "Break the content into H2 sections that match sub-questions.",
        )
    else:
        r.add("heading-outline", 4, "pass", f"{len(p.headings)} headings, no skipped levels.")

    # Canonical
    page_url = url
    if not p.canonicals:
        r.add(
            "canonical", 6, "fail", "No rel=canonical.", 'Add <link rel="canonical" href="<absolute preferred URL>">.'
        )
    elif len(set(p.canonicals)) > 1:
        r.add("canonical", 6, "fail", f"Conflicting canonicals: {sorted(set(p.canonicals))}.", "Keep one canonical.")
    else:
        c = p.canonicals[0]
        if not urlsplit(c).scheme:
            r.add("canonical", 6, "warn", f"Canonical '{c}' is relative.", "Use an absolute URL.")
        elif url and c.rstrip("/") != url.rstrip("/"):
            r.add(
                "canonical",
                6,
                "warn",
                f"Canonical points elsewhere: {c}.",
                "Expected if this is a duplicate; otherwise make it self-referencing.",
            )
        else:
            r.add("canonical", 6, "pass", f"Canonical {c}.")
        if not page_url and urlsplit(c).scheme:
            page_url = c

    # Mixed content (only when the page is known to be https)
    if urlsplit(page_url).scheme == "https":
        insecure = {"active": [], "passive": []}
        for kind, src in p.resources:
            if src.lower().startswith("http://") and src not in insecure[kind]:
                insecure[kind].append(src)
        if insecure["active"]:
            r.add(
                "mixed-content",
                4,
                "fail",
                f"{len(insecure['active'])} script/style/frame URL(s) over http:// are blocked on https: "
                f"{insecure['active'][:3]}.",
                "Serve them over https:// (or a relative URL); blocked scripts and styles break the page.",
            )
        elif insecure["passive"]:
            r.add(
                "mixed-content",
                4,
                "warn",
                f"{len(insecure['passive'])} image/media URL(s) over http://: {insecure['passive'][:3]}.",
                "Change them to https://; browsers upgrade or flag them and the page loses its secure padlock.",
            )
        else:
            r.add("mixed-content", 4, "pass", "No http:// subresources on this https page.")

    # Robots
    robots = ",".join(p.robots)
    if "noindex" in robots or "none" in robots:
        r.add("indexable", 10, "fail", f"Page is noindex ({robots}).", "Remove noindex if this page should rank.")
    else:
        r.add("indexable", 10, "pass", "No noindex directive in the HTML.")

    # lang + viewport
    r.add(
        "lang",
        2,
        "pass" if p.lang else "fail",
        f"<html lang> = '{p.lang}'." if p.lang else "No lang attribute on <html>.",
        "" if p.lang else 'Add lang, e.g. <html lang="en">.',
    )
    r.add(
        "viewport",
        3,
        "pass" if p.viewport else "fail",
        "Viewport meta present." if p.viewport else "No viewport meta: page is not mobile-friendly.",
        "" if p.viewport else 'Add <meta name="viewport" content="width=device-width, initial-scale=1">.',
    )

    # Content length
    body_text = " ".join(p.text_parts)
    wc = len(words(body_text))
    if wc >= MIN_WORDS:
        r.add("word-count", 6, "pass", f"{wc} words of body text.")
    elif wc >= MIN_WORDS // 2:
        r.add(
            "word-count",
            6,
            "warn",
            f"{wc} words of body text.",
            "Thin for most informational queries; cover the sub-questions searchers have.",
        )
    else:
        r.add(
            "word-count",
            6,
            "fail",
            f"Only {wc} words of body text.",
            "Add substantive, unique content (or noindex if it is a utility page).",
        )

    # Images
    content_imgs = [i for i in p.images if not i["src"].startswith("data:")]
    missing_alt = [i["src"] for i in content_imgs if not i["has_alt"]]
    if not content_imgs:
        r.add("image-alt", 4, "warn", "No images.", "Consider a relevant image or diagram with descriptive alt text.")
    elif missing_alt:
        r.add(
            "image-alt",
            4,
            "fail" if len(missing_alt) * 2 > len(content_imgs) else "warn",
            f"{len(missing_alt)}/{len(content_imgs)} images lack an alt attribute: {missing_alt[:3]}.",
            'Describe informative images; use alt="" for decorative ones.',
        )
    else:
        r.add("image-alt", 4, "pass", f"All {len(content_imgs)} images have alt attributes.")

    # Links
    host = urlsplit(page_url).netloc.lower() if page_url else ""
    internal, external, generic = [], [], []
    for link in p.links:
        href = link["href"]
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absu = urljoin(page_url or "https://invalid.invalid/", href)
        h = urlsplit(absu).netloc.lower()
        if h in (host, "invalid.invalid") or not urlsplit(href).netloc:
            internal.append(link)
        else:
            external.append(link)
        if link["text"].lower() in ("click here", "here", "read more", "more", "this", "link", "learn more"):
            generic.append(link["text"])
    if len(internal) >= 3:
        r.add("internal-links", 6, "pass", f"{len(internal)} internal links.")
    elif internal:
        r.add(
            "internal-links",
            6,
            "warn",
            f"Only {len(internal)} internal link(s).",
            "Link to 3+ related pages with descriptive anchors.",
        )
    else:
        r.add("internal-links", 6, "fail", "No internal links.", "Link to related pages and a parent hub.")
    if generic:
        r.add(
            "anchor-text",
            3,
            "warn",
            f"Generic anchor text: {sorted(set(generic))}.",
            "Use anchors that describe the target page.",
        )
    else:
        r.add("anchor-text", 3, "pass", "No generic anchors found.")
    r.add(
        "external-links",
        1,
        "pass" if external else "warn",
        f"{len(external)} external links.",
        "" if external else "Cite authoritative sources where it helps the reader.",
    )

    # Social + structured data
    missing_og = [k for k in ("og:title", "og:description", "og:image") if not p.og.get(k)]
    r.add(
        "open-graph",
        3,
        "pass" if not missing_og else "warn",
        "Open Graph complete." if not missing_og else f"Missing {missing_og}.",
        "" if not missing_og else "Add og:title, og:description and og:image (1200x630).",
    )
    r.add(
        "structured-data",
        3,
        "pass" if p.jsonld_blocks else "warn",
        f"{p.jsonld_blocks} JSON-LD block(s)." if p.jsonld_blocks else "No JSON-LD structured data.",
        "" if p.jsonld_blocks else "Add schema that matches the page type (see the schema-markup skill).",
    )

    # Keyword
    kw_info = {}
    if keyword:
        title = p.titles[0] if p.titles else ""
        desc = p.descriptions[0] if p.descriptions else ""
        first100 = " ".join(words(body_text)[:100])
        h2s = " ".join(h for lvl, h in p.headings if lvl == 2)
        slug = urlsplit(page_url).path.replace("-", " ").replace("_", " ").replace("/", " ") if page_url else ""
        bw = words(body_text)
        kw_words = words(keyword)
        occurrences = (
            sum(1 for i in range(len(bw) - len(kw_words) + 1) if bw[i : i + len(kw_words)] == kw_words)
            if kw_words
            else 0
        )
        density = round(100 * occurrences * len(kw_words) / len(bw), 2) if bw else 0.0
        placements = {
            "title": contains_phrase(title, keyword),
            "h1": any(contains_phrase(h, keyword) for h in h1s),
            "first_100_words": contains_phrase(first100, keyword),
            "meta_description": contains_phrase(desc, keyword),
            "h2": contains_phrase(h2s, keyword),
            "url": contains_phrase(slug, keyword) if slug else None,
        }
        kw_info = {"keyword": keyword, "placements": placements, "occurrences": occurrences, "density_percent": density}
        for place, weight in (("title", 6), ("h1", 4), ("first_100_words", 3), ("meta_description", 2)):
            ok = placements[place]
            r.add(
                f"keyword-{place.replace('_', '-')}",
                weight,
                "pass" if ok else "fail",
                f"Keyword {'found' if ok else 'not found'} in {place.replace('_', ' ')}.",
                "" if ok else f"Work '{keyword}' (or a close variant) into the {place.replace('_', ' ')} naturally.",
            )
        if density > 3.0:
            r.add(
                "keyword-stuffing",
                3,
                "warn",
                f"Keyword density {density}% looks stuffed.",
                "Use synonyms and related entities instead of repeating the phrase.",
            )

    return {
        "url": page_url,
        "score": r.score(),
        "checks": r.checks,
        "facts": {
            "title": p.titles[0] if p.titles else None,
            "meta_description": p.descriptions[0] if p.descriptions else None,
            "h1": h1s,
            "outline": [f"{'  ' * (lvl - 1)}H{lvl} {text}" for lvl, text in p.headings],
            "word_count": wc,
            "internal_links": len(internal),
            "external_links": len(external),
            "images": len(content_imgs),
        },
        "keyword": kw_info or None,
    }


def render_text(res: dict) -> str:
    out = [f"On-page SEO score: {res['score']}/100" + (f"  ({res['url']})" if res["url"] else ""), ""]
    icons = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    order = {"fail": 0, "warn": 1, "pass": 2}
    for c in sorted(res["checks"], key=lambda c: (order[c["status"]], -c["weight"])):
        out.append(f"[{icons[c['status']]}] {c['id']:<22} {c['message']}")
        if c["fix"] and c["status"] != "pass":
            out.append(f"       {'':<22} fix: {c['fix']}")
    out.append("")
    out.append("Heading outline:")
    out.extend("  " + line for line in res["facts"]["outline"] or ["(none)"])
    return "\n".join(out)


def read_source(source: str, fetch: bool) -> tuple[str, str]:
    if source == "-":
        return sys.stdin.read(), ""
    if re.match(r"^https?://", source, re.I):
        if not fetch:
            raise ValueError("source is a URL: pass --fetch to allow one HTTP GET, or save the page and pass the file")
        req = urllib.request.Request(source, headers={"User-Agent": "seo-audit-skills/0.1 (+on-page-seo-review)"})
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - opt-in, http(s) only
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read(5_000_000).decode(charset, errors="replace"), resp.geturl()
    with open(source, encoding="utf-8", errors="replace") as fh:
        return fh.read(), ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Score on-page SEO of an HTML file (or a URL with --fetch).",
        epilog="Exit codes: 0 score >= --min-score, 1 below, 2 error.",
    )
    ap.add_argument("source", help="HTML file, '-' for stdin, or an http(s) URL together with --fetch")
    ap.add_argument("--keyword", default="", help="primary keyword/phrase to check placement for")
    ap.add_argument("--url", default="", help="the page's public URL (classifies links, checks the canonical)")
    ap.add_argument("--fetch", action="store_true", help="allow one HTTP GET when source is a URL")
    ap.add_argument("--min-score", type=int, default=70, help="exit 1 below this score (default 70)")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)
    try:
        html, fetched_url = read_source(args.source, args.fetch)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    res = review(html, url=args.url or fetched_url, keyword=args.keyword)
    print(json.dumps(res, indent=2, ensure_ascii=False) if args.json else render_text(res))
    return 0 if res["score"] >= args.min_score else 1


if __name__ == "__main__":
    sys.exit(main())
