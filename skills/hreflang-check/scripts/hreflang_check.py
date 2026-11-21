#!/usr/bin/env python3
"""Audit hreflang annotations offline: codes, return links, self-references, canonicals.

Input (pick one):
  hreflang_check.py --html-dir build/ --base-url https://example.com [--clean-urls]
  hreflang_check.py --sitemap sitemap.xml          # <xhtml:link rel="alternate" hreflang=...>
  hreflang_check.py --csv annotations.csv          # columns: url,hreflang,href

Checks: valid ISO 639-1 language + optional ISO 15924 script + ISO 3166-1 alpha-2
region (or x-default), absolute URLs, self-reference, reciprocal (return) links,
one URL per code, consistent clusters, hreflang to non-canonical or missing pages,
and <html lang> agreement.

Exit status: 0 = no errors, 1 = errors (or warnings with --strict), 2 = input error.
Python 3.9+ standard library only. No network access.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

LANGS = set(
    """
    aa ab ae af ak am an ar as av ay az ba be bg bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de
    dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia
    id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo
    lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl
    ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk
    tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu
    """.split()
)
REGIONS = set(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS
    BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE
    EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM
    HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC
    LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA
    NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW
    SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO
    TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
    """.split()
)
# Country codes and withdrawn ISO codes often used by mistake as language codes.
LANG_FIXES = {
    "jp": "ja",
    "cn": "zh",
    "cz": "cs",
    "dk": "da",
    "gr": "el",
    "iw": "he",
    "in": "id",
    "ji": "yi",
    "ua": "uk",
    "vn": "vi",
    "al": "sq",
    "rs": "sr",
}
# Valid but rare languages whose code is usually a country code typed by mistake.
SUSPICIOUS = {
    "kr": "Kanuri (Korean is 'ko')",
    "se": "Northern Sami (Swedish is 'sv')",
    "br": "Breton (Brazilian Portuguese is 'pt-BR')",
    "my": "Burmese (Malay is 'ms', Malaysia is '-MY')",
    "si": "Sinhala (Slovenian is 'sl')",
    "ee": "Ewe (Estonian is 'et')",
}
REGION_FIXES = {
    "UK": "GB",
    "EN": "US or GB",
    "EU": "(no EU region; list countries)",
    "LA": "(LA is Laos)",
    "419": "a specific country (Google does not support UN M.49 codes such as 419)",
}


def read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def check_code(code: str) -> tuple[str, str]:
    """Return (severity, message) where severity is '' for a valid code."""
    c = code.strip()
    if c.lower() == "x-default":
        return "", ""
    parts = c.replace("_", "-").split("-")
    if "_" in c:
        return "error", f"'{code}' uses an underscore; use a hyphen ({c.replace('_', '-')})."
    lang = parts[0].lower()
    if lang in LANG_FIXES:
        return (
            "error",
            f"'{code}': '{lang}' is not an ISO 639-1 language (country or withdrawn code); did you mean '{LANG_FIXES[lang]}'?",
        )
    if len(parts) == 1 and parts[0].upper() in REGIONS and lang not in LANGS:
        return (
            "error",
            f"'{code}' looks like a region only; hreflang needs a language first (e.g. en-{parts[0].upper()}).",
        )
    if lang not in LANGS:
        if len(lang) == 3 and lang.isalpha():
            return (
                "warning",
                f"'{code}': 3-letter language code; Google expects ISO 639-1 (2 letters) where one exists.",
            )
        return "error", f"'{code}': unknown ISO 639-1 language '{lang}'."
    rest = parts[1:]
    if rest and len(rest[0]) == 4 and rest[0].isalpha():
        rest = rest[1:]  # script subtag such as Hant
    if len(rest) > 1:
        return "error", f"'{code}': too many subtags; use language[-Script][-REGION]."
    if rest:
        region = rest[0].upper()
        if region in REGION_FIXES:
            return "error", f"'{code}': '{rest[0]}' is not a valid region; use {REGION_FIXES[region]}."
        if region not in REGIONS:
            return "error", f"'{code}': unknown ISO 3166-1 alpha-2 region '{rest[0]}'."
    if lang in SUSPICIOUS:
        return "warning", f"'{code}': '{lang}' is {SUSPICIOUS[lang]}; check this is intended."
    return "", ""


class HreflangParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.canonical = ""
        self.alternates: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "link":
            rels = a.get("rel", "").lower().split()
            if "canonical" in rels and not self.canonical:
                self.canonical = a.get("href", "").strip()
            elif "alternate" in rels and "hreflang" in a:
                self.alternates.append((a["hreflang"].strip(), a.get("href", "").strip()))


def norm(url: str) -> str:
    p = urlsplit(url)
    path = p.path or "/"
    return f"{p.scheme.lower()}://{p.netloc.lower()}{path}" + (f"?{p.query}" if p.query else "")


def file_to_url(rel: str, base: str, clean: bool) -> str:
    rel = rel.replace(os.sep, "/")
    if rel == "index.html":
        path = "/"
    elif rel.endswith("/index.html"):
        path = "/" + rel[: -len("index.html")]
    elif clean and rel.endswith(".html"):
        path = "/" + rel[:-5]
    else:
        path = "/" + rel
    return base.rstrip("/") + path


def load_html(root: str, base: str, clean: bool) -> dict:
    pages = {}
    for dirpath, _d, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith((".html", ".htm")):
                continue
            full = os.path.join(dirpath, name)
            url = file_to_url(os.path.relpath(full, root), base, clean)
            p = HreflangParser()
            with open(full, encoding="utf-8", errors="replace") as fh:
                p.feed(fh.read())
            pages[norm(url)] = {
                "url": url,
                "lang": p.lang,
                "canonical": norm(urljoin(url, p.canonical)) if p.canonical else None,
                "alternates": [(c, h) for c, h in p.alternates],
            }
    return pages


def load_sitemap(path: str) -> dict:
    data = read_file_bytes(path)
    if b"<!DOCTYPE" in data[:2048].upper():
        raise ValueError("sitemap declares a DOCTYPE; refusing to parse")
    root = ET.fromstring(data)
    ns = root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""
    q = (lambda n: f"{{{ns}}}{n}") if ns else (lambda n: n)
    pages = {}
    for u in root.findall(q("url")):
        loc = (u.findtext(q("loc")) or "").strip()
        if not loc:
            continue
        alts = [
            (link.get("hreflang", ""), link.get("href", ""))
            for link in u.findall("{http://www.w3.org/1999/xhtml}link")
            if link.get("rel") == "alternate"
        ]
        pages[norm(loc)] = {"url": loc, "lang": None, "canonical": None, "alternates": alts}
    return pages


def load_csv(path: str) -> dict:
    pages: dict = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        cols = {c.lower().strip(): c for c in reader.fieldnames or []}
        need = [k for k in ("url", "hreflang", "href") if k not in cols]
        if need:
            raise ValueError(f"CSV is missing columns {need}; expected url,hreflang,href")
        for row in reader:
            url = (row[cols["url"]] or "").strip()
            if not url:
                continue
            page = pages.setdefault(norm(url), {"url": url, "lang": None, "canonical": None, "alternates": []})
            page["alternates"].append(((row[cols["hreflang"]] or "").strip(), (row[cols["href"]] or "").strip()))
    return pages


