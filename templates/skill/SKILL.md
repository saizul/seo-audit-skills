---
name: my-skill-name
description: One or two sentences on WHAT the skill does (inputs, checks, outputs) and WHEN to use it. Use when the user asks for <trigger phrases>, mentions <keywords>, or works on <situations>. Max 1024 characters.
license: MIT
---

# Human-readable skill title

One short paragraph: the goal of the skill and what "done" looks like.

Paths below are relative to this skill's directory.

## When to use

- <trigger phrase or situation>
- <another>

## When not to use

- <situation> - use `<other-skill>` instead.

## Inputs to collect

1. <what to ask the user for, and which input is preferred>

## Workflow

1. **Run the deterministic check:**
   `python3 scripts/my_script.py <input> --json`
   Explain what the exit code means.
2. **Interpret** the result: what to look at first, what the script cannot see.
3. **Decide** using the decision points below.
4. **Fix at the source** (template, config, CMS setting) and re-run the script.

## Decision points

- **<Situation A> vs <Situation B>:** what to do in each case and why.

## Output

```
## <Report title>
| Priority | Issue | Evidence | Fix |
```

State what was not checked.

## Files

- `scripts/my_script.py` - what it does (`--json`, exit codes).
- [references/details.md](references/details.md) - long tables, rules and examples (loaded only when needed).
