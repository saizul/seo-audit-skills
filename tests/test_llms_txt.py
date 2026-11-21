from conftest import load_script

llms = load_script("llms-txt", "llms_txt")


def test_build_from_sitemap(fixtures, capsys):
    f = str(fixtures / "llms-txt" / "sitemap.xml")
    assert (
        llms.main(
            [
                "build",
                "--name",
                "Example",
                "--summary",
                "Example syncs files.",
                "--sitemap",
                f,
                "--section",
                "Docs=/docs/",
                "--section",
                "Blog=/blog/",
                "--optional",
                "Blog",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert out.startswith("# Example\n\n> Example syncs files.\n")
    assert "## Docs" in out and "## Optional" in out and "## Pages" in out
    assert out.index("## Docs") < out.index("## Pages") < out.index("## Optional")
    assert "- [Getting Started](https://example.com/docs/getting-started)" in out
    assert "/page/2/" not in out and "/tag/" not in out
    assert out.count("https://example.com/pricing") == 1
    assert [i for i in llms.validate(out) if i["severity"] != "notice"] == []


def test_no_default_excludes(fixtures, capsys):
    f = str(fixtures / "llms-txt" / "sitemap.xml")
    llms.main(["build", "--name", "E", "--sitemap", f, "--no-default-excludes"])
    assert "/tag/news/" in capsys.readouterr().out


def test_build_from_pages_csv_and_json(fixtures, capsys):
    llms.main(["build", "--name", "Example", "--pages", str(fixtures / "llms-txt" / "pages.csv")])
    out = capsys.readouterr().out
    assert "- [Install](https://example.com/docs/install): How to install the CLI" in out  # brand suffix stripped
    assert "[Beta (preview)]" in out  # brackets escaped
    llms.main(["build", "--name", "Example", "--pages", str(fixtures / "llms-txt" / "pages.json")])
    assert "- [A page](https://example.com/a): First" in capsys.readouterr().out


def test_build_from_html_skips_noindex(fixtures, capsys, tmp_path):
    out_file = tmp_path / "llms.txt"
    assert (
        llms.main(
            [
                "build",
                "--name",
                "Example",
                "--html-dir",
                str(fixtures / "llms-txt" / "site"),
                "--base-url",
                "https://example.com",
                "-o",
                str(out_file),
            ]
        )
        == 0
    )
    text = out_file.read_text()
    assert "Quickstart" in text and "Five minute setup." in text
    assert "draft" not in text.lower()
    assert "wrote" in capsys.readouterr().err


def test_validate_good(fixtures, capsys):
    assert llms.main(["validate", str(fixtures / "llms-txt" / "good.txt"), "--strict"]) == 0
    assert "OK" in capsys.readouterr().out


def test_validate_bad(fixtures, capsys):
    assert llms.main(["validate", str(fixtures / "llms-txt" / "bad.txt")]) == 1
    issues = llms.validate((fixtures / "llms-txt" / "bad.txt").read_text())
    msgs = " | ".join(i["message"] for i in issues)
    for needle in (
        "first line must be an H1",
        "Only one H1",
        "must start with a Markdown link",
        "introduced with ': '",
        "relative",
        "also listed",
        "Prose inside",
        "Only H1 and H2",
        "has no links",
    ):
        assert needle in msgs, needle
    capsys.readouterr()


def test_validate_empty():
    assert llms.validate("")[0]["severity"] == "error"


def test_title_from_url():
    assert llms.title_from_url("https://e.com/") == "Home"
    assert llms.title_from_url("https://e.com/docs/getting-started.html") == "Getting Started"


def test_sitemap_index_rejected(tmp_path, capsys):
    p = tmp_path / "idx.xml"
    p.write_text(
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://e.com/s.xml</loc></sitemap></sitemapindex>'
    )
    assert llms.main(["build", "--name", "E", "--sitemap", str(p)]) == 2
    assert "sitemap index" in capsys.readouterr().err


def test_reference_example_is_valid():
    from conftest import SKILLS

    text = (SKILLS / "llms-txt" / "references" / "example.md").read_text()
    block = text.split("```markdown\n", 1)[1].split("\n```", 1)[0]
    assert [i for i in llms.validate(block) if i["severity"] != "notice"] == []
