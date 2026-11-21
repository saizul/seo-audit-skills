"""Shared helpers: load skill scripts as modules and locate fixtures. No network."""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_script(skill: str, name: str):
    """Import skills/<skill>/scripts/<name>.py as a module (scripts are not a package)."""
    path = SKILLS / skill / "scripts" / f"{name}.py"
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(f"{skill.replace('-', '_')}_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fixtures():
    return FIXTURES


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if any test tries to open a socket."""

    def guard(*_args, **_kwargs):
        raise RuntimeError("network access is not allowed in tests")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


def run_json(module, argv, capsys):
    """Run module.main(argv + ['--json']) and return (exit_code, parsed_json)."""
    code = module.main([*argv, "--json"])
    out = capsys.readouterr().out
    return code, json.loads(out)
