import gzip

import pytest
from conftest import load_script, run_json

robots_mod = load_script("robots-sitemap-check", "robots_check")
sitemap_mod = load_script("robots-sitemap-check", "sitemap_check")


@pytest.fixture
def robots(fixtures):
    return robots_mod.Robots((fixtures / "robots-sitemap-check" / "robots.txt").read_text())


@pytest.mark.parametrize(
    "path,agent,allowed",
    [
        ("/cart/x", "SomeBot", False),
        ("/search?q=1", "SomeBot", False),
        ("/search/help", "SomeBot", True),  # longer Allow wins
        ("/doc.pdf", "SomeBot", False),
        ("/doc.pdf?x=1", "SomeBot", True),  # $ anchors the end
        ("/list?sort=asc", "SomeBot", False),
        ("/cart/x", "Googlebot", True),  # Googlebot group replaces '*'
        ("/private/x", "Googlebot", False),
        ("/private/press/a", "Googlebot", True),
        ("/tmp/x", "Googlebot", False),  # groups for the same agent merge
        ("/tmp/x", "Googlebot-Image", False),  # falls back to googlebot
        ("/tmp/x", "Bingbot", True),
        ("/robots.txt", "SomeBot", True),
        ("https://example.com/cart/", "SomeBot", False),
    ],
)
def test_matching(robots, path, agent, allowed):
    assert robots.check(path, agent)["allowed"] is allowed


def test_tie_goes_to_allow():
    r = robots_mod.Robots("User-agent: *\nDisallow: /page\nAllow: /page\n")
    assert r.check("/page")["allowed"] is True


def test_percent_encoding_equivalence():
    r = robots_mod.Robots("User-agent: *\nDisallow: /café\n")
    assert r.check("/caf%C3%A9")["allowed"] is False


def test_lint_bad_file(fixtures, capsys):
    code, data = run_json(robots_mod, [str(fixtures / "robots-sitemap-check" / "robots-bad.txt")], capsys)
    assert code == 1
    msgs = " | ".join(i["message"] for i in data["issues"])
    assert "before any User-agent" in msgs
    assert "blocks the whole site" in msgs
    assert "Sitemap URL must be absolute" in msgs
    assert "no ':' separator" in msgs
    assert "CSS/JS" in msgs
    assert "Misspelt" in msgs
    assert "not supported by Google" in msgs


def test_expectations(fixtures, capsys):
    f = str(fixtures / "robots-sitemap-check" / "robots.txt")
    assert robots_mod.main([f, "--expect-allowed", "/", "--expect-blocked", "/private/x"]) == 0
    assert robots_mod.main([f, "--expect-allowed", "/private/x"]) == 1
    out = capsys.readouterr().out
    assert "FAIL expected allowed" in out


def test_size_limit():
    r = robots_mod.Robots("User-agent: *\n" + "Disallow: /x\n" * 50000)
    assert any("500 KiB" in i["message"] for i in r.issues)


def test_sitemap_good_gz(fixtures, capsys):
    f = str(fixtures / "robots-sitemap-check" / "sitemap.xml.gz")
    robots = str(fixtures / "robots-sitemap-check" / "robots.txt")
    code, data = run_json(
        sitemap_mod, [f, "--base-url", "https://example.com", "--robots", robots, "--now", "2026-03-15"], capsys
    )
    assert code == 0
    assert data["type"] == "urlset" and data["count"] == 3
    assert data["hreflang_entries"] == 1
    assert data["issues"] == []


def test_sitemap_bad(fixtures, capsys):
    d = fixtures / "robots-sitemap-check"
    code, data = run_json(
        sitemap_mod,
        [
            str(d / "sitemap-bad.xml"),
            "--base-url",
            "https://example.com",
            "--robots",
            str(d / "robots.txt"),
            "--exclude-list",
            str(d / "exclude.txt"),
            "--now",
            "2026-03-15",
        ],
        capsys,
    )
    assert code == 1
    msgs = " | ".join(f"{i['url']} {i['message']}" for i in data["issues"])
    assert "not a W3C datetime" in msgs
    assert "outside 0.0-1.0" in msgs
    assert "/relative/page <loc> must be an absolute" in msgs
    assert "other.example.org/page URL is not under" in msgs
    assert "in the future" in msgs
    assert "Listed 2 times" in msgs
    assert "exclude list" in msgs
    assert "private/report Listed URL is blocked by robots.txt" in msgs
    assert "tracking/session" in msgs
    assert "Entry without <loc>" in msgs


def test_sitemap_index(fixtures, capsys):
    code, data = run_json(sitemap_mod, [str(fixtures / "robots-sitemap-check" / "sitemap-index.xml")], capsys)
    assert code == 0
    assert data["type"] == "sitemapindex"
    assert len(data["children"]) == 2


