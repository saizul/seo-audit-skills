import pytest
from conftest import load_script, run_json

h = load_script("hreflang-check", "hreflang_check")


@pytest.mark.parametrize(
    "code,severity",
    [
        ("en", ""),
        ("en-GB", ""),
        ("EN-gb", ""),
        ("zh-Hant-TW", ""),
        ("zh-Hans", ""),
        ("x-default", ""),
        ("pt-BR", ""),
        ("en-UK", "error"),
        ("jp", "error"),
        ("GB", "error"),
        ("es-419", "error"),
        ("en_US", "error"),
        ("de-XX", "error"),
        ("xx", "error"),
        ("en-US-CA", "error"),
        ("fil", "warning"),
        ("kr", "warning"),
        ("se-SE", "warning"),
    ],
)
def test_check_code(code, severity):
    assert h.check_code(code)[0] == severity


def test_good_cluster(fixtures, capsys):
    code, data = run_json(
        h, ["--html-dir", str(fixtures / "hreflang-check" / "good"), "--base-url", "https://example.com"], capsys
    )
    assert code == 0
    assert data["issues"] == []
    assert data["annotated_pages"] == 2


def test_bad_cluster(fixtures, capsys):
    code, data = run_json(
        h, ["--html-dir", str(fixtures / "hreflang-check" / "bad"), "--base-url", "https://example.com"], capsys
    )
    assert code == 1
    msgs = [(i["severity"], i["url"], i["message"]) for i in data["issues"]]
    text = " | ".join(m for _, _, m in msgs)
    assert "is relative" in text
    assert "'UK' is not a valid region" in text
    assert "points to two URLs" in text
    assert "canonicalises to https://example.com/es/main/" in text
    assert any(s == "error" and "No return link: https://example.com/fr/" in m for s, _, m in msgs)
    assert any("<html lang='fr'> disagrees" in m for _, _, m in msgs)
    assert any("inconsistent annotation sets" in m for _, _, m in msgs)
    assert any("No self-referencing" in m for _, u, m in msgs) is False


def test_missing_self_reference():
    pages = {
        "https://e.com/": {
            "url": "https://e.com/",
            "lang": None,
            "canonical": None,
            "alternates": [("de", "https://e.com/de/")],
        },
        "https://e.com/de/": {
            "url": "https://e.com/de/",
            "lang": None,
            "canonical": None,
            "alternates": [("de", "https://e.com/de/"), ("en", "https://e.com/")],
        },
    }
    issues = h.audit(pages)
    assert any(i["url"] == "https://e.com/" and "self-referencing" in i["message"] for i in issues)


def test_sitemap_input(fixtures, capsys):
    code, data = run_json(h, ["--sitemap", str(fixtures / "hreflang-check" / "sitemap.xml")], capsys)
    assert code == 1
    assert any("No return link" in i["message"] and "pt-BR" in i["message"] for i in data["issues"])


def test_csv_input(fixtures, capsys):
    code, data = run_json(h, ["--csv", str(fixtures / "hreflang-check" / "annotations.csv")], capsys)
    assert code == 1
    assert any("did you mean 'ja'" in i["message"] for i in data["issues"])


def test_code_mode(capsys):
    assert h.main(["--code", "en-GB", "--code", "x-default"]) == 0
    assert h.main(["--code", "en-UK"]) == 1
    capsys.readouterr()


def test_bad_inputs(tmp_path, capsys):
    bad = tmp_path / "a.csv"
    bad.write_text("page,lang\nx,y\n")
    assert h.main(["--csv", str(bad)]) == 2
    assert h.main(["--sitemap", str(tmp_path / "missing.xml")]) == 2
    capsys.readouterr()
