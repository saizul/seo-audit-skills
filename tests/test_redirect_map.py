from conftest import load_script

rm = load_script("redirect-map", "redirect_map")


def rows_for(fixtures):
    old = rm.read_urls(str(fixtures / "redirect-map" / "old.txt"))
    new = rm.read_urls(str(fixtures / "redirect-map" / "new.csv"))
    return {r["old"]: r for r in rm.build_map(old, new, 0.55, 0.05)}


def test_read_urls(fixtures):
    old = rm.read_urls(str(fixtures / "redirect-map" / "old.txt"))
    new = rm.read_urls(str(fixtures / "redirect-map" / "new.csv"))
    assert len(old) == 11 and old[0] == "https://old.example.com/"
    assert len(new) == 10 and new[0] == "https://www.example.com/"  # header skipped, Address column


def test_methods(fixtures):
    rows = rows_for(fixtures)
    base = "https://old.example.com"
    assert rows[f"{base}/about-us.html"]["method"] == "exact"
    assert rows[f"{base}/team/index.html"]["new"] == "https://www.example.com/team/"
    assert rows[f"{base}/products/Summit-Jacket"]["method"] == "slug"
    fuzzy = rows[f"{base}/blog/2019/05/how-to-choose-trail-running-shoes/"]
    assert fuzzy["method"] == "fuzzy" and fuzzy["new"].endswith("/guides/choosing-trail-running-shoes/")
    assert rows[f"{base}/blog/category/gear/"]["method"] == "parent"
    assert rows[f"{base}/old-promo-2018"]["method"] == "none"
    assert rows[f"{base}/blog/trail-shoe-review-part-2"]["new"].endswith("part-2/")


def test_ambiguous_fuzzy_is_flagged():
    rows = rm.build_map(
        ["/blog/red-running-shoe-review"], ["/reviews/red-running-shoes", "/reviews/red-running-shoes-2"], 0.5, 0.1
    )
    assert rows[0]["method"] == "fuzzy" and rows[0]["review"] is True
    assert "close alternative" in rows[0]["note"]


def test_chain_warning():
    rows = rm.build_map(["/products/widget", "/widget"], ["/widget"], 0.55, 0.05)
    first = next(r for r in rows if r["old"] == "/products/widget")
    assert first["method"] == "slug"
    assert "chains" in first["note"]


def test_nginx_output(fixtures, capsys):
    d = fixtures / "redirect-map"
    assert rm.main([str(d / "old.txt"), str(d / "new.csv"), "--format", "nginx"]) == 0
    out = capsys.readouterr().out
    assert "map $uri $redirect_target {" in out
    assert '"/about-us.html" "/about-us/";' in out
    assert "/blog/category/gear/" not in out  # below --min-confidence
    assert '"/" "/"' not in out  # never redirect to itself


def test_apache_output_is_anchored(fixtures, capsys):
    d = fixtures / "redirect-map"
    rm.main([str(d / "old.txt"), str(d / "new.csv"), "--format", "apache"])
    out = capsys.readouterr().out
    assert "RedirectMatch 301 ^/contact$ /contact/" in out
    assert r"^/about-us\.html$" in out


def test_netlify_skips_slash_only(fixtures, capsys):
    d = fixtures / "redirect-map"
    rm.main([str(d / "old.txt"), str(d / "new.csv"), "--format", "netlify"])
    out = capsys.readouterr().out
    assert "# skipped (trailing-slash only): /contact -> /contact/" in out
    assert "/products/Summit-Jacket /shop/summit-jacket/ 301" in out


def test_absolute_targets(fixtures, capsys):
    d = fixtures / "redirect-map"
    rm.main([str(d / "old.txt"), str(d / "new.csv"), "--format", "netlify", "--absolute-targets"])
    assert "https://www.example.com/shop/summit-jacket/ 301" in capsys.readouterr().out


def test_csv_and_json_and_exit_codes(fixtures, tmp_path, capsys):
    d = fixtures / "redirect-map"
    out = tmp_path / "map.csv"
    assert rm.main([str(d / "old.txt"), str(d / "new.csv"), "-o", str(out)]) == 0
    assert out.read_text().splitlines()[0] == "old,new,method,confidence,review,note"
    assert rm.main([str(d / "old.txt"), str(d / "new.csv"), "--fail-on-unmatched"]) == 1
    assert rm.main([str(d / "old.txt"), str(d / "new.csv"), "--format", "json"]) == 0
    assert '"method": "exact"' in capsys.readouterr().out


def test_empty_input(tmp_path, capsys):
    e = tmp_path / "e.txt"
    e.write_text("\n")
    assert rm.main([str(e), str(e)]) == 2
    capsys.readouterr()


def test_norm_path():
    assert rm.norm_path("https://x.com/A/Index.html") == "/a"
    assert rm.norm_path("/about-us.php") == "/about-us"
    assert rm.norm_path("about") == "/about"


def test_vercel_output(fixtures, capsys):
    import json

    d = fixtures / "redirect-map"
    assert rm.main([str(d / "old.txt"), str(d / "new.csv"), "--format", "vercel"]) == 0
    doc = json.loads(capsys.readouterr().out)
    redirects = {r["source"]: r for r in doc["redirects"]}
    assert redirects["/products/Summit-Jacket"] == {
        "source": "/products/Summit-Jacket",
        "destination": "/shop/summit-jacket/",
        "statusCode": 301,
    }
    assert "/contact" not in redirects  # trailing-slash only: left to Vercel
    assert "/blog/category/gear/" not in redirects  # below --min-confidence


def test_vercel_source_escapes_path_to_regexp_syntax():
    assert rm.vercel_source("/a:b/(x)*") == r"/a\:b/\(x\)\*"


def test_cloudflare_bulk_absolute_urls(fixtures, capsys):
    d = fixtures / "redirect-map"
    assert rm.main([str(d / "old.txt"), str(d / "new.csv"), "--format", "cloudflare-bulk"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "old.example.com/products/Summit-Jacket,https://www.example.com/shop/summit-jacket/,301" in lines
    assert not any(line.startswith(("#", "source")) for line in lines)  # no header, no comments
    assert all(not line.startswith("http") for line in lines)  # source has no scheme


def test_cloudflare_bulk_relative_needs_host(tmp_path, capsys):
    old, new = tmp_path / "old.txt", tmp_path / "new.txt"
    old.write_text("/about-us.html\n", encoding="utf-8")
    new.write_text("/about-us/\n", encoding="utf-8")
    assert rm.main([str(old), str(new), "--format", "cloudflare-bulk"]) == 2
    assert "--host" in capsys.readouterr().err
    assert rm.main([str(old), str(new), "--format", "cloudflare-bulk", "--host", "WWW.Example.com"]) == 0
    assert capsys.readouterr().out == "www.example.com/about-us.html,https://www.example.com/about-us/,301\n"


def test_cloudflare_bulk_quotes_commas():
    rows = [{"old": "/a,b", "new": "/c,d/", "method": "exact", "confidence": 1.0, "review": False, "note": ""}]
    out = rm.render(rows, "cloudflare-bulk", 0.7, False, "example.com")
    assert out == '"example.com/a,b","https://example.com/c,d/",301\n'
