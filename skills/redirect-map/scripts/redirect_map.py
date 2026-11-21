#!/usr/bin/env python3
"""Map old URLs to new URLs for a site migration, with fuzzy matching and review flags.

  redirect_map.py old-urls.txt new-urls.txt                     # CSV report to stdout
  redirect_map.py old.csv new.csv --format nginx -o redirects.conf
  redirect_map.py old.txt new.txt --format apache --min-confidence 0.8

Inputs are text files (one URL or path per line) or CSV files (a 'url'/'address'
column, otherwise the first column). Matching, in order:

  exact    same normalised path (case, trailing slash, index files, .html/.php)
  slug     same last path segment, unique in the new site
  fuzzy    best similarity of slug and path tokens above --threshold
  parent   nearest new URL that is an ancestor directory of the old path
  none     no candidate: decide manually (410, a hub page, or restore content)

Output formats: csv (report), json, nginx (map block), apache (Redirect 301),
netlify/cloudflare (_redirects). Server formats include only rows at or above
--min-confidence and never redirect a URL to itself.

Exit status: 0 ok, 1 when --fail-on-unmatched and something is unmatched or
flagged for review, 2 input error. Python 3.9+ standard library only. No network.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from difflib import SequenceMatcher
from urllib.parse import unquote, urlsplit

STOP = {
    "a",
    "an",
    "and",
    "the",
    "of",
    "for",
    "to",
    "in",
    "on",
    "with",
    "or",
    "how",
    "what",
    "is",
    "your",
    "my",
    "html",
    "htm",
    "php",
    "asp",
    "aspx",
    "index",
    "www",
}
INDEX_FILES = ("index.html", "index.htm", "index.php", "default.aspx", "default.asp")
EXT = re.compile(r"\.(html?|php|aspx?|jsp|cfm)$", re.I)


def read_urls(path: str) -> list[str]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        text = fh.read()
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        return []
    if path.lower().endswith(".csv") or ("," in lines[0] and not lines[0].lower().startswith(("http", "/"))):
        rows = list(csv.reader(io.StringIO("\n".join(lines))))
        if rows[0] and rows[0][0].strip().lower().startswith(("http", "/")):
            idx, body = 0, rows  # no header row
        else:
            header = [h.strip().lower() for h in rows[0]]
            idx = next((header.index(c) for c in ("url", "address", "loc", "old", "new", "path") if c in header), 0)
            body = rows[1:]
        return [r[idx].strip() for r in body if len(r) > idx and r[idx].strip()]
    return [line.strip() for line in lines]


def path_of(url: str) -> str:
    p = urlsplit(
        url
        if re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I)
        else "http://x" + ("" if url.startswith("/") else "/") + url
    )
    return p.path or "/"


def norm_path(url: str) -> str:
    path = unquote(path_of(url)).lower()
    for idx in INDEX_FILES:
        if path.endswith("/" + idx):
            path = path[: -len(idx)]
    path = EXT.sub("", path)
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1:
        path = path.rstrip("/")
    return path or "/"


def slug(url: str) -> str:
    np = norm_path(url)
    return np.rsplit("/", 1)[-1] if np != "/" else ""


def tokens(text: str) -> set[str]:
    return {
        t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in STOP and not (t.isdigit() and len(t) <= 2)
    }


def similarity(old: str, new: str) -> float:
    so, sn = slug(old), slug(new)
    slug_ratio = SequenceMatcher(None, so, sn).ratio() if so and sn else 0.0
    to, tn = tokens(norm_path(old)), tokens(norm_path(new))
    jac = len(to & tn) / len(to | tn) if to | tn else 0.0
    so_t, sn_t = tokens(so), tokens(sn)
    slug_jac = len(so_t & sn_t) / len(so_t | sn_t) if so_t | sn_t else 0.0
    return round(0.4 * slug_ratio + 0.35 * slug_jac + 0.25 * jac, 3)


def build_map(old_urls: list[str], new_urls: list[str], threshold: float, review_margin: float) -> list[dict]:
    by_norm: dict[str, str] = {}
    by_slug: dict[str, list[str]] = {}
    for n in new_urls:
        by_norm.setdefault(norm_path(n), n)
        s = slug(n)
        if s:
            by_slug.setdefault(s, []).append(n)
    old_norms = {norm_path(o) for o in old_urls}
    rows = []
    for old in dict.fromkeys(old_urls):
        np = norm_path(old)
        row = {"old": old, "new": "", "method": "none", "confidence": 0.0, "review": True, "note": ""}
        if np in by_norm:
            row.update(new=by_norm[np], method="exact", confidence=1.0, review=False)
            if path_of(by_norm[np]) == path_of(old):
                row["note"] = "same path - no redirect needed unless the host changes"
        elif slug(old) and len(by_slug.get(slug(old), [])) == 1:
            row.update(new=by_slug[slug(old)][0], method="slug", confidence=0.9, review=False)
        else:
            scored = sorted(((similarity(old, n), n) for n in new_urls), reverse=True)
            if scored and scored[0][0] >= threshold:
                best, second = scored[0], scored[1] if len(scored) > 1 else (0.0, "")
                ambiguous = second[0] >= best[0] - review_margin
                row.update(
                    new=best[1], method="fuzzy", confidence=best[0], review=ambiguous or best[0] < threshold + 0.15
                )
                if ambiguous:
                    row["note"] = f"close alternative: {second[1]} ({second[0]})"
            else:
                parent = np
                while parent not in ("", "/"):
                    parent = parent.rsplit("/", 1)[0] or "/"
                    if parent in by_norm and parent != "/":
                        row.update(
                            new=by_norm[parent],
                            method="parent",
                            confidence=0.3,
                            review=True,
                            note="redirects to a parent section; check relevance or serve 410",
                        )
                        break
                if row["method"] == "none":
                    row["note"] = "no match: map manually, restore the content, or return 410"
                    if scored:
                        row["note"] += f" (closest: {scored[0][1]} {scored[0][0]})"
        if row["new"] and norm_path(row["new"]) in old_norms and norm_path(row["new"]) != np:
            row["note"] = (row["note"] + "; " if row["note"] else "") + "target is also an old URL - check for chains"
        rows.append(row)
    return rows


def target_for(url: str, keep_host: bool) -> str:
    """Path (plus query) of the target, or the full URL for cross-domain moves."""
    if keep_host and re.match(r"^https?://", url, re.I):
        return url
    query = urlsplit(url).query if re.match(r"^https?://", url, re.I) else ""
    return path_of(url) + (f"?{query}" if query else "")


def render(rows: list[dict], fmt: str, min_conf: float, absolute_targets: bool) -> str:
    if fmt == "json":
        return json.dumps(rows, indent=2)
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["old", "new", "method", "confidence", "review", "note"])
        for r in rows:
            w.writerow(
                [r["old"], r["new"], r["method"], f"{r['confidence']:.2f}", "yes" if r["review"] else "no", r["note"]]
            )
        return buf.getvalue()
    usable = [r for r in rows if r["new"] and r["confidence"] >= min_conf and path_of(r["old"]) != path_of(r["new"])]
    lines = []
    if fmt == "nginx":
        lines.append("# Generated by redirect_map.py - review before deploying.")
        lines.append("# In the http {} block:")
        lines.append("map $uri $redirect_target {")
        lines.append('    default "";')
        for r in usable:
            lines.append(f"    {nginx_quote(path_of(r['old']))} {nginx_quote(target_for(r['new'], absolute_targets))};")
        lines.append("}")
        lines.append("# In the server {} block:")
        lines.append("# if ($redirect_target) { return 301 $redirect_target; }")
    elif fmt == "apache":
        # RedirectMatch with an anchored pattern: plain "Redirect" is a prefix match, so
        # "Redirect /contact /contact/" would loop.
        lines.append("# Generated by redirect_map.py - review before deploying.")
        for r in usable:
            pattern = "^" + re.sub(r"([.+?*()\[\]{}|\\^$])", r"\\\1", path_of(r["old"])) + "$"
            lines.append(
                f"RedirectMatch 301 {apache_quote(pattern)} {apache_quote(target_for(r['new'], absolute_targets))}"
            )
    elif fmt == "netlify":
        # Netlify normalises trailing slashes before matching and Cloudflare Pages handles
        # them itself, so a slash-only rule would loop; leave those to the platform.
        lines.append("# Generated by redirect_map.py - review before deploying.")
        for r in usable:
            src, dst = path_of(r["old"]), target_for(r["new"], absolute_targets)
            if src.rstrip("/") == dst.rstrip("/"):
                lines.append(f"# skipped (trailing-slash only): {src} -> {dst}")
                continue
            lines.append(f"{src.replace(' ', '%20')} {dst.replace(' ', '%20')} 301")
    return "\n".join(lines) + "\n"


def nginx_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def apache_quote(s: str) -> str:
    return f'"{s}"' if re.search(r"\s", s) else s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build an old->new 301 redirect map with fuzzy matching.",
        epilog="Exit codes: 0 ok, 1 unmatched/review rows with --fail-on-unmatched, 2 input error.",
    )
    ap.add_argument("old", help="file with old URLs (txt or csv)")
    ap.add_argument("new", help="file with new URLs (txt or csv)")
    ap.add_argument("--format", choices=("csv", "json", "nginx", "apache", "netlify"), default="csv")
    ap.add_argument("--threshold", type=float, default=0.55, help="minimum fuzzy similarity 0-1 (default 0.55)")
    ap.add_argument(
        "--review-margin",
        type=float,
        default=0.05,
        help="flag fuzzy matches whose runner-up is this close (default 0.05)",
    )
    ap.add_argument(
        "--min-confidence", type=float, default=0.7, help="lowest confidence written to server formats (default 0.7)"
    )
    ap.add_argument("--absolute-targets", action="store_true", help="keep scheme+host in targets (cross-domain moves)")
    ap.add_argument("--fail-on-unmatched", action="store_true", help="exit 1 if any row is unmatched or needs review")
    ap.add_argument("-o", "--output", help="write to a file instead of stdout")
    args = ap.parse_args(argv)
    try:
        old, new = read_urls(args.old), read_urls(args.new)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not old or not new:
        print("error: both URL lists must be non-empty", file=sys.stderr)
        return 2
    rows = build_map(old, new, args.threshold, args.review_margin)
    out = render(rows, args.format, args.min_confidence, args.absolute_targets)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
    else:
        sys.stdout.write(out)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["method"]] = counts.get(r["method"], 0) + 1
    review = sum(1 for r in rows if r["review"])
    print(
        f"{len(rows)} old URLs: "
        + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        + f"; needs review={review}",
        file=sys.stderr,
    )
    return 1 if args.fail_on_unmatched and (review or counts.get("none")) else 0


if __name__ == "__main__":
    sys.exit(main())
