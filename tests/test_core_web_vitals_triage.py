import json

import pytest
from conftest import load_script, run_json

cwv = load_script("core-web-vitals-triage", "cwv_triage")


@pytest.mark.parametrize(
    "metric,value,rating",
    [
        ("LCP", 2500, "good"),
        ("LCP", 2501, "needs-improvement"),
        ("LCP", 4001, "poor"),
        ("INP", 200, "good"),
        ("INP", 501, "poor"),
        ("CLS", 0.1, "good"),
        ("CLS", 0.26, "poor"),
        ("TTFB", 900, "needs-improvement"),
    ],
)
def test_thresholds(metric, value, rating):
    assert cwv.rate(metric, value) == rating


def test_lighthouse_report(fixtures, capsys):
    code, data = run_json(cwv, [str(fixtures / "core-web-vitals-triage" / "lighthouse.json")], capsys)
    assert code == 1
    assert data["performance_score"] == 42
    assert data["form_factor"] == "mobile"
    assert data["field"] == {}
    assert data["lab"]["LCP"]["rating"] == "poor"
    assert data["core_web_vitals"]["INP (TBT proxy)"] == "poor"
    ids = [o["id"] for o in data["opportunities"]]
    assert ids[0] == "render-blocking-resources"
    assert "uses-text-compression" not in ids  # passing audit
    assert "is-on-https" not in ids  # not a performance audit
    srt = next(o for o in data["opportunities"] if o["id"] == "server-response-time")
    assert srt["savings"] == {"LCP": 900}  # inferred from overallSavingsMs
    assert "largest-contentful-paint-element" in data["diagnostics"]
    assert 'loading="lazy"' in data["diagnostics"]["largest-contentful-paint-element"][0]


def test_top_limits_output(fixtures, capsys):
    _, data = run_json(cwv, [str(fixtures / "core-web-vitals-triage" / "lighthouse.json"), "--top", "2"], capsys)
    assert len(data["opportunities"]) == 2


def test_psi_uses_field_data(fixtures, capsys):
    code, data = run_json(cwv, [str(fixtures / "core-web-vitals-triage" / "psi.json")], capsys)
    assert code == 1  # CLS poor in the field
    assert data["field_source"] == "psi-url"
    assert data["field"]["CLS"]["value"] == pytest.approx(0.28)
    assert data["core_web_vitals"] == {"LCP": "needs-improvement", "INP": "good", "CLS": "poor"}
    assert data["assessment"] == "fail"
    # CLS fails in the field, so the CLS fix outranks the lab-only unused-JS fix.
    ids = [o["id"] for o in data["opportunities"]]
    assert ids.index("unsized-images") < ids.index("unused-javascript")


def test_crux_pass(fixtures, capsys):
    code, data = run_json(cwv, [str(fixtures / "core-web-vitals-triage" / "crux.json")], capsys)
    assert code == 0
    assert data["assessment"] == "pass"
    assert data["field"]["CLS"]["value"] == 0.05
    assert data["url"] == "https://example.com"


def test_crux_overrides_field(fixtures, capsys):
    d = fixtures / "core-web-vitals-triage"
    code, data = run_json(cwv, [str(d / "lighthouse.json"), "--crux", str(d / "crux.json")], capsys)
    assert data["field_source"] == "crux"
    assert data["assessment"] == "pass"
    assert code == 0


def test_fail_on_levels(fixtures, capsys):
    psi = str(fixtures / "core-web-vitals-triage" / "psi.json")
    assert cwv.main([psi, "--fail-on", "never"]) == 0
    fast = str(fixtures / "core-web-vitals-triage" / "lighthouse-fast.json")
    assert cwv.main([fast, "--fail-on", "needs-improvement"]) == 0
    out = capsys.readouterr().out
    assert "UNKNOWN" in out  # lab-only data can't confirm a pass


def test_unknown_json(fixtures, tmp_path, capsys):
    assert cwv.main([str(fixtures / "core-web-vitals-triage" / "unknown.json")]) == 2
    bad = tmp_path / "x.json"
    bad.write_text("{not json")
    assert cwv.main([str(bad)]) == 2
    capsys.readouterr()


def test_text_render(fixtures, capsys):
    cwv.main([str(fixtures / "core-web-vitals-triage" / "lighthouse.json")])
    out = capsys.readouterr().out
    assert "Prioritised fixes" in out and "Where to start" in out


def test_insight_audits_with_metric_savings():
    lhr = {
        "audits": {
            "largest-contentful-paint": {"numericValue": 3000},
            "lcp-discovery-insight": {
                "title": "LCP request discovery",
                "score": 0,
                "scoreDisplayMode": "metricSavings",
                "metricSavings": {"LCP": 600},
                "details": {"type": "checklist"},
            },
        }
    }
    res = cwv.analyse(json.loads(json.dumps(lhr)), None, 5)
    assert res["opportunities"][0]["id"] == "lcp-discovery-insight"
