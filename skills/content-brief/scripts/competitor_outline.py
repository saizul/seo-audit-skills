#!/usr/bin/env python3
"""Compare saved competitor pages and extract what a content brief needs.

  competitor_outline.py rank1.html rank2.html rank3.html
  competitor_outline.py rank*.html --ours draft.html --min-docs 2 --json

For each page: title, H1-H3 outline, word count, question headings and FAQ
questions. Across pages: terms and phrases (1-3 words) used by at least
--min-docs pages, recurring subtopics (similar H2/H3 headings), the median word
count, and - with --ours - the terms and subtopics your page is missing.

Save pages with your browser ("Save page as... HTML only") or curl; this script
never fetches anything. Exit status: 0 ok, 2 input error.
Python 3.9+ standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter
from difflib import SequenceMatcher
from html.parser import HTMLParser

STOP = set(
    """
    a about above after again against all also am an and any are as at back be because been before
    being below best between both but by can could did do does doing down during each even every few
    first for from further get got had has have having he her here hers him his how i if in into is
    it its itself just let like lot lots made make many matter matters may me might more most much
    must my need new no nor not now of off on once one only or other our ours out over own really
    same see she should so some still such than that the their them then there these they thing
    things this those through to too two under until up use used using very was way ways we well
    were what when where which while who whom why will with would you your yours
    """.split()
)
SKIP = {"script", "style", "noscript", "template", "svg", "nav", "footer", "header", "aside", "form"}


class OutlineParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.headings: list[tuple[int, str]] = []
        self.text: list[str] = []
        self.jsonld: list[str] = []
        self._stack: list[str] = []
        self._cap: str | None = None
        self._buf: list[str] = []
        self._in_jsonld = False
        self._buf_ld: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("title", "h1", "h2", "h3"):
            self._cap, self._buf = tag, []
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._buf_ld = []
        if tag not in ("meta", "link", "img", "br", "hr", "input", "source"):
            self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._cap:
            text = " ".join("".join(self._buf).split())
            if tag == "title":
                self.title = self.title or text
            elif text:
                self.headings.append((int(tag[1]), text))
            self._cap = None
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            self.jsonld.append("".join(self._buf_ld))
        if tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._buf_ld.append(data)
            return
        if self._cap:
            self._buf.append(data)
        if "head" in self._stack or any(t in SKIP for t in self._stack):
            return
        self.text.append(data)


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9'+-]*[a-z0-9]|[a-z0-9]", text.lower())


def ngrams(words: list[str], n: int) -> set[str]:
    out = set()
    for i in range(len(words) - n + 1):
        gram = words[i : i + n]
        if gram[0] in STOP or gram[-1] in STOP or all(w.isdigit() for w in gram):
            continue
        if n == 3 and gram[1] in ("and", "or"):
            continue  # "x and y" is a list, not a phrase
        if n == 1 and (len(gram[0]) < 3 or gram[0] in STOP):
            continue
        out.add(" ".join(gram))
    return out


def faq_questions(blocks: list[str]) -> list[str]:
    qs = []

    def walk(node) -> None:
        if isinstance(node, dict):
            t = node.get("@type")
            if t == "Question" or (isinstance(t, list) and "Question" in t):
                if isinstance(node.get("name"), str):
                    qs.append(node["name"].strip())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for b in blocks:
        try:
            walk(json.loads(b))
        except json.JSONDecodeError:
            continue
    return qs


def analyse_page(path: str) -> dict:
    with open(path, encoding="utf-8", errors="replace") as fh:
        p = OutlineParser()
        p.feed(fh.read())
    body = " ".join(p.text)
    words = tokens(body)
    terms = set()
    for n in (1, 2, 3):
        terms |= ngrams(words, n)
    questions = [
        h
        for _lvl, h in p.headings
        if h.endswith("?") or re.match(r"(?i)^(how|what|why|when|where|which|who|can|is|are|do|does|should)\b", h)
    ]
    return {
        "file": os.path.basename(path),
        "title": p.title,
        "h1": [h for lvl, h in p.headings if lvl == 1],
        "outline": [{"level": lvl, "text": h} for lvl, h in p.headings],
        "word_count": len(words),
        "questions": questions,
        "faq_schema_questions": faq_questions(p.jsonld),
        "_terms": terms,
        "_counts": Counter(w for w in words if w not in STOP and len(w) > 2),
    }


def norm_heading(h: str) -> str:
    h = re.sub(r"^\s*(\d+[.)]|step \d+:?)\s*", "", h.lower())
    return " ".join(w for w in tokens(h) if w not in STOP)


def subtopics(pages: list[dict], min_docs: int, threshold: float = 0.6) -> list[dict]:
    groups: list[dict] = []
    for page in pages:
        for item in page["outline"]:
            if item["level"] not in (2, 3):
                continue
            key = norm_heading(item["text"])
            if not key:
                continue
            for g in groups:
                if SequenceMatcher(None, key, g["key"]).ratio() >= threshold or (
                    set(key.split()) and set(key.split()) == set(g["key"].split())
                ):
                    g["docs"].add(page["file"])
                    g["examples"].append(item["text"])
                    break
            else:
                groups.append({"key": key, "docs": {page["file"]}, "examples": [item["text"]]})
    out = [
        {
            "subtopic": g["examples"][0],
            "pages": len(g["docs"]),
            "variants": sorted(set(g["examples"]))[:4],
            "_key": g["key"],
        }
        for g in groups
        if len(g["docs"]) >= min_docs
    ]
    return sorted(out, key=lambda g: -g["pages"])


def compare(paths: list[str], ours: str | None, min_docs: int, top: int) -> dict:
    pages = [analyse_page(p) for p in paths]
    n = len(pages)
    min_docs = max(1, min(min_docs, n))
    doc_freq: Counter = Counter()
    for p in pages:
        doc_freq.update(p["_terms"])
    total_counts: Counter = Counter()
    for p in pages:
        total_counts.update(p["_counts"])

    def term_score(t: str) -> float:
        parts = t.split()
        freq = sum(1 for p in pages if t in p["_terms"])
        return freq * (1.0 + 0.6 * (len(parts) - 1))

    common = [t for t, df in doc_freq.items() if df >= min_docs]
    # Prefer phrases; drop a shorter term contained in a kept phrase with the same doc frequency.
    common.sort(key=lambda t: (-term_score(t), -total_counts.get(t, 0), t))
    kept: list[str] = []
    for t in common:
        if any(f" {t} " in f" {k} " and doc_freq[k] == doc_freq[t] for k in kept):
            continue
        kept.append(t)
        if len(kept) >= top:
            break
    topics = subtopics(pages, min_docs)
    result = {
        "pages": [{k: v for k, v in p.items() if not k.startswith("_")} for p in pages],
        "median_word_count": int(statistics.median([p["word_count"] for p in pages])) if pages else 0,
        "common_terms": [{"term": t, "pages": doc_freq[t]} for t in kept],
        "common_subtopics": [{k: v for k, v in t.items() if not k.startswith("_")} for t in topics],
        "questions": sorted({q for p in pages for q in p["questions"] + p["faq_schema_questions"]}),
        "min_docs": min_docs,
    }
    if ours:
        mine = analyse_page(ours)
        my_keys = [norm_heading(i["text"]) for i in mine["outline"]]
        result["ours"] = {
            "file": mine["file"],
            "word_count": mine["word_count"],
            "missing_terms": [t["term"] for t in result["common_terms"] if t["term"] not in mine["_terms"]],
            "missing_subtopics": [
                t["subtopic"]
                for t in topics
                if not any(SequenceMatcher(None, t["_key"], k).ratio() >= 0.6 for k in my_keys if k)
            ],
        }
    return result


def render_md(r: dict) -> str:
    out = ["# Competitor outline analysis", ""]
    out.append(
        f"Pages analysed: {len(r['pages'])}; median word count: {r['median_word_count']}; terms/subtopics kept when used by >= {r['min_docs']} pages."
    )
    out.append("")
    for p in r["pages"]:
        out.append(f"## {p['file']} - {p['word_count']} words")
        out.append(f"Title: {p['title'] or '-'}")
        for item in p["outline"]:
            out.append(f"{'  ' * (item['level'] - 1)}- H{item['level']} {item['text']}")
        out.append("")
    out.append("## Common subtopics")
    out.extend([f"- {t['subtopic']} ({t['pages']} pages)" for t in r["common_subtopics"]] or ["- (none shared)"])
    out.append("")
    out.append("## Common terms and entities")
    out.append(", ".join(f"{t['term']} ({t['pages']})" for t in r["common_terms"]) or "(none)")
    out.append("")
    out.append("## Questions competitors answer")
    out.extend([f"- {q}" for q in r["questions"]] or ["- (none found)"])
    if "ours" in r:
        o = r["ours"]
        out += ["", f"## Gaps in {o['file']} ({o['word_count']} words)", "Missing subtopics:"]
        out.extend([f"- {s}" for s in o["missing_subtopics"]] or ["- none"])
        out.append("Missing terms: " + (", ".join(o["missing_terms"]) or "none"))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Extract outlines, shared subtopics, terms and questions from saved competitor pages.",
        epilog="Exit codes: 0 ok, 2 input error.",
    )
    ap.add_argument("pages", nargs="+", help="saved competitor HTML files (top-ranking pages)")
    ap.add_argument("--ours", help="your page or draft (HTML) to find gaps in")
    ap.add_argument("--min-docs", type=int, default=2, help="pages that must use a term/subtopic (default 2)")
    ap.add_argument("--top", type=int, default=40, help="number of common terms to keep (default 40)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    args = ap.parse_args(argv)
    try:
        res = compare(args.pages, args.ours, args.min_docs, args.top)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=2) if args.json else render_md(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
