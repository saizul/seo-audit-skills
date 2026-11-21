#!/usr/bin/env python3
"""Validate every skill in this repository and the plugin marketplace manifests.

  python tools/validate_skills.py            # validate the repo this file lives in
  python tools/validate_skills.py --root .   # validate another checkout
  python tools/validate_skills.py --json

Checks, per skill (skills/<name>/SKILL.md):
  - YAML frontmatter with only known keys; `name` is lowercase-hyphen, <= 64 chars,
    no leading/trailing/double hyphens, and equals the folder name
  - `description` is 1-1024 chars and says when to use the skill ("Use when ...")
  - required body sections: When to use, When not to use, Workflow, Output
  - body is at most 400 lines (move detail to references/)
  - every relative link and every scripts/ references/ assets/ path mentioned exists
  - every script is mentioned in SKILL.md, answers --help, and is covered by a test

Repository checks:
  - .claude-plugin/marketplace.json is valid, lists the plugin(s) with existing
    sources, and its skills list matches the skills/ folders exactly
  - .claude-plugin/plugin.json name matches the marketplace entry; its version is in CHANGELOG.md
  - README.md and AGENTS.md mention every skill

Exit status: 0 = valid, 1 = errors found. Python 3.9+ standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PLUGIN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ALLOWED_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
REQUIRED_SECTIONS = ("When to use", "When not to use", "Workflow", "Output")
MAX_BODY_LINES = 400
PATH_PREFIXES = ("scripts/", "references/", "assets/", "../")


def parse_frontmatter(text: str) -> tuple[dict | None, str, str]:
    """Return (frontmatter, body, error). Supports the YAML subset skills use."""
    if not text.startswith("---\n"):
        return None, text, "SKILL.md must start with '---' YAML frontmatter"
    end = text.find("\n---", 4)
    if end == -1:
        return None, text, "frontmatter is not closed with '---'"
    raw = text[4:end]
    body = text[end + 4 :].lstrip("\n")
    data: dict = {}
    current_map: str | None = None
    block_key: str | None = None
    block_lines: list[str] = []
    for line in raw.splitlines():
        if block_key is not None:
            if line.startswith((" ", "\t")) or not line.strip():
                block_lines.append(line.strip())
                continue
            data[block_key] = " ".join(x for x in block_lines if x)
            block_key = None
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            if current_map is None:
                return None, body, f"unexpected indented line in frontmatter: {line.strip()!r}"
            k, sep, v = line.strip().partition(":")
            if not sep:
                return None, body, f"invalid line under {current_map}: {line.strip()!r}"
            data[current_map][k.strip()] = unquote(v.strip())
            continue
        current_map = None
        k, sep, v = line.partition(":")
        if not sep:
            return None, body, f"invalid frontmatter line: {line!r}"
        k, v = k.strip(), v.strip()
        if k in data:
            return None, body, f"duplicate frontmatter key: {k}"
        if v in (">", "|", ">-", "|-"):
            block_key, block_lines = k, []
        elif v == "":
            data[k] = {}
            current_map = k
        else:
            data[k] = unquote(v)
    if block_key is not None:
        data[block_key] = " ".join(x for x in block_lines if x)
    return data, body, ""


def unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def mentioned_paths(body: str) -> set[str]:
    paths = set()
    for target in re.findall(r"\]\(([^)\s]+)\)", body):
        if not re.match(r"^(https?:|mailto:|#)", target):
            paths.add(target.split("#", 1)[0])
    for span in re.findall(r"`([^`\n]+)`", body):
        for token in span.split():
            token = token.strip("'\",;:()")
            if token.startswith(PATH_PREFIXES) and not re.search(r"[<>*{}$]", token):
                paths.add(token)
    return {p for p in paths if p}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")


def validate_skill(skill_dir: Path, tests_text: str, report: Report, run_help: bool = True) -> None:
    where = f"skills/{skill_dir.name}"
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        report.error(where, "missing SKILL.md")
        return
    text = skill_md.read_text(encoding="utf-8")
    fm, body, err = parse_frontmatter(text)
    if err:
        report.error(where, err)
        return
    unknown = set(fm) - ALLOWED_KEYS
    if unknown:
        report.error(where, f"unknown frontmatter keys: {sorted(unknown)}")
    name = fm.get("name", "")
    if not isinstance(name, str) or not name:
        report.error(where, "frontmatter 'name' is required")
    else:
        if len(name) > 64:
            report.error(where, f"name is {len(name)} chars (max 64)")
        if not NAME_RE.match(name):
            report.error(where, f"name '{name}' must be lowercase letters, digits and single hyphens")
        if name != skill_dir.name:
            report.error(where, f"name '{name}' does not match folder '{skill_dir.name}'")
    desc = fm.get("description", "")
    if not isinstance(desc, str) or not desc.strip():
        report.error(where, "frontmatter 'description' is required")
    else:
        if len(desc) > 1024:
            report.error(where, f"description is {len(desc)} chars (max 1024)")
        if not re.search(r"\buse (it )?when\b", desc, re.I):
            report.error(where, "description must say when to use the skill (include 'Use when ...')")
        if len(desc) < 80:
            report.warn(where, "description is very short; name concrete triggers and keywords")
    comp = fm.get("compatibility")
    if isinstance(comp, str) and len(comp) > 500:
        report.error(where, "compatibility is longer than 500 chars")
    if "metadata" in fm and not isinstance(fm["metadata"], dict):
        report.error(where, "metadata must be a mapping")

    headings = {h.strip() for h in re.findall(r"^##\s+(.+)$", body, re.M)}
    for section in REQUIRED_SECTIONS:
        if section not in headings:
            report.error(where, f"missing required section '## {section}'")
    if not re.search(r"^#\s+\S", body, re.M):
        report.warn(where, "body has no H1 title")
    n_lines = body.count("\n") + 1
    if n_lines > MAX_BODY_LINES:
        report.error(where, f"SKILL.md body is {n_lines} lines (max {MAX_BODY_LINES}); move detail to references/")

    for rel in sorted(mentioned_paths(body)):
        target = (skill_dir / rel).resolve()
        if not target.exists():
            report.error(where, f"referenced path does not exist: {rel}")

    scripts_dir = skill_dir / "scripts"
    if scripts_dir.is_dir():
        for script in sorted(scripts_dir.iterdir()):
            if script.name.startswith((".", "_")) or script.suffix not in (".py", ".sh"):
                continue
            if f"scripts/{script.name}" not in body:
                report.error(where, f"scripts/{script.name} is not mentioned in SKILL.md")
            if script.suffix == ".py":
                if (
                    f'load_script("{skill_dir.name}", "{script.stem}")' not in tests_text
                    and script.name not in tests_text
                ):
                    report.error(where, f"scripts/{script.name} has no test in tests/")
                if run_help:
                    proc = subprocess.run(
                        [sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=60
                    )
                    if proc.returncode != 0 or "usage" not in proc.stdout.lower():
                        report.error(where, f"scripts/{script.name} --help failed: {proc.stderr.strip()[:200]}")
    for sub in ("references", "assets"):
        d = skill_dir / sub
        if d.is_dir() and not any(d.iterdir()):
            report.warn(where, f"{sub}/ is empty")


def validate_repo(root: Path, run_help: bool = True) -> Report:
    report = Report()
    skills_root = root / "skills"
    if not skills_root.is_dir():
        report.error("repo", "no skills/ directory")
        return report
    skill_dirs = sorted(d for d in skills_root.iterdir() if d.is_dir() and not d.name.startswith("."))
    if not skill_dirs:
        report.error("repo", "skills/ contains no skills")
    tests_text = (
        "\n".join(p.read_text(encoding="utf-8") for p in sorted((root / "tests").rglob("*.py")))
        if (root / "tests").is_dir()
        else ""
    )
    for d in skill_dirs:
        validate_skill(d, tests_text, report, run_help)
    names = [d.name for d in skill_dirs]

    # Marketplace + plugin manifests
    mp_path = root / ".claude-plugin" / "marketplace.json"
    plugin_version = None
    if not mp_path.is_file():
        report.error("marketplace", ".claude-plugin/marketplace.json is missing")
    else:
        try:
            mp = json.loads(mp_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report.error("marketplace", f"invalid JSON: {exc}")
            mp = None
        if isinstance(mp, dict):
            if not PLUGIN_NAME_RE.match(str(mp.get("name", ""))):
                report.error("marketplace", "name is missing or invalid")
            if not isinstance(mp.get("owner"), dict) or not mp["owner"].get("name"):
                report.error("marketplace", "owner.name is required")
            plugins = mp.get("plugins")
            if not isinstance(plugins, list) or not plugins:
                report.error("marketplace", "plugins must be a non-empty array")
                plugins = []
            listed: list[str] = []
            seen_names = set()
            for i, entry in enumerate(plugins):
                w = f"marketplace plugins[{i}]"
                pname = entry.get("name", "") if isinstance(entry, dict) else ""
                if not PLUGIN_NAME_RE.match(pname):
                    report.error(w, "name is missing or invalid")
                if pname in seen_names:
                    report.error(w, f"duplicate plugin name {pname}")
                seen_names.add(pname)
                source = entry.get("source") if isinstance(entry, dict) else None
                if not isinstance(source, str) or not (source.startswith("./") or source == "."):
                    report.error(w, "source must be a relative path starting with './'")
                    continue
                if ".." in source:
                    report.error(w, "source must not contain '..'")
                    continue
                src_dir = (root / source).resolve()
                if not src_dir.is_dir():
                    report.error(w, f"source {source} does not exist")
                    continue
                pj = src_dir / ".claude-plugin" / "plugin.json"
                if pj.is_file():
                    try:
                        manifest = json.loads(pj.read_text(encoding="utf-8"))
                    except json.JSONDecodeError as exc:
                        report.error("plugin.json", f"invalid JSON: {exc}")
                        manifest = {}
                    if manifest.get("name") != pname:
                        report.error(
                            "plugin.json", f"name '{manifest.get('name')}' differs from marketplace entry '{pname}'"
                        )
                    plugin_version = manifest.get("version", plugin_version)
                for sk in entry.get("skills", []) or []:
                    if not isinstance(sk, str) or not sk.startswith("./"):
                        report.error(w, f"skill path {sk!r} must start with './'")
                        continue
                    if not (src_dir / sk).joinpath("SKILL.md").is_file():
                        report.error(w, f"skill path {sk} has no SKILL.md")
                    listed.append(Path(sk).name)
            missing = sorted(set(names) - set(listed))
            extra = sorted(set(listed) - set(names))
            if missing:
                report.error("marketplace", f"skills not listed in marketplace.json: {missing}")
            if extra:
                report.error("marketplace", f"marketplace.json lists unknown skills: {extra}")

    changelog = root / "CHANGELOG.md"
    if plugin_version and changelog.is_file() and f"[{plugin_version}]" not in changelog.read_text(encoding="utf-8"):
        report.error("CHANGELOG.md", f"no entry for plugin version {plugin_version}")
    for doc in ("README.md", "AGENTS.md"):
        p = root / doc
        if not p.is_file():
            report.error(doc, "missing")
            continue
        text = p.read_text(encoding="utf-8")
        for n in names:
            if n not in text:
                report.error(doc, f"does not mention skill '{n}'")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Validate skills, marketplace.json and docs.", epilog="Exit codes: 0 valid, 1 errors."
    )
    ap.add_argument(
        "--root", default=str(Path(__file__).resolve().parent.parent), help="repository root (default: this checkout)"
    )
    ap.add_argument("--no-run", action="store_true", help="skip running each script with --help")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)
    report = validate_repo(Path(args.root), run_help=not args.no_run)
    if args.json:
        print(json.dumps({"errors": report.errors, "warnings": report.warnings}, indent=2))
    else:
        for w in report.warnings:
            print(f"WARNING {w}")
        for e in report.errors:
            print(f"ERROR   {e}")
        n = len(list((Path(args.root) / "skills").glob("*/SKILL.md")))
        print(f"{n} skills checked: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
