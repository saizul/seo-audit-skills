import pytest
from conftest import load_script, run_json

ki = load_script("content-brief", "keyword_intent")
co = load_script("content-brief", "competitor_outline")


@pytest.mark.parametrize(
    "kw,intent",
    [
        ("how to clean trail running shoes", "informational"),
        ("what is a rock plate", "informational"),
        ("best trail running shoes", "commercial"),
        ("salomon vs hoka", "commercial"),
        ("buy trail running shoes", "transactional"),
        ("trail shoes coupon", "transactional"),
        ("running store near me", "local"),
        ("acme login", "navigational"),
        ("trail running shoes", "commercial"),
    ],
)
def test_classify(kw, intent):
    assert ki.classify(kw, ["acme"])["intent"] == intent


def test_brand_plus_commercial_is_not_navigational():
    assert ki.classify("acme vs globex", ["acme"])["intent"] == "commercial"
    assert ki.classify("acme", ["acme"])["intent"] == "navigational"


def test_modifier_word_boundaries():
    # "show" contains "how" but is not a question word
    assert "how" not in ki.classify("trail show", [])["modifiers"]


def test_clusters_by_intent_and_terms(fixtures, capsys):
    code, data = run_json(ki, [str(fixtures / "content-brief" / "keywords.csv"), "--brand", "acme"], capsys)
    assert code == 0
    by_kw = {r["keyword"]: r for r in data}
    assert by_kw["best trail running shoes"]["cluster"] == by_kw["trail shoes"]["cluster"]
    assert by_kw["how to clean trail running shoes"]["cluster"] != by_kw["best trail running shoes"]["cluster"]
    assert by_kw["buy trail running shoes"]["cluster"] == by_kw["acme trail shoes price"]["cluster"]
    assert by_kw["trail shoes"]["cluster_head"] == "trail running shoes"  # highest volume heads the cluster
    assert by_kw["trail running shoes"]["volume"] == 12000


def test_inline_keywords_and_text_output(capsys):
    assert ki.main(["--kw", "how to tie shoes", "--kw", "best shoes"]) == 0
    out = capsys.readouterr().out
    assert "Cluster 1" in out and "informational" in out


def test_plain_text_file(tmp_path, capsys):
    p = tmp_path / "kw.txt"
    p.write_text("# comment\nhow to wax skis\nski wax near me\n")
    _, data = run_json(ki, [str(p)], capsys)
    assert [r["intent"] for r in data] == ["informational", "local"]


def test_competitor_outline(fixtures, capsys):
    d = fixtures / "content-brief"
    code, data = run_json(
        co,
        [
            str(d / "rank1.html"),
            str(d / "rank2.html"),
            str(d / "rank3.html"),
            "--ours",
            str(d / "ours.html"),
            "--top",
            "15",
        ],
        capsys,
    )
    assert code == 0
    assert len(data["pages"]) == 3
    terms = {t["term"]: t["pages"] for t in data["common_terms"]}
    assert terms["lug depth"] == 3
    assert "rock plate" in terms and "heel-to-toe drop" in terms
    assert "running shoes" not in terms  # subsumed by "trail running shoes"
    subs = {s["subtopic"]: s["pages"] for s in data["common_subtopics"]}
    assert subs["Lug depth and grip"] == 3
    assert "How long do trail running shoes last?" in data["questions"]  # from FAQ schema and H3
    assert "What is a rock plate?" in data["questions"]
    assert "Lug depth and grip" in data["ours"]["missing_subtopics"]
    assert "rock plate" in data["ours"]["missing_terms"]
    assert "grip" not in data["ours"]["missing_terms"]
    nav_words = {w for p in data["pages"] for w in p["title"].split()}
    assert "Copyright" not in nav_words
    assert data["median_word_count"] > 0


def test_competitor_markdown(fixtures, capsys):
    d = fixtures / "content-brief"
    co.main([str(d / "rank1.html"), str(d / "rank2.html")])
    out = capsys.readouterr().out
    assert out.startswith("# Competitor outline analysis")
    assert "## Common subtopics" in out


def test_missing_file(capsys):
    assert co.main(["/nonexistent.html"]) == 2
    capsys.readouterr()
