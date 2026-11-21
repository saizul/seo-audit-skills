from conftest import load_script, run_json

audit = load_script("technical-seo-audit", "site_audit")


def codes(data, url_suffix=None):
    return {f["code"] for f in data["findings"] if url_suffix is None or f["url"].endswith(url_suffix)}


def test_html_mode_finds_core_problems(fixtures, capsys):
    site = str(fixtures / "technical-seo-audit" / "site")
    code, data = run_json(audit, ["html", site, "--base-url", "https://example.com"], capsys)
    assert code == 1
    assert data["stats"]["pages"] == 6
    assert data["stats"]["indexable"] == 5
    assert "broken-internal-link" in codes(data, "example.com/")
    assert "canonical-relative" in codes(data, "/about/")
    assert "canonical-target-missing" in codes(data, "/blog/post-1.html")
    assert "orphan-page" in codes(data, "/orphan.html")
    assert {"noindex", "noindex-and-canonical"} <= codes(data, "/private.html")
    dup = [f for f in data["findings"] if f["code"] == "title-duplicate"]
    assert len(dup) == 2


def test_html_mode_assets_and_external_links_are_not_broken(fixtures, capsys):
    site = str(fixtures / "technical-seo-audit" / "site")
    _, data = run_json(audit, ["html", site, "--base-url", "https://example.com"], capsys)
    broken = [f["message"] for f in data["findings"] if f["code"] == "broken-internal-link"]
    assert broken == ["Link to https://example.com/missing-page/ has no matching page or file."]


def test_html_mode_noindex_pages_are_not_orphans(fixtures, capsys):
    site = str(fixtures / "technical-seo-audit" / "site")
    _, data = run_json(audit, ["html", site, "--base-url", "https://example.com"], capsys)
    assert "orphan-page" not in codes(data, "/private.html")


def test_clean_urls_build_is_clean(fixtures, capsys):
    site = str(fixtures / "technical-seo-audit" / "clean")
    code, data = run_json(audit, ["html", site, "--base-url", "https://example.com", "--clean-urls"], capsys)
    assert code == 0
    assert data["findings"] == []
    assert data["stats"]["max_click_depth"] == 1


def test_fail_on_never_and_warning(fixtures, capsys):
    site = str(fixtures / "technical-seo-audit" / "site")
    assert audit.main(["html", site, "--base-url", "https://example.com", "--fail-on", "never"]) == 0
    capsys.readouterr()


def test_csv_mode(fixtures, capsys):
    crawl = str(fixtures / "technical-seo-audit" / "crawl.csv")
    code, data = run_json(audit, ["csv", crawl], capsys)
    assert code == 1
    by_url = {}
    for f in data["findings"]:
        by_url.setdefault(f["url"], set()).add(f["code"])
    assert "redirect-chain" in by_url["https://example.com/a"]
    assert "redirect-loop" in by_url["https://example.com/loop1"]
    assert "client-error" in by_url["https://example.com/gone"]
    assert "server-error" in by_url["https://example.com/err"]
    assert "temporary-redirect" in by_url["https://example.com/temp"]
    assert "canonical-to-redirect" in by_url["https://example.com/canon-redirect"]
    assert "noindex" in by_url["https://example.com/hidden"]
    assert {"noindex", "noindex-and-canonical"} <= by_url["https://example.com/header-noindex"]
    assert "uppercase-url" in by_url["https://example.com/Blog/Post"]
    assert "http-page-served" in by_url["http://example.com/old"]
    assert data["stats"]["status_classes"] == {"2xx": 7, "3xx": 5, "4xx": 1, "5xx": 1}


def test_csv_mode_max_chain(fixtures, capsys):
    crawl = str(fixtures / "technical-seo-audit" / "crawl.csv")
    _, data = run_json(audit, ["csv", crawl, "--max-chain", "2"], capsys)
    assert "redirect-chain" not in {f["code"] for f in data["findings"]}


def test_bad_input_exit_2(fixtures, capsys):
    assert audit.main(["csv", str(fixtures / "technical-seo-audit" / "bad.csv")]) == 2
    assert audit.main(["html", "/nonexistent/dir", "--base-url", "https://example.com"]) == 2
    assert audit.main(["html", str(fixtures), "--base-url", "example.com"]) == 2
    assert "error:" in capsys.readouterr().err


def test_page_key_normalisation():
    assert audit.page_key("/a/index.html") == audit.page_key("/a/") == audit.page_key("/a") == "/a"
    assert audit.page_key("/") == "/"
    assert audit.page_key("/b.html") == "/b"


def test_text_output(fixtures, capsys):
    site = str(fixtures / "technical-seo-audit" / "site")
    audit.main(["html", site, "--base-url", "https://example.com"])
    out = capsys.readouterr().out
    assert "[ERROR]" in out and "broken-internal-link" in out
