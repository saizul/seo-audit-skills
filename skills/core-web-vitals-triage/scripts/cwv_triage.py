#!/usr/bin/env python3
"""Turn Lighthouse / PageSpeed Insights / CrUX JSON into a prioritised Core Web Vitals fix list.

  cwv_triage.py lighthouse-report.json            # `lighthouse URL --output=json`
  cwv_triage.py psi.json                          # PageSpeed Insights API v5 response
  cwv_triage.py crux.json                         # CrUX API queryRecord response
  cwv_triage.py lh.json --crux crux.json --top 8 --json

Rates each metric with the official thresholds (LCP, INP, CLS from field data;
LCP, CLS, TBT, FCP, Speed Index from lab data), then ranks Lighthouse audits and
insights by estimated metric savings, weighting metrics that fail in the field.

Exit status: 0 = nothing at or above --fail-on, 1 = a metric is rated at or
above --fail-on, 2 = input error. Python 3.9+ standard library only. No network.
"""

from __future__ import annotations

import argparse
import json
import sys

# metric -> (good upper bound, poor lower bound, unit)
THRESHOLDS = {
    "LCP": (2500, 4000, "ms"),
    "INP": (200, 500, "ms"),
    "CLS": (0.1, 0.25, ""),
    "FCP": (1800, 3000, "ms"),
    "TTFB": (800, 1800, "ms"),
    "TBT": (200, 600, "ms"),
    "SI": (3400, 5800, "ms"),
}
CORE = ("LCP", "INP", "CLS")
LAB_AUDITS = {
    "largest-contentful-paint": "LCP",
    "cumulative-layout-shift": "CLS",
    "total-blocking-time": "TBT",
    "first-contentful-paint": "FCP",
    "speed-index": "SI",
    "interaction-to-next-paint": "INP",
}
CRUX_KEYS = {
    "largest_contentful_paint": "LCP",
    "interaction_to_next_paint": "INP",
    "cumulative_layout_shift": "CLS",
    "first_contentful_paint": "FCP",
    "experimental_time_to_first_byte": "TTFB",
    "time_to_first_byte": "TTFB",
}
PSI_KEYS = {
    "LARGEST_CONTENTFUL_PAINT_MS": "LCP",
    "INTERACTION_TO_NEXT_PAINT": "INP",
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": "CLS",
    "FIRST_CONTENTFUL_PAINT_MS": "FCP",
    "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "TTFB",
}
# Which metric an audit mostly moves when Lighthouse gives no metricSavings.
AUDIT_METRIC = {
    "render-blocking-resources": "LCP",
    "render-blocking-insight": "LCP",
    "server-response-time": "LCP",
    "document-latency-insight": "LCP",
    "redirects": "LCP",
    "uses-rel-preconnect": "LCP",
    "prioritize-lcp-image": "LCP",
    "lcp-lazy-loaded": "LCP",
    "lcp-discovery-insight": "LCP",
    "lcp-phases-insight": "LCP",
    "lcp-breakdown-insight": "LCP",
    "uses-responsive-images": "LCP",
    "offscreen-images": "LCP",
    "modern-image-formats": "LCP",
    "uses-optimized-images": "LCP",
    "image-delivery-insight": "LCP",
    "efficient-animated-content": "LCP",
    "uses-text-compression": "LCP",
    "unused-css-rules": "LCP",
    "unminified-css": "LCP",
    "font-display": "FCP",
    "font-display-insight": "FCP",
    "network-dependency-tree-insight": "LCP",
    "unused-javascript": "TBT",
    "unminified-javascript": "TBT",
    "legacy-javascript": "TBT",
    "legacy-javascript-insight": "TBT",
    "duplicated-javascript": "TBT",
    "duplicated-javascript-insight": "TBT",
    "bootup-time": "TBT",
    "mainthread-work-breakdown": "TBT",
    "third-party-summary": "TBT",
    "third-parties-insight": "TBT",
    "long-tasks": "TBT",
    "dom-size": "TBT",
    "dom-size-insight": "TBT",
    "forced-reflow-insight": "INP",
    "inp-breakdown-insight": "INP",
    "interaction-to-next-paint-insight": "INP",
    "layout-shifts": "CLS",
    "layout-shift-elements": "CLS",
    "cls-culprits-insight": "CLS",
    "unsized-images": "CLS",
    "non-composited-animations": "CLS",
    "uses-long-cache-ttl": "LCP",
    "cache-insight": "LCP",
    "total-byte-weight": "LCP",
}
FIX_HINTS = {
    "LCP": "Make the LCP resource discoverable in the HTML, preload/fetchpriority=high it, never lazy-load it, cut TTFB and render-blocking CSS/JS.",
    "INP": "Break up long tasks, defer non-critical JS, yield to the main thread in event handlers, avoid layout thrashing.",
    "CLS": "Reserve space: width/height on images and embeds, min-height for ads and late content, font-display with matched fallbacks.",
    "TBT": "Ship less JavaScript: remove unused code, split bundles, delay third parties, move work off the main thread.",
    "FCP": "Inline critical CSS, remove render-blocking resources, speed up the server response.",
    "TTFB": "Cache HTML at the edge/CDN, reduce redirects, optimise backend queries.",
    "SI": "Improve FCP and LCP; paint meaningful content early.",
}
DIAGNOSTIC_DETAILS = (
    "largest-contentful-paint-element",
    "layout-shift-elements",
    "layout-shifts",
    "lcp-lazy-loaded",
    "lcp-phases-insight",
    "lcp-breakdown-insight",
    "cls-culprits-insight",
)


