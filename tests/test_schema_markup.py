import io
import json

import pytest
from conftest import ROOT, load_script, run_json

v = load_script("schema-markup", "validate_jsonld")
TEMPLATES = sorted((ROOT / "skills" / "schema-markup" / "assets" / "templates").glob("*.json"))


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_templates_have_no_errors_or_warnings(path, capsys):
    code, data = run_json(v, [str(path), "--strict"], capsys)
    assert code == 0, data
    assert [i for i in data[0]["issues"] if i["severity"] != "notice"] == []


def test_templates_cover_core_types():
    names = {p.stem for p in TEMPLATES}
    assert {"article", "product", "faqpage", "localbusiness", "organization", "person", "breadcrumblist"} <= names


def messages(data):
    return [(i["severity"], i["message"]) for i in data[0]["issues"]]


def test_broken_html(fixtures, capsys):
    code, data = run_json(v, [str(fixtures / "schema-markup" / "broken.html")], capsys)
    assert code == 1
    assert data[0]["blocks"] == 3
    msgs = " | ".join(m for _, m in messages(data))
    assert "priceCurrency 'usd'" in msgs
    assert "availability 'InStockNow'" in msgs
    assert "price '$129'" in msgs
    assert "Standalone Review needs itemReviewed" in msgs
    assert "ListItem needs item" in msgs
    assert "datePublished '15/01/2026'" in msgs
    assert "Invalid JSON" in msgs
    assert "@context" in msgs
    assert "Missing required property: address" in msgs
    assert "author is a plain string" in msgs


def check(doc):
    return v.validate_text("t", json.dumps(doc))["issues"]


def test_product_needs_offer_review_or_rating():
    issues = check({"@context": "https://schema.org", "@type": "Product", "name": "X"})
    assert any("offers or review or aggregateRating" in i["message"] and i["severity"] == "error" for i in issues)


def test_aggregate_rating_range():
    doc = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "X",
        "aggregateRating": {"@type": "AggregateRating", "ratingValue": 7, "reviewCount": 3},
    }
    assert any("outside" in i["message"] for i in check(doc))
    doc["aggregateRating"]["bestRating"] = 10
    assert not any("outside" in i["message"] for i in check(doc))


def test_faq_items_must_be_questions():
    doc = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Answer", "text": "x"}]}
    assert any("must be a Question" in i["message"] for i in check(doc))


def test_event_online_needs_virtual_location():
    doc = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": "Webinar",
        "startDate": "2026-05-01T10:00:00+00:00",
        "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
        "location": {"@type": "Place", "name": "x", "address": "y"},
    }
    assert any("VirtualLocation" in i["message"] for i in check(doc))


def test_video_duration_format():
    doc = {
        "@context": "https://schema.org",
        "@type": "VideoObject",
        "name": "v",
        "thumbnailUrl": "https://e.com/t.jpg",
        "uploadDate": "2026-01-01",
        "duration": "1:33",
    }
    assert any("duration" in i["message"] for i in check(doc))
    doc["duration"] = "PT1M33S"
    assert not any("duration" in i["message"] for i in check(doc))


def test_graph_and_id_references_ok():
    doc = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": "https://e.com/#org",
                "name": "E",
                "url": "https://e.com/",
                "logo": "https://e.com/l.png",
                "sameAs": ["https://x.com/e"],
            },
            {
                "@type": "WebSite",
                "name": "E",
                "url": "https://e.com/",
                "alternateName": "E",
                "publisher": {"@id": "https://e.com/#org"},
            },
        ],
    }
    assert [i for i in check(doc) if i["severity"] == "error"] == []


def test_local_business_subtype_uses_parent_rule():
    issues = check({"@context": "https://schema.org", "@type": "Dentist", "name": "Smile"})
    assert any("address" in i["message"] and i["severity"] == "error" for i in issues)


def test_no_blocks_and_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("<html><body>nothing</body></html>"))
    assert v.main(["-"]) == 0
    assert "No JSON-LD" in capsys.readouterr().out


def test_list_types(capsys):
    assert v.main(["--list-types"]) == 0
    out = capsys.readouterr().out
    assert "Product" in out and "LocalBusiness subtypes" in out


def test_missing_file_exit_2(capsys):
    assert v.main(["/nonexistent.json"]) == 2
