#!/usr/bin/env python3
"""Lint a robots.txt file and test URLs against it the way Google does (RFC 9309).

  robots_check.py robots.txt
  robots_check.py robots.txt --test /checkout/ --test "/search?q=shoes" --user-agent Googlebot
  robots_check.py robots.txt --expect-allowed / --expect-allowed /blog/ --expect-blocked /cart/

Matching follows Google's documented behaviour: the most specific user-agent group
wins (groups with the same agent are merged, '*' is the fallback), the longest
matching rule wins, and allow wins a tie. '*' and '$' wildcards are supported.

Because a named group replaces the '*' group entirely, the linter warns when a
crawler-specific group (e.g. Googlebot) silently drops Disallow rules that the
'*' group has, which is a common reason private paths end up crawled.

Exit status: 0 = no errors and all expectations met, 1 = otherwise, 2 = input error.
Python 3.9+ standard library only. Reads a local file; no network access.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import quote, unquote, urlsplit

MAX_BYTES = 500 * 1024  # Google ignores content after 500 KiB
KNOWN = {"user-agent", "allow", "disallow", "sitemap"}
IGNORED_BY_GOOGLE = {
    "crawl-delay",
    "host",
    "clean-param",
    "request-rate",
    "visit-time",
    "noindex",
    "nofollow",
    "noarchive",
}


def read_text(path: str, encoding: str = "utf-8", errors: str = "strict") -> str:
    with open(path, encoding=encoding, errors=errors) as fh:
        return fh.read()


class Rule:
    __slots__ = ("allow", "pattern", "line", "_re")

    def __init__(self, allow: bool, pattern: str, line: int) -> None:
        self.allow = allow
        self.pattern = pattern
        self.line = line
        self._re = compile_pattern(pattern)

    def matches(self, path: str) -> bool:
        return bool(self._re.match(path))


def normalise_path(path: str) -> str:
    # Percent-encode consistently so /caf%C3%A9 and /café compare equal.
    return quote(unquote(path), safe="/?&=*$:@!,;+%-._~")


def compile_pattern(pattern: str) -> re.Pattern:
    p = normalise_path(pattern)
    anchored = p.endswith("$")
    if anchored:
        p = p[:-1]
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in p)
    return re.compile(regex + ("$" if anchored else ""))


class Robots:
    def __init__(self, text: str) -> None:
        self.groups: list[tuple[list[str], list[Rule]]] = []
        self.sitemaps: list[tuple[str, int]] = []
        self.agent_lines: dict[str, int] = {}
        self.issues: list[dict] = []
        self.size = len(text.encode("utf-8"))
        self._parse(text)

    def _issue(self, severity: str, line: int, message: str) -> None:
        self.issues.append({"severity": severity, "line": line, "message": message})

    def _parse(self, text: str) -> None:
        if self.size > MAX_BYTES:
            self._issue("error", 0, f"File is {self.size} bytes; Google ignores everything after 500 KiB.")
        text = text.lstrip("﻿")
        current_agents: list[str] = []
        current_rules: list[Rule] = []
        last_was_agent = False
        for n, raw in enumerate(text.splitlines(), start=1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if ":" not in line:
                self._issue("error", n, f"Line has no ':' separator: '{raw.strip()}'.")
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if key in ("useragent", "user agent"):
                self._issue("warning", n, f"Misspelt directive '{key}'; use 'User-agent'.")
                key = "user-agent"
            if key in ("dissallow", "disalow", "dissalow"):
                self._issue("warning", n, f"Misspelt directive '{key}'; use 'Disallow'.")
                key = "disallow"
            if key == "user-agent":
                if not last_was_agent:
                    if current_agents:
                        self.groups.append((current_agents, current_rules))
                    current_agents, current_rules = [], []
                current_agents.append(value.lower())
                self.agent_lines.setdefault(value.lower(), n)
                last_was_agent = True
                continue
            last_was_agent = False
            if key in ("allow", "disallow"):
                if not current_agents:
                    self._issue("error", n, f"'{key}' before any User-agent line is ignored.")
                    continue
                if value == "":
                    continue  # empty disallow/allow = no rule
                if not value.startswith(("/", "*")):
                    self._issue("warning", n, f"Path '{value}' should start with '/'; Google treats it as '/{value}'.")
                    value = "/" + value
                current_rules.append(Rule(key == "allow", value, n))
                if key == "disallow" and re.search(
                    r"\.(css|js)(\$|$)|/(wp-includes|assets|static|_next|js|css)/", value, re.I
                ):
                    self._issue(
                        "warning", n, f"'Disallow: {value}' may block CSS/JS that Google needs to render pages."
                    )
            elif key == "sitemap":
                if not re.match(r"^https?://", value, re.I):
                    self._issue("error", n, f"Sitemap URL must be absolute: '{value}'.")
                self.sitemaps.append((value, n))
            elif key in IGNORED_BY_GOOGLE:
                self._issue("notice", n, f"'{key}' is not supported by Google and is ignored.")
            else:
                self._issue("warning", n, f"Unknown directive '{key}'.")
        if current_agents:
            self.groups.append((current_agents, current_rules))

        for agents, rules in self.groups:
            if (
                "*" in agents
                and any(not r.allow and r.pattern == "/" for r in rules)
                and not any(r.allow for r in rules)
            ):
                line = next(r.line for r in rules if r.pattern == "/")
                self._issue("error", line, "'User-agent: *' + 'Disallow: /' blocks the whole site for every crawler.")
        self._check_inheritance()
        if not self.groups:
            self._issue("notice", 0, "No user-agent groups: everything is allowed.")
        if not self.sitemaps:
            self._issue("notice", 0, "No Sitemap: line. Add one so crawlers find your XML sitemap.")

    def _check_inheritance(self) -> None:
        """Warn when a named group drops '*' Disallow rules (named groups do not inherit '*')."""
        star = [r for agents, rules in self.groups if "*" in agents for r in rules]
        if not star or any(not r.allow and r.pattern == "/" for r in star):
            return  # no '*' rules, or '*' blocks everything on purpose (allow-listing bots)
        star_disallow = [r.pattern for r in star if not r.allow]
        missing_by_agent: dict[tuple[str, ...], list[str]] = {}
        for agent in self.agent_lines:
            if agent == "*":
                continue
            own = {r.pattern for agents, rules in self.groups if agent in agents for r in rules if not r.allow}
            missing = tuple(p for p in dict.fromkeys(star_disallow) if p not in own)
            if missing:
                missing_by_agent.setdefault(missing, []).append(agent)
        for missing, agents in missing_by_agent.items():
            shown = ", ".join(missing[:3]) + (f" (+{len(missing) - 3} more)" if len(missing) > 3 else "")
            who = ", ".join(agents)
            self._issue(
                "warning",
                min(self.agent_lines[a] for a in agents),
                f"Group for '{who}' does not inherit 'User-agent: *' rules, so Disallow {shown} "
                "do not apply to it; repeat them in that group if they should.",
            )

    def rules_for(self, user_agent: str) -> tuple[str, list[Rule]]:
        token = user_agent.lower().split("/")[0].strip()
        candidates = [token]
        while "-" in token:
            token = token.rsplit("-", 1)[0]
            candidates.append(token)
        for cand in candidates:
            merged = [r for agents, rules in self.groups if cand in agents for r in rules]
            if any(cand in agents for agents, _ in self.groups):
                return cand, merged
        return "*", [r for agents, rules in self.groups if "*" in agents for r in rules]

    def check(self, url_or_path: str, user_agent: str = "Googlebot") -> dict:
        parts = urlsplit(url_or_path)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        path = normalise_path(path)
        group, rules = self.rules_for(user_agent)
        best: Rule | None = None
        for r in rules:
            if r.matches(path):
                plen = len(normalise_path(r.pattern))
                if (
                    best is None
                    or plen > len(normalise_path(best.pattern))
                    or (plen == len(normalise_path(best.pattern)) and r.allow and not best.allow)
                ):
                    best = r
        if path == "/robots.txt":
            best = None
        allowed = True if best is None else best.allow
        return {
            "url": url_or_path,
            "user_agent": user_agent,
            "group": group,
            "allowed": allowed,
            "rule": None if best is None else f"{'Allow' if best.allow else 'Disallow'}: {best.pattern}",
            "line": None if best is None else best.line,
        }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Lint robots.txt and test URLs with Google's matching rules.",
        epilog="Exit codes: 0 ok, 1 errors or failed expectations, 2 input error.",
    )
    ap.add_argument("robots_file", help="path to robots.txt ('-' for stdin)")
    ap.add_argument(
        "--user-agent", default="Googlebot", help="crawler token for --test and --expect-* (default Googlebot)"
    )
    ap.add_argument(
        "--test", action="append", default=[], metavar="URL", help="report whether URL/path is allowed (repeatable)"
    )
    ap.add_argument("--expect-allowed", action="append", default=[], metavar="URL", help="fail if URL/path is blocked")
    ap.add_argument("--expect-blocked", action="append", default=[], metavar="URL", help="fail if URL/path is allowed")
    ap.add_argument("--strict", action="store_true", help="warnings also fail")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)
    try:
        text = sys.stdin.read() if args.robots_file == "-" else read_text(args.robots_file, errors="replace")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    robots = Robots(text)
    tests = [robots.check(u, args.user_agent) for u in args.test]
    expectations = []
    for u in args.expect_allowed:
        res = robots.check(u, args.user_agent)
        expectations.append({**res, "expected": "allowed", "ok": res["allowed"]})
    for u in args.expect_blocked:
        res = robots.check(u, args.user_agent)
        expectations.append({**res, "expected": "blocked", "ok": not res["allowed"]})

    if args.json:
        print(
            json.dumps(
                {
                    "size_bytes": robots.size,
                    "groups": [
                        {"user_agents": a, "rules": [f"{'Allow' if r.allow else 'Disallow'}: {r.pattern}" for r in rs]}
                        for a, rs in robots.groups
                    ],
                    "sitemaps": [s for s, _ in robots.sitemaps],
                    "issues": robots.issues,
                    "tests": tests,
                    "expectations": expectations,
                },
                indent=2,
            )
        )
    else:
        print(f"robots.txt: {robots.size} bytes, {len(robots.groups)} group(s), {len(robots.sitemaps)} sitemap line(s)")
        for s, _ in robots.sitemaps:
            print(f"  Sitemap: {s}")
        for i in sorted(robots.issues, key=lambda x: ("error", "warning", "notice").index(x["severity"])):
            loc = f"line {i['line']}" if i["line"] else "file"
            print(f"  {i['severity'].upper():<8} {loc}: {i['message']}")
        for t in tests:
            verdict = "ALLOWED" if t["allowed"] else "BLOCKED"
            print(
                f"  {verdict:<8} {t['url']}  [{t['user_agent']} -> group '{t['group']}'{', ' + t['rule'] + ' (line ' + str(t['line']) + ')' if t['rule'] else ''}]"
            )
        for e in expectations:
            mark = "OK  " if e["ok"] else "FAIL"
            print(f"  {mark} expected {e['expected']}: {e['url']}" + (f" (matched {e['rule']})" if e["rule"] else ""))

    bad = {"error", "warning"} if args.strict else {"error"}
    failed = any(i["severity"] in bad for i in robots.issues) or any(not e["ok"] for e in expectations)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
