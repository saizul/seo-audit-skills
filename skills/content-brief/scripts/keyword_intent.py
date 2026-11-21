#!/usr/bin/env python3
"""Classify keywords by search intent and cluster them into topics (rule-based, offline).

  keyword_intent.py keywords.txt                    # one keyword per line
  keyword_intent.py keywords.csv --brand acme       # CSV with a keyword column (+ optional volume)
  keyword_intent.py --kw "best trail shoes" --kw "how to clean trail shoes"

Intent labels: informational, commercial, transactional, navigational, local.
Each keyword gets the modifiers that triggered the label, a suggested page type,
and a cluster id; clusters group keywords that share their core terms.

The rules are a fast first pass. Confirm the intent of money keywords by looking
at the live results page (what ranks is the real intent).
Exit status: 0 ok, 2 input error. Python 3.9+ standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys

MODIFIERS = {
    "transactional": [
        "buy",
        "order",
        "purchase",
        "price",
        "prices",
        "pricing",
        "cost",
        "cheap",
        "cheapest",
        "deal",
        "deals",
        "discount",
        "coupon",
        "promo",
        "sale",
        "for sale",
        "shop",
        "subscribe",
        "download",
        "free trial",
        "quote",
        "hire",
        "booking",
        "rent",
    ],
    "commercial": [
        "best",
        "top",
        "review",
        "reviews",
        "vs",
        "versus",
        "compare",
        "comparison",
        "alternative",
        "alternatives",
        "rated",
        "recommended",
        "which",
        "worth it",
        "pros and cons",
    ],
    "local": ["near me", "nearby", "open now", "in my area", "directions", "hours"],
    "navigational": [
        "login",
        "log in",
        "sign in",
        "signin",
        "dashboard",
        "official site",
        "contact",
        "customer service",
        "phone number",
    ],
    "informational": [
        "how",
        "what",
        "why",
        "when",
        "where",
        "who",
        "guide",
        "tutorial",
        "tips",
        "ideas",
        "examples",
        "meaning",
        "definition",
        "define",
        "learn",
        "steps",
        "checklist",
        "template",
        "is",
        "are",
        "can",
        "does",
        "do",
        "should",
        "ways",
        "benefits",
        "history",
        "explained",
    ],
}
PRIORITY = ["local", "navigational", "transactional", "commercial", "informational"]
PAGE_TYPE = {
    "informational": "guide / how-to article, FAQ or glossary entry",
    "commercial": "comparison, 'best X' list or in-depth review",
    "transactional": "product, category or pricing page",
    "navigational": "brand page (homepage, login, support) - usually not a content target",
    "local": "location / service-area page with NAP and map",
}
STOP = set(
    """
    a an and are at be best can do does for how in is me my near of on or our the to top versus vs
    what when where which who why with without your
    """.split()
)


def normalise(kw: str) -> str:
    return " ".join(re.findall(r"[\w'+.-]+", kw.lower()))


def has(phrase: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", text) is not None


def classify(keyword: str, brands: list[str]) -> dict:
    text = normalise(keyword)
    hits: dict[str, list[str]] = {}
    for intent, mods in MODIFIERS.items():
        found = [m for m in mods if has(m, text)]
        if found:
            hits[intent] = found
    for b in brands:
        if b and has(b.lower(), text):
            hits.setdefault("navigational", []).append(f"brand:{b}")
    if "navigational" in hits and any(h.startswith("brand:") for h in hits["navigational"]):
        # "acme vs globex" or "acme price" are not pure navigation.
        if "commercial" in hits or "transactional" in hits or "informational" in hits:
            hits["navigational"] = [h for h in hits["navigational"] if not h.startswith("brand:")] or []
            if not hits["navigational"]:
                del hits["navigational"]
    if text.endswith("?") or (text.split() and text.split()[0] in {"how", "what", "why", "is", "can", "does"}):
        hits.setdefault("informational", [])
    primary = next((i for i in PRIORITY if i in hits), None)
    if primary is None:
        # Bare head terms ("trail running shoes") usually show mixed, product-led results.
        primary = "commercial"
        confidence = "low"
    else:
        confidence = "high" if len(hits) == 1 else "medium"
    return {
        "keyword": keyword,
        "intent": primary,
        "secondary": [i for i in PRIORITY if i in hits and i != primary],
        "modifiers": sorted({m for v in hits.values() for m in v}),
        "confidence": confidence,
        "page_type": PAGE_TYPE[primary],
    }


def core_terms(keyword: str) -> frozenset:
    words = [w for w in normalise(keyword).split() if w not in STOP]
    mods = {m for v in MODIFIERS.values() for m in v if " " not in m}
    core = [w.rstrip("s") if len(w) > 3 else w for w in words if w not in mods]
    return frozenset(core or words)


def cluster(rows: list[dict], threshold: float) -> None:
    # One cluster = one page candidate, so keywords only cluster with the same intent.
    clusters: list[tuple[frozenset, int, str]] = []
    for r in sorted(rows, key=lambda r: -(r.get("volume") or 0)):
        terms = core_terms(r["keyword"])
        best, best_score = None, 0.0
        for cterms, cid, cintent in clusters:
            if cintent != r["intent"]:
                continue
            inter = len(terms & cterms)
            score = inter / len(terms | cterms) if terms | cterms else 0
            if score > best_score:
                best, best_score = cid, score
        if best is not None and best_score >= threshold:
            r["cluster"] = best
        else:
            cid = len(clusters) + 1
            clusters.append((terms, cid, r["intent"]))
            r["cluster"] = cid
    heads = {}
    for r in sorted(rows, key=lambda r: (-(r.get("volume") or 0), len(r["keyword"]))):
        heads.setdefault(r["cluster"], r["keyword"])
    for r in rows:
        r["cluster_head"] = heads[r["cluster"]]


def read_keywords(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        text = fh.read()
    if path.endswith(".csv") or ("," in text.splitlines()[0] if text.strip() else False):
        reader = csv.DictReader(text.splitlines())
        cols = {c.lower().strip(): c for c in reader.fieldnames or []}
        kcol = cols.get("keyword") or cols.get("query") or cols.get("keywords") or (reader.fieldnames or [None])[0]
        vcol = cols.get("volume") or cols.get("search volume") or cols.get("impressions")
        out = []
        for row in reader:
            kw = (row.get(kcol) or "").strip()
            if not kw:
                continue
            vol = None
            if vcol and row.get(vcol):
                try:
                    vol = int(float(row[vcol].replace(",", "")))
                except ValueError:
                    vol = None
            out.append({"keyword": kw, "volume": vol})
        return out
    return [
        {"keyword": line.strip(), "volume": None}
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Rule-based search-intent classification and keyword clustering.",
        epilog="Exit codes: 0 ok, 2 input error.",
    )
    ap.add_argument("file", nargs="?", help="text file (one keyword per line) or CSV with a keyword column")
    ap.add_argument("--kw", action="append", default=[], help="keyword (repeatable)")
    ap.add_argument("--brand", action="append", default=[], help="brand name(s) that signal navigational intent")
    ap.add_argument("--threshold", type=float, default=0.5, help="cluster similarity 0-1 (default 0.5)")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)
    try:
        rows = read_keywords(args.file) if args.file else []
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rows += [{"keyword": k, "volume": None} for k in args.kw]
    if not rows:
        ap.error("no keywords given")
    results = []
    for r in rows:
        res = classify(r["keyword"], args.brand)
        res["volume"] = r["volume"]
        results.append(res)
    cluster(results, args.threshold)
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    by_cluster: dict[int, list[dict]] = {}
    for r in results:
        by_cluster.setdefault(r["cluster"], []).append(r)
    for cid, items in sorted(by_cluster.items()):
        print(f"Cluster {cid}: {items[0]['cluster_head']}  [{items[0]['intent']} -> {items[0]['page_type']}]")
        for i in items:
            vol = f"{i['volume']:>7}" if i["volume"] is not None else "      -"
            mods = ",".join(i["modifiers"]) or "-"
            print(f"  {vol}  {i['intent']:<13} {i['confidence']:<6} {i['keyword']}  (modifiers: {mods})")
        if any(i["confidence"] == "low" for i in items):
            print("  note: low-confidence intent - check what ranks on the results page")
    return 0


if __name__ == "__main__":
    sys.exit(main())