def rate(metric: str, value: float) -> str:
    good, poor, _ = THRESHOLDS[metric]
    if value <= good:
        return "good"
    if value > poor:
        return "poor"
    return "needs-improvement"


def fmt(metric: str, value: float | None) -> str:
    if value is None:
        return "-"
    if metric == "CLS":
        return f"{value:.3f}"
    return f"{value / 1000:.2f} s" if value >= 1000 else f"{round(value)} ms"


def parse_crux(record: dict) -> dict:
    out = {}
    for key, metric in CRUX_KEYS.items():
        m = record.get("metrics", {}).get(key)
        if not m:
            continue
        p75 = m.get("percentiles", {}).get("p75")
        if p75 is None:
            continue
        out[metric] = float(p75)
    return out


def parse_psi_field(exp: dict) -> dict:
    out = {}
    for key, metric in PSI_KEYS.items():
        m = exp.get("metrics", {}).get(key)
        if m and m.get("percentile") is not None:
            v = float(m["percentile"])
            out[metric] = v / 100 if metric == "CLS" else v
    return out


def parse_lighthouse(lhr: dict, top: int, field: dict) -> dict:
    audits = lhr.get("audits", {})
    lab = {}
    for aid, metric in LAB_AUDITS.items():
        a = audits.get(aid)
        if a and a.get("numericValue") is not None:
            lab[metric] = float(a["numericValue"])

    failing_field = {m for m, v in field.items() if m in THRESHOLDS and rate(m, v) != "good"}
    failing_lab = {m for m, v in lab.items() if rate(m, v) != "good"}
    opportunities = []
    for aid, a in audits.items():
        if aid in LAB_AUDITS or not isinstance(a, dict):
            continue
        score = a.get("score")
        mode = a.get("scoreDisplayMode", "")
        if mode in ("notApplicable", "manual", "informative") and not a.get("metricSavings"):
            continue
        if score is not None and score >= 0.9:
            continue
        details = a.get("details") or {}
        savings = dict(a.get("metricSavings") or {})
        ms = details.get("overallSavingsMs")
        if not savings and ms:
            savings = {AUDIT_METRIC.get(aid, "LCP"): ms}
        savings = {k: v for k, v in savings.items() if k in THRESHOLDS and v}
        if not savings and aid not in AUDIT_METRIC:
            continue
        impact = 0.0
        for metric, val in savings.items():
            # Normalise by the "poor" boundary so ms and unitless CLS are comparable,
            # then weight metrics that already fail (field data counts most).
            poor = THRESHOLDS[metric][1]
            weight = 3.0 if metric in failing_field else 2.0 if metric in failing_lab else 1.0
            if metric in CORE:
                weight *= 1.5
            impact += weight * float(val) / poor
        if not savings:
            impact = 0.05 * (1 - (score or 0))
        metrics = sorted(savings) or [AUDIT_METRIC[aid]]
        opportunities.append(
            {
                "id": aid,
                "title": a.get("title", aid),
                "display": a.get("displayValue", ""),
                "score": score,
                "metrics": metrics,
                "savings": {k: round(v, 3) if k == "CLS" else round(v) for k, v in savings.items()},
                "bytes": details.get("overallSavingsBytes"),
                "impact": round(impact, 3),
                "items": [summarise_item(i) for i in (details.get("items") or [])[:3]],
            }
        )
    opportunities.sort(key=lambda o: o["impact"], reverse=True)

    diagnostics = {}
    for aid in DIAGNOSTIC_DETAILS:
        a = audits.get(aid)
        if a and (a.get("details") or {}).get("items"):
            diagnostics[aid] = [summarise_item(i) for i in a["details"]["items"][:3]]

    perf = (lhr.get("categories", {}).get("performance") or {}).get("score")
    return {
        "url": lhr.get("finalDisplayedUrl") or lhr.get("finalUrl") or lhr.get("requestedUrl"),
        "lighthouse_version": lhr.get("lighthouseVersion"),
        "form_factor": (lhr.get("configSettings") or {}).get("formFactor"),
        "performance_score": None if perf is None else round(perf * 100),
        "lab": lab,
        "opportunities": opportunities[:top],
        "diagnostics": diagnostics,
    }


