---
name: core-web-vitals-triage
description: Interpret Lighthouse, PageSpeed Insights or Chrome UX Report (CrUX) JSON, rate LCP, INP, CLS, FCP, TTFB and TBT against the official thresholds, separate field data from lab data, and turn the audits into a ranked fix list mapped to the code that causes each problem. Use when the user shares a Lighthouse or PSI report, asks why a page is slow or fails Core Web Vitals, sees "Poor URLs" in Search Console's Core Web Vitals report, or wants performance budgets in CI.
license: MIT
---

# Core Web Vitals triage

Read the performance data correctly (field first, lab second), find the few fixes
that move the failing metric, and trace each one to the code or config behind it.

Paths below are relative to this skill's directory.

## When to use

- The user has a Lighthouse JSON (`lighthouse <url> --output=json --output-path=lh.json`), a PSI API response, or a CrUX API response
- "Why is my LCP/INP/CLS bad?", "we fail Core Web Vitals", "improve PageSpeed score"
- Setting performance gates in CI

## When not to use

- Server capacity or load testing - this is page-experience triage.
- Pure on-page content questions: `on-page-seo-review`.

## Get the data (ask the user, or run locally with permission)

- Lab: `npx lighthouse https://example.com/ --output=json --output-path=lh.json --only-categories=performance` (add `--preset=desktop` for desktop).
- PSI (lab + field in one): save `https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=<URL>&strategy=mobile` as JSON.
- CrUX (field only): POST to the CrUX API `records:queryRecord` with `{"url": "..."}` or `{"origin": "..."}`; needs an API key the user supplies - never ask them to paste it into chat; have them run the request.

## Workflow

1. **Triage:**
   `python3 scripts/cwv_triage.py report.json --json`
   Combine a lab report with separate field data: `--crux crux.json`. Exit 1 means a core metric is poor (`--fail-on needs-improvement` is stricter).
2. **Decide which metric to fix** using field data (p75 of real users, 28 days) when present. Google's assessment uses LCP, INP and CLS at p75; lab TBT is only a proxy for INP. With lab data only, say the pass/fail cannot be confirmed.
3. **Work the ranked list.** `opportunities` are sorted by estimated savings, weighted toward metrics that fail in the field. Check the diagnostics: the LCP element and layout-shift culprits name the exact nodes.
4. **Map each fix to the code** using [references/fixes.md](references/fixes.md): find the LCP image in the template, the render-blocking stylesheet in the layout, the third-party tag in the tag manager, the component that shifts. Propose concrete diffs.
5. **Verify:** re-run Lighthouse after the change (median of 3-5 runs; lab numbers vary), and tell the user field data needs up to 28 days to reflect a fix.

## Thresholds (p75)

| Metric | Good | Needs improvement | Poor |
| --- | --- | --- | --- |
| LCP | <= 2.5 s | <= 4.0 s | > 4.0 s |
| INP | <= 200 ms | <= 500 ms | > 500 ms |
| CLS | <= 0.1 | <= 0.25 | > 0.25 |
| FCP | <= 1.8 s | <= 3.0 s | > 3.0 s |
| TTFB | <= 0.8 s | <= 1.8 s | > 1.8 s |
| TBT (lab) | <= 200 ms | <= 600 ms | > 600 ms |

## Decision points

- **Field and lab disagree.** Trust field data for "is there a problem"; use lab data to find "why". Lab runs on one device and network; field data covers every visitor.
- **LCP:** split it into TTFB, resource load delay, load time and render delay (Lighthouse's LCP breakdown). Fix the largest part first: slow server, late-discovered image, heavy image, or render-blocking CSS/JS.
- **INP:** needs real interactions; lab TBT and long tasks point at the scripts. Look for heavy event handlers, hydration, and third-party scripts.
- **CLS:** almost always images/embeds without dimensions, injected banners/ads, or web fonts swapping.
- **Origin vs URL data.** PSI falls back to origin data for low-traffic URLs; say which one you used.

## Output

```
## Core Web Vitals triage - <URL> (<mobile|desktop>, <field source or "lab only">)
| Metric | Field p75 | Lab | Rating |
Assessment: <pass | fail | unknown (lab only)>

## Fix plan (highest impact first)
| # | Metric | Fix | Evidence (audit, savings, element) | Where in the code | Effort |

## Verify
<how to measure the change; when field data will update>
```

## Files

- `scripts/cwv_triage.py` - parser and ranker for Lighthouse JSON (v10+, including insight audits), PSI v5 and CrUX API responses (`--crux`, `--top`, `--fail-on`, `--json`).
- [references/fixes.md](references/fixes.md) - audit-by-audit causes and fixes, with framework-specific notes.
