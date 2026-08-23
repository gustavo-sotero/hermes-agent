"""Tests for /init — generate or update AGENTS.md from a project scan.

Covers the shared prompt builder (hermes_cli.init_command.build_init_prompt),
the harness-instruction collector (`.github/instructions/`, `CLAUDE.md`,
`.cursorrules`), and the slash-command registry wiring. /init has no engine
and no model tool: it builds a guidance-laden prompt that the live agent runs
as a normal turn (the /learn pattern), so these are the load-bearing behavior
contracts.
"""

from hermes_cli.init_command import (
    _QUALITY_BAR,
    _collect_harness_instructions,
    build_init_prompt,
    build_init_prompt_for_cwd,
)


class TestBuildInitPrompt:

    def test_merge_not_overwrite_when_existing_file_passed(self):
        existing = "# My Project\n\nAlways run `make lint` before committing.\n"
        prompt = build_init_prompt("/tmp/proj", existing_file=existing)
        low = prompt.lower()
        # Update mode, with explicit merge-not-overwrite discipline.
        assert "UPDATE the existing AGENTS.md" in prompt
        assert "merge" in low
        assert "do not overwrite" in low or "not overwrite" in low
        assert "preserve" in low
        # And it carries the current content so the agent can merge.
        assert existing.strip() in prompt

    def test_includes_extra_notes_verbatim(self):
        notes = "focus on the test setup, and mention the flaky e2e suite"
        prompt = build_init_prompt("/tmp/proj", extra=notes)
        assert notes in prompt

    def test_embeds_harness_instructions_when_present(self):
        harness = [
            (".github/instructions/stack.instructions.md", "# Stack\n\nBun.\n"),
            ("CLAUDE.md", "# Claude\n\nRun `make test`.\n"),
        ]
        prompt = build_init_prompt("/tmp/proj", harness_instructions=harness)
        # The embedding instruction is present, and each file is labeled.
        assert "EXTERNAL HARNESS INSTRUCTIONS" in prompt
        assert "===== FILE: .github/instructions/stack.instructions.md =====" in prompt
        assert "===== FILE: CLAUDE.md =====" in prompt
        assert "# Stack" in prompt
        # No harness section when nothing was collected.
        prompt2 = build_init_prompt("/tmp/proj")
        assert "EXTERNAL HARNESS INSTRUCTIONS" not in prompt2


class TestCollectHarnessInstructions:

    def test_collects_github_copilot_instructions(self, tmp_path):
        (tmp_path / ".github" / "instructions").mkdir(parents=True)
        (tmp_path / ".github" / "instructions" / "stack.instructions.md").write_text(
            "# Stack\n\nBun.\n", encoding="utf-8"
        )
        (tmp_path / ".github" / "instructions" / "prd-sdd.instructions.md").write_text(
            "# PRD\n\nDirect channel.\n", encoding="utf-8"
        )
        collected = _collect_harness_instructions(tmp_path)
        rels = [rel for rel, _ in collected]
        assert ".github/instructions/prd-sdd.instructions.md" in rels
        assert ".github/instructions/stack.instructions.md" in rels
        assert any(content.startswith("# Stack") for _, content in collected)

    def test_collects_claude_and_cursor_rules(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Claude\n\nRules.\n", encoding="utf-8")
        (tmp_path / ".cursorrules").write_text("cursor\n", encoding="utf-8")
        (tmp_path / ".cursor" / "rules").mkdir(parents=True)
        (tmp_path / ".cursor" / "rules" / "frontend.mdc").write_text(
            "frontend rules\n", encoding="utf-8"
        )
        collected = _collect_harness_instructions(tmp_path)
        rels = [rel for rel, _ in collected]
        assert "CLAUDE.md" in rels
        assert ".cursorrules" in rels
        assert ".cursor/rules/frontend.mdc" in rels

    def test_returns_empty_when_no_harness_docs(self, tmp_path):
        assert _collect_harness_instructions(tmp_path) == []


class TestBuildInitPromptForCwd:

    def test_reads_existing_agents_md(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text(
            "# Existing\n\nRun `tox -e py311`.\n", encoding="utf-8"
        )
        prompt = build_init_prompt_for_cwd(cwd=str(tmp_path))
        assert "UPDATE the existing AGENTS.md" in prompt
        assert "Run `tox -e py311`." in prompt

    def test_collects_harness_instructions_from_cwd(self, tmp_path):
        (tmp_path / ".github" / "instructions").mkdir(parents=True)
        (tmp_path / ".github" / "instructions" / "stack.instructions.md").write_text(
            "# Stack\n\nBun native-first.\n", encoding="utf-8"
        )
        prompt = build_init_prompt_for_cwd(cwd=str(tmp_path))
        assert "EXTERNAL HARNESS INSTRUCTIONS" in prompt
        assert "===== FILE: .github/instructions/stack.instructions.md =====" in prompt
        assert "Bun native-first." in prompt

    def test_passes_extra_through(self, tmp_path):
        prompt = build_init_prompt_for_cwd(cwd=str(tmp_path), extra="keep it short")
        assert "keep it short" in prompt


class TestInitRegistryWiring:
    def test_init_is_registered_and_resolves(self):
        from hermes_cli.commands import resolve_command

        cmd = resolve_command("init")
        assert cmd is not None
        assert cmd.name == "init"

    def test_init_works_on_the_gateway(self):
        # /init is a both-surfaces command like /learn, not CLI-only.
        from hermes_cli.commands import GATEWAY_KNOWN_COMMANDS

        assert "init" in GATEWAY_KNOWN_COMMANDS