def summarise_item(item) -> str:
    if not isinstance(item, dict):
        return str(item)[:160]
    node = item.get("node") if isinstance(item.get("node"), dict) else None
    if node:
        return (node.get("snippet") or node.get("selector") or node.get("nodeLabel") or "")[:160]
    if "items" in item and isinstance(item["items"], list) and item["items"]:
        return summarise_item(item["items"][0])
    for key in ("url", "source", "label", "phase", "groupLabel", "entity"):
        v = item.get(key)
        if isinstance(v, str) and v:
            extra = item.get("wastedMs") or item.get("timing") or item.get("duration")
            return f"{v[:140]}" + (f" ({round(extra)} ms)" if isinstance(extra, (int, float)) else "")
        if isinstance(v, dict) and (v.get("text") or v.get("url")):
            return str(v.get("text") or v.get("url"))[:160]
    return json.dumps(item)[:160]


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def analyse(doc: dict, crux_doc: dict | None, top: int) -> dict:
    field: dict = {}
    field_source = None
    lhr = None
    if "record" in doc:
        field, field_source = parse_crux(doc["record"]), "crux"
    elif "lighthouseResult" in doc:
        lhr = doc["lighthouseResult"]
        exp = doc.get("loadingExperience") or {}
        if exp.get("metrics") and exp.get("origin_fallback") is not True:
            field, field_source = parse_psi_field(exp), "psi-url"
        elif (doc.get("originLoadingExperience") or {}).get("metrics"):
            field, field_source = parse_psi_field(doc["originLoadingExperience"]), "psi-origin"
    elif "audits" in doc:
        lhr = doc
    else:
        raise ValueError("unrecognised JSON: expected a Lighthouse report, a PSI v5 response or a CrUX record")
    if crux_doc is not None:
        if "record" not in crux_doc:
            raise ValueError("--crux file is not a CrUX API response (no 'record')")
        field, field_source = parse_crux(crux_doc["record"]), "crux"

    result = {"field_source": field_source, "field": {}, "lab": {}, "opportunities": [], "diagnostics": {}}
    for m, v in field.items():
        result["field"][m] = {"value": v, "rating": rate(m, v), "display": fmt(m, v)}
    if lhr is not None:
        lh = parse_lighthouse(lhr, top, field)
        result.update(
            {
                k: lh[k]
                for k in (
                    "url",
                    "lighthouse_version",
                    "form_factor",
                    "performance_score",
                    "opportunities",
                    "diagnostics",
                )
            }
        )
        result["lab"] = {m: {"value": v, "rating": rate(m, v), "display": fmt(m, v)} for m, v in lh["lab"].items()}
    elif "record" in doc:
        key = doc["record"].get("key", {})
        result["url"] = key.get("url") or key.get("origin")
        result["form_factor"] = key.get("formFactor")

    cwv_source = result["field"] if result["field"] else result["lab"]
    core = {m: cwv_source[m]["rating"] for m in CORE if m in cwv_source}
    if not result["field"] and "TBT" in result["lab"] and "INP" not in core:
        core["INP (TBT proxy)"] = result["lab"]["TBT"]["rating"]
    result["core_web_vitals"] = core
    result["assessment"] = (
        "pass"
        if core and all(v == "good" for v in core.values()) and result["field"]
        else ("fail" if any(v != "good" for v in core.values()) else "unknown")
    )
    result["next_steps"] = [FIX_HINTS[m.split()[0]] for m, v in core.items() if v != "good"]
    return result