def test_sitemap_unescaped_and_doctype(fixtures, capsys):
    d = fixtures / "robots-sitemap-check"
    _, data = run_json(sitemap_mod, [str(d / "sitemap-unescaped.xml")], capsys)
    assert "&amp;" in data["issues"][0]["message"]
    _, data = run_json(sitemap_mod, [str(d / "sitemap-doctype.xml")], capsys)
    assert "DOCTYPE" in data["issues"][0]["message"]


def test_identical_lastmod_and_limits():
    urls = "".join(f"<url><loc>https://e.com/{i}</loc><lastmod>2026-01-01</lastmod></url>" for i in range(6))
    xml = f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'.encode()
    res = sitemap_mod.check(xml)
    assert any("identical" in i["message"] for i in res["issues"])
    res = sitemap_mod.check(b"<urlset><url><loc>https://e.com/</loc></url></urlset>")
    assert any("namespace" in i["message"] for i in res["issues"])


def test_lastmod_parsing():
    assert sitemap_mod.parse_lastmod("2026-01-05T10:00Z") is not None
    assert sitemap_mod.parse_lastmod("2026-01-05T10:00:00.123+05:30") is not None
    assert sitemap_mod.parse_lastmod("2026") is not None
    assert sitemap_mod.parse_lastmod("05/01/2026") is None
    assert sitemap_mod.parse_lastmod("2026-01-05 10:00") is None


def test_gzip_reader(tmp_path):
    p = tmp_path / "s.xml.gz"
    p.write_bytes(gzip.compress(b"<urlset/>"))
    assert sitemap_mod.read_bytes(str(p)) == b"<urlset/>"


# The pattern table in references/rules.md, checked against the implementation.
@pytest.mark.parametrize(
    "pattern,path,matches",
    [
        ("/fish", "/fish", True),
        ("/fish", "/fish.html", True),
        ("/fish", "/fishheads/x", True),
        ("/fish", "/fish?id=1", True),
        ("/fish", "/Fish", False),
        ("/fish", "/catfish", False),
        ("/fish/", "/fish/salmon", True),
        ("/fish/", "/fish", False),
        ("/*.php", "/a/b.php?x=1", True),
        ("/*.php", "/", False),
        ("/*.php$", "/index.php", True),
        ("/*.php$", "/index.php?x=1", False),
        ("/*?sort=", "/list?sort=asc", True),
        ("/*?sort=", "/list?page=2&sort=asc", False),
    ],
)
def test_reference_pattern_table(pattern, path, matches):
    r = robots_mod.Robots(f"User-agent: *\nDisallow: {pattern}\n")
    assert (not r.check(path)["allowed"]) is matches


def _inherit_issues(text):
    return [i for i in robots_mod.Robots(text).issues if "does not inherit" in i["message"]]


def test_named_group_not_inheriting_star_rules(robots):
    issues = [i for i in robots.issues if "does not inherit" in i["message"]]
    assert len(issues) == 1  # googlebot and bingbot miss the same rules: one warning
    (issue,) = issues
    assert issue["severity"] == "warning" and issue["line"] == 10
    assert "'googlebot, bingbot'" in issue["message"]
    assert "Disallow /cart/, /search, /*.pdf$ (+1 more)" in issue["message"]


def test_inheritance_warning_skipped_when_rules_repeated_or_star_blocks_all():
    repeated = "User-agent: *\nDisallow: /cart/\n\nUser-agent: Googlebot\nDisallow: /cart/\nDisallow: /tmp/\n"
    assert _inherit_issues(repeated) == []
    allowlist_bots = "User-agent: *\nDisallow: /\n\nUser-agent: Googlebot\nAllow: /\n"
    assert _inherit_issues(allowlist_bots) == []
    no_star = "User-agent: Googlebot\nDisallow: /tmp/\n"
    assert _inherit_issues(no_star) == []


def test_inheritance_warning_per_agent_and_strict(tmp_path, capsys):
    text = (
        "User-agent: *\nDisallow: /admin/\nDisallow: /cart/\n\n"
        "User-agent: Googlebot\nDisallow: /admin/\n\nUser-agent: AdsBot-Google\nAllow: /\n"
    )
    issues = _inherit_issues(text)
    assert [i["line"] for i in issues] == [5, 8]
    assert "'googlebot'" in issues[0]["message"] and "Disallow /cart/ do not" in issues[0]["message"]
    assert "'adsbot-google'" in issues[1]["message"] and "/admin/, /cart/" in issues[1]["message"]
    f = tmp_path / "robots.txt"
    f.write_text(text + "Sitemap: https://example.com/sitemap.xml\n")
    assert robots_mod.main([str(f)]) == 0
    assert robots_mod.main([str(f), "--strict"]) == 1
    assert "does not inherit" in capsys.readouterr().out
