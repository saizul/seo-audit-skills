import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from conftest import ROOT

spec = importlib.util.spec_from_file_location("validate_skills", ROOT / "tools" / "validate_skills.py")
vs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vs)

GOOD_SKILL = """---
name: demo-skill
description: Does a demo thing for tests. Use when the user asks for a demo of the validator with a long enough description.
license: MIT
---

# Demo

## When to use

- demos

## When not to use

- production

## Workflow

1. Run `python3 scripts/demo.py --help`.
2. Read [the notes](references/notes.md).

## Output

A demo.
"""
DEMO_SCRIPT = """import argparse
argparse.ArgumentParser(description="demo").parse_args()
"""


def make_repo(tmp_path: Path, skill_md: str = GOOD_SKILL, folder: str = "demo-skill") -> Path:
    root = tmp_path / "repo"
    sk = root / "skills" / folder
    (sk / "scripts").mkdir(parents=True)
    (sk / "references").mkdir()
    (sk / "SKILL.md").write_text(skill_md)
    (sk / "scripts" / "demo.py").write_text(DEMO_SCRIPT)
    (sk / "references" / "notes.md").write_text("notes")
    (root / "tests").mkdir()
    (root / "tests" / "test_demo.py").write_text(f'load_script("{folder}", "demo")\n')
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "demo-market",
                "owner": {"name": "Tester"},
                "plugins": [{"name": "demo", "source": "./", "skills": [f"./skills/{folder}"]}],
            }
        )
    )
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "demo", "version": "0.1.0"}))
    (root / "CHANGELOG.md").write_text("## [0.1.0]\n")
    (root / "README.md").write_text(folder)
    (root / "AGENTS.md").write_text(folder)
    return root


def errors(root: Path) -> list[str]:
    return vs.validate_repo(root).errors


def test_real_repository_is_valid():
    report = vs.validate_repo(ROOT)
    assert report.errors == []


def test_minimal_repo_is_valid(tmp_path):
    assert errors(make_repo(tmp_path)) == []


def test_name_must_match_folder(tmp_path):
    root = make_repo(tmp_path, folder="other-name")
    assert any("does not match folder" in e for e in errors(root))


@pytest.mark.parametrize("bad", ["Demo-Skill", "demo--skill", "-demo", "demo_skill", "a" * 65])
def test_invalid_names(tmp_path, bad):
    root = make_repo(tmp_path, GOOD_SKILL.replace("name: demo-skill", f"name: {bad}"))
    assert any("name" in e for e in errors(root))


def test_description_rules(tmp_path):
    root = make_repo(tmp_path, GOOD_SKILL.replace("Use when", "Handy for"))
    assert any("say when to use" in e for e in errors(root))
    long_desc = "Use when " + "x" * 1100
    root2 = make_repo(
        tmp_path / "b",
        GOOD_SKILL.replace(
            "Does a demo thing for tests. Use when the user asks for a demo of the validator with a long enough description.",
            long_desc,
        ),
    )
    assert any("max 1024" in e for e in errors(root2))


def test_block_scalar_description(tmp_path):
    md = GOOD_SKILL.replace(
        "description: Does a demo thing for tests. Use when the user asks for a demo of the validator with a long enough description.",
        "description: >\n  Does a demo thing for tests.\n  Use when the user asks for a demo of the validator with a long enough description.",
    )
    assert errors(make_repo(tmp_path, md)) == []


def test_missing_frontmatter_and_unknown_keys(tmp_path):
    root = make_repo(tmp_path, GOOD_SKILL.split("---\n", 2)[2])
    assert any("frontmatter" in e for e in errors(root))
    root2 = make_repo(tmp_path / "b", GOOD_SKILL.replace("license: MIT", "license: MIT\nversion: 1"))
    assert any("unknown frontmatter keys" in e for e in errors(root2))


def test_required_sections_and_length(tmp_path):
    root = make_repo(tmp_path, GOOD_SKILL.replace("## When not to use", "## Notes"))
    assert any("When not to use" in e for e in errors(root))
    root2 = make_repo(tmp_path / "b", GOOD_SKILL + "\nline" * 420)
    assert any("max 400" in e for e in errors(root2))


def test_broken_references(tmp_path):
    root = make_repo(tmp_path, GOOD_SKILL.replace("references/notes.md", "references/missing.md"))
    assert any("references/missing.md" in e for e in errors(root))


def test_script_rules(tmp_path):
    root = make_repo(tmp_path)
    (root / "tests" / "test_demo.py").write_text("")
    assert any("has no test" in e for e in errors(root))
    root2 = make_repo(tmp_path / "b")
    (root2 / "skills" / "demo-skill" / "scripts" / "extra.py").write_text(DEMO_SCRIPT)
    errs = errors(root2)
    assert any("extra.py is not mentioned" in e for e in errs)
    root3 = make_repo(tmp_path / "c")
    (root3 / "skills" / "demo-skill" / "scripts" / "demo.py").write_text("raise SystemExit(3)\n")
    assert any("--help failed" in e for e in errors(root3))


def test_marketplace_rules(tmp_path):
    root = make_repo(tmp_path)
    mp = root / ".claude-plugin" / "marketplace.json"
    data = json.loads(mp.read_text())
    data["plugins"][0]["skills"] = []
    mp.write_text(json.dumps(data))
    assert any("not listed in marketplace.json" in e for e in errors(root))
    data["plugins"][0]["skills"] = ["./skills/demo-skill", "./skills/ghost"]
    mp.write_text(json.dumps(data))
    errs = errors(root)
    assert any("ghost has no SKILL.md" in e for e in errs)
    mp.write_text("{broken")
    assert any("invalid JSON" in e for e in errors(root))


def test_plugin_name_and_changelog(tmp_path):
    root = make_repo(tmp_path)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "other", "version": "0.2.0"}))
    errs = errors(root)
    assert any("differs from marketplace entry" in e for e in errs)
    assert any("no entry for plugin version 0.2.0" in e for e in errs)


def test_docs_must_mention_skills(tmp_path):
    root = make_repo(tmp_path)
    (root / "README.md").write_text("nothing here")
    assert any("README.md: does not mention" in e for e in errors(root))


def test_cli(tmp_path, capsys):
    root = make_repo(tmp_path)
    assert vs.main(["--root", str(root)]) == 0
    assert "1 skills checked: 0 error(s)" in capsys.readouterr().out
    shutil.rmtree(root / "skills" / "demo-skill" / "references")
    assert vs.main(["--root", str(root), "--json", "--no-run"]) == 1
    assert json.loads(capsys.readouterr().out)["errors"]