def render_text(r: dict) -> str:
    out = [f"Core Web Vitals triage: {r.get('url') or '(unknown URL)'}"]
    meta = []
    if r.get("form_factor"):
        meta.append(r["form_factor"])
    if r.get("lighthouse_version"):
        meta.append(f"Lighthouse {r['lighthouse_version']}")
    if r.get("performance_score") is not None:
        meta.append(f"performance score {r['performance_score']}")
    if meta:
        out.append("  " + ", ".join(meta))
    out.append("")
    if r["field"]:
        out.append(f"Field data (p75, {r['field_source']}) - this is what Google uses:")
        for m, d in r["field"].items():
            out.append(f"  {m:<5} {d['display']:>9}  {d['rating']}")
    else:
        out.append("Field data: none. Lab data cannot confirm a pass; check CrUX/Search Console when traffic allows.")
    if r["lab"]:
        out.append("Lab data (Lighthouse, one run):")
        for m, d in r["lab"].items():
            out.append(f"  {m:<5} {d['display']:>9}  {d['rating']}")
    out.append("")
    out.append(
        f"Assessment: {r['assessment'].upper()}  " + ", ".join(f"{k}={v}" for k, v in r["core_web_vitals"].items())
    )
    if r["opportunities"]:
        out.append("")
        out.append("Prioritised fixes (highest estimated impact first):")
        for n, o in enumerate(r["opportunities"], 1):
            sav = ", ".join(f"{k} -{fmt(k, v)}" for k, v in o["savings"].items()) or "no estimate"
            out.append(
                f"  {n:>2}. [{'/'.join(o['metrics'])}] {o['title']} ({o['id']}) - {sav}"
                + (f"; {o['display']}" if o["display"] else "")
            )
            for item in o["items"]:
                out.append(f"        - {item}")
    if r["diagnostics"]:
        out.append("")
        out.append("Diagnostics:")
        for aid, items in r["diagnostics"].items():
            out.append(f"  {aid}:")
            out.extend(f"    - {i}" for i in items)
    if r["next_steps"]:
        out.append("")
        out.append("Where to start:")
        out.extend(f"  - {s}" for s in r["next_steps"])
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Prioritise Core Web Vitals fixes from Lighthouse, PSI or CrUX JSON.",
        epilog="Exit codes: 0 ok, 1 a core metric rated at/above --fail-on, 2 input error.",
    )
    ap.add_argument("report", help="Lighthouse JSON, PSI v5 JSON or CrUX API JSON")
    ap.add_argument("--crux", help="optional CrUX API JSON to use as field data")
    ap.add_argument("--top", type=int, default=10, help="number of fixes to list (default 10)")
    ap.add_argument("--fail-on", choices=("poor", "needs-improvement", "never"), default="poor")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)
    try:
        doc = load(args.report)
        crux = load(args.crux) if args.crux else None
        res = analyse(doc, crux, args.top)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=2) if args.json else render_text(res))
    if args.fail_on == "never":
        return 0
    bad = {"poor"} if args.fail_on == "poor" else {"poor", "needs-improvement"}
    return 1 if any(v in bad for v in res["core_web_vitals"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