def audit(pages: dict) -> list[dict]:
    issues: list[dict] = []

    def add(sev: str, url: str, msg: str) -> None:
        issues.append({"severity": sev, "url": url, "message": msg})

    annotated = {k: v for k, v in pages.items() if v["alternates"]}
    resolved: dict[str, dict[str, str]] = {}
    display: dict[str, str] = {}
    for key, page in annotated.items():
        url = page["url"]
        codes: dict[str, str] = {}
        for code, href in page["alternates"]:
            if not href:
                add("error", url, f"hreflang='{code}' has an empty href.")
                continue
            if not urlsplit(href).scheme:
                add("error", url, f"hreflang='{code}' href '{href}' is relative; Google requires absolute URLs.")
            sev, msg = check_code(code)
            if sev:
                add(sev, url, msg)
            target = norm(urljoin(url, href))
            lc = code.lower()
            if lc in codes and codes[lc] != target:
                add("error", url, f"hreflang='{code}' points to two URLs: {codes[lc]} and {target}.")
            codes.setdefault(lc, target)
            display.setdefault(lc, code)
        resolved[key] = codes
        if key not in codes.values():
            add("warning", url, "No self-referencing hreflang; each page should list itself.")
        if "x-default" not in codes:
            add("notice", url, "No x-default; add one for users whose language you do not target.")
        if page.get("canonical") and page["canonical"] != key:
            add(
                "error",
                url,
                f"Page has hreflang but canonicalises to {page['canonical']}; hreflang belongs on canonical URLs only.",
            )
        if page.get("lang") is not None:
            self_codes = [c for c, t in codes.items() if t == key and c != "x-default"]
            if (
                page["lang"]
                and self_codes
                and not any(page["lang"].lower().split("-")[0] == c.split("-")[0] for c in self_codes)
            ):
                add("warning", url, f"<html lang='{page['lang']}'> disagrees with its own hreflang {self_codes}.")

    for key, codes in resolved.items():
        url = pages[key]["url"]
        for lc, target in codes.items():
            code = display.get(lc, lc)
            if target == key:
                continue
            if target not in pages:
                add(
                    "warning",
                    url,
                    f"hreflang='{code}' target {target} is not in the dataset (missing page or not crawled).",
                )
                continue
            tpage = pages[target]
            if tpage.get("canonical") and tpage["canonical"] != target:
                add("error", url, f"hreflang='{code}' points to {target}, which canonicalises to {tpage['canonical']}.")
            back = resolved.get(target, {})
            if key not in back.values():
                add("error", url, f"No return link: {target} (hreflang='{code}') does not link back to this page.")

    # Cluster consistency: pages that reference each other should carry the same set.
    seen: set[str] = set()
    for key, codes in resolved.items():
        if key in seen:
            continue
        cluster = {t for t in codes.values() if t in resolved} | {key}
        seen |= cluster
        sets = {k: frozenset(resolved[k].items()) for k in cluster}
        if len(set(sets.values())) > 1:
            add(
                "warning",
                pages[key]["url"],
                f"Cluster of {len(cluster)} pages has inconsistent annotation sets; generate hreflang from one shared mapping.",
            )
    return issues


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Offline hreflang audit for HTML builds, sitemaps or CSV exports.",
        epilog="Exit codes: 0 ok, 1 errors (or warnings with --strict), 2 input error.",
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--html-dir", help="directory of built HTML files (needs --base-url)")
    src.add_argument("--sitemap", help="XML sitemap with xhtml:link annotations")
    src.add_argument("--csv", help="CSV with url,hreflang,href columns")
    src.add_argument("--code", action="append", help="just validate hreflang code(s), e.g. --code en-UK")
    ap.add_argument("--base-url", default="", help="production origin for --html-dir")
    ap.add_argument("--clean-urls", action="store_true", help="page.html is served as /page")
    ap.add_argument("--strict", action="store_true", help="warnings also fail")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)

    if args.code:
        results = []
        for c in args.code:
            sev, msg = check_code(c)
            results.append({"code": c, "valid": sev != "error", "severity": sev or "ok", "message": msg})
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                print(f"{r['code']:<12} {r['severity'].upper():<8} {r['message']}")
        return 1 if any(not r["valid"] for r in results) else 0

    try:
        if args.html_dir:
            if not args.base_url:
                ap.error("--html-dir needs --base-url")
            pages = load_html(args.html_dir, args.base_url, args.clean_urls)
        elif args.sitemap:
            pages = load_sitemap(args.sitemap)
        else:
            pages = load_csv(args.csv)
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    issues = audit(pages)
    annotated = sum(1 for p in pages.values() if p["alternates"])
    if args.json:
        print(json.dumps({"pages": len(pages), "annotated_pages": annotated, "issues": issues}, indent=2))
    else:
        print(f"hreflang audit: {len(pages)} pages, {annotated} with annotations")
        grouped = defaultdict(list)
        for i in issues:
            grouped[i["severity"]].append(i)
        for sev in ("error", "warning", "notice"):
            for i in grouped[sev]:
                print(f"  {sev.upper():<8} {i['url']}: {i['message']}")
        if not issues:
            print("  OK - no issues")
    bad = {"error", "warning"} if args.strict else {"error"}
    return 1 if any(i["severity"] in bad for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
