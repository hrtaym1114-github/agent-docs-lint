from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from agent_docs_lint.scanner import scan


ROOT = Path(__file__).resolve().parents[1]


def rules_for(path: str) -> set[str]:
    return {finding.rule for finding in scan(ROOT / path)}


def test_demo_has_all_rule_families() -> None:
    assert {"dead_ref", "model_name", "unreferenced_agent", "broken_anchor"} <= rules_for("fixtures/demo")


def test_clean_fixture_passes() -> None:
    assert scan(ROOT / "fixtures/clean") == []


def test_dead_ref_rule() -> None:
    findings = scan(ROOT / "fixtures/demo")
    assert any(f.rule == "dead_ref" and "missing linked path" in f.message for f in findings)
    assert any(f.rule == "dead_ref" and "missing slash command" in f.message for f in findings)


def test_template_backtick_paths_are_not_dead_refs(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "Write exports to `output/data/t/<date>.json`.\n",
        encoding="utf-8",
    )

    assert [finding for finding in scan(tmp_path) if finding.rule == "dead_ref"] == []


def test_self_slash_commands_are_not_dead_refs(tmp_path: Path) -> None:
    agent = tmp_path / "agents" / "publish.md"
    agent.parent.mkdir()
    agent.write_text("Run `/publish` after drafting. Ignore short `/go` examples.\n", encoding="utf-8")

    skill = tmp_path / ".claude" / "skills" / "review" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Run `/review` for this skill.\n", encoding="utf-8")

    dead_refs = [finding for finding in scan(tmp_path) if finding.rule == "dead_ref"]
    assert dead_refs == []


def test_nested_agent_attachments_are_not_agent_defs(tmp_path: Path) -> None:
    attachment = tmp_path / "agents" / "1234" / "attachments" / "notes.md"
    attachment.parent.mkdir(parents=True)
    attachment.write_text("# Attachment\n", encoding="utf-8")

    assert [finding for finding in scan(tmp_path) if finding.rule == "unreferenced_agent"] == []


def test_model_name_rule() -> None:
    findings = scan(ROOT / "fixtures/demo")
    assert any(f.rule == "model_name" and "gpt-4o" in f.message for f in findings)


def test_unreferenced_agent_rule() -> None:
    findings = scan(ROOT / "fixtures/demo")
    assert any(f.rule == "unreferenced_agent" and f.path.endswith("orphan-agent.md") for f in findings)


def test_broken_anchor_rule() -> None:
    findings = scan(ROOT / "fixtures/demo")
    assert any(f.rule == "broken_anchor" and "#missing-section" in f.message for f in findings)


def test_config_can_disable_and_override_models(tmp_path: Path) -> None:
    config = tmp_path / "lint.toml"
    config.write_text(
        'disable_rules = ["dead_ref", "broken_anchor", "unreferenced_agent"]\n'
        'model_names = ["custom-model"]\n',
        encoding="utf-8",
    )
    findings = scan(ROOT / "fixtures/demo", config)
    assert findings == []


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agent_docs_lint.cli", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_cli_exit_codes() -> None:
    failing = run_cli("fixtures/demo")
    assert failing.returncode == 1
    assert "dead_ref" in failing.stdout

    clean = run_cli("fixtures/clean")
    assert clean.returncode == 0
    assert clean.stdout.strip() == "No findings."

    warn_only = run_cli("fixtures/demo", "--warn-only")
    assert warn_only.returncode == 0


def test_cli_json() -> None:
    result = run_cli("fixtures/demo", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert {"dead_ref", "model_name", "unreferenced_agent", "broken_anchor"} <= {item["rule"] for item in data}
