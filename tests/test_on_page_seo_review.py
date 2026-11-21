import io

import pytest
from conftest import load_script, run_json

onpage = load_script("on-page-seo-review", "onpage_review")


def check(data, cid):
    return next(c for c in data["checks"] if c["id"] == cid)


def test_good_page_scores_high(fixtures, capsys):
    page = str(fixtures / "on-page-seo-review" / "good.html")
    code, data = run_json(onpage, [page, "--keyword", "trail running shoes"], capsys)
    assert code == 0
    assert data["score"] >= 90
    assert data["url"] == "https://shop.example.com/guides/trail-running-shoes"
    assert data["keyword"]["placements"]["title"] is True
    assert data["keyword"]["placements"]["h1"] is True
    assert data["keyword"]["placements"]["url"] is True
    assert data["facts"]["internal_links"] == 3
    assert data["facts"]["external_links"] == 1
    assert check(data, "heading-outline")["status"] == "pass"


def test_bad_page_fails(fixtures, capsys):
    page = str(fixtures / "on-page-seo-review" / "bad.html")
    code, data = run_json(onpage, [page], capsys)
    assert code == 1
    assert data["score"] < 50
    assert check(data, "indexable")["status"] == "fail"
    assert check(data, "h1")["status"] == "warn"
    assert "H1 -> H4" in check(data, "heading-outline")["message"]
    assert check(data, "image-alt")["status"] == "fail"
    assert check(data, "anchor-text")["status"] == "warn"
    assert check(data, "meta-description")["status"] == "fail"


def test_min_score_controls_exit(fixtures, capsys):
    page = str(fixtures / "on-page-seo-review" / "bad.html")
    assert onpage.main([page, "--min-score", "0"]) == 0
    capsys.readouterr()


def test_keyword_missing_and_stuffing():
    html = "<html><head><title>Cats</title></head><body><h1>Cats</h1><p>" + "dog food " * 50 + "</p></body></html>"
    res = onpage.review(html, keyword="dog food")
    ids = {c["id"]: c["status"] for c in res["checks"]}
    assert ids["keyword-title"] == "fail"
    assert ids["keyword-first-100-words"] == "pass"
    assert ids["keyword-stuffing"] == "warn"


def test_phrase_matching_is_word_based():
    assert onpage.contains_phrase("Best Trail-Running Shoes", "trail-running shoes")
    assert not onpage.contains_phrase("restaurants", "rest")


def test_url_requires_fetch_flag(capsys):
    assert onpage.main(["https://example.com/"]) == 2
    assert "--fetch" in capsys.readouterr().err


def test_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("<html><head><title>x</title></head><body></body></html>"))
    code = onpage.main(["-", "--min-score", "0"])
    assert code == 0
    assert "On-page SEO score" in capsys.readouterr().out


@pytest.mark.parametrize("title,status", [("Short", "warn"), ("A" * 45, "pass"), ("B" * 80, "warn")])
def test_title_length(title, status):
    res = onpage.review(f"<html><head><title>{title}</title></head><body></body></html>")
    assert next(c for c in res["checks"] if c["id"] == "title")["status"] == status
