"""``/init`` — build the prompt that asks the agent to generate or update a project AGENTS.md."""

from __future__ import annotations

import os
from pathlib import Path

# Harness instruction collection: /init also absorbs instruction docs written
# for OTHER coding agents (GitHub Copilot's `.github/instructions/`, Claude
# Code's `CLAUDE.md`, Cursor's `.cursorrules` / `.cursor/rules/*.mdc`). Hermes
# only auto-loads AGENTS.md every session, so rules living in those files would
# otherwise be invisible to it; /init embeds them into the AGENTS.md it writes.
_HARNESS_FILE_MAX_CHARS = 60_000  # per-file cap (a vendored doc can be huge)
_HARNESS_TOTAL_MAX_CHARS = 200_000  # total cap across all collected files


def _collect_harness_instructions(cwd: Path) -> list[tuple[str, str]]:
    """Collect instruction docs from other agent harnesses.

    Returns ``(rel_path, content)`` tuples sorted by path, with per-file and
    total caps so a giant vendored doc cannot balloon the /init prompt.
    """
    candidates: list[tuple[str, Path]] = []

    def _rel(p: Path) -> str:
        # Normalize to POSIX separators so labels are stable across OSes.
        return str(p.relative_to(cwd)).replace("\\", "/")

    # GitHub Copilot: .github/instructions/*.md
    gh_dir = cwd / ".github" / "instructions"
    if gh_dir.is_dir():
        for p in sorted(gh_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in {".md", ".markdown"}:
                candidates.append((_rel(p), p))

    # Claude Code
    for name in ("CLAUDE.md", "claude.md"):
        p = cwd / name
        if p.is_file():
            candidates.append((name, p))

    # Cursor
    cr = cwd / ".cursorrules"
    if cr.is_file():
        candidates.append((".cursorrules", cr))
    cursor_rules = cwd / ".cursor" / "rules"
    if cursor_rules.is_dir():
        for p in sorted(cursor_rules.glob("*.mdc")):
            candidates.append((_rel(p), p))

    result: list[tuple[str, str]] = []
    total = 0
    for rel, path in candidates:
        try:
            content = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if not content:
            continue
        if len(content) > _HARNESS_FILE_MAX_CHARS:
            content = (
                content[:_HARNESS_FILE_MAX_CHARS]
                + "\n\n[truncated: file exceeds the per-file collection cap]"
            )
        if total + len(content) > _HARNESS_TOTAL_MAX_CHARS:
            continue
        result.append((rel, content))
        total += len(content)
    return result


# The quality bar, embedded in every prompt so the generated file reads like a
# maintainer wrote it — concrete and command-exact, not generic advice.
_QUALITY_BAR = """\
Quality bar for the file you write (this is what separates a useful AGENTS.md
from noise):
- CONCISE: target under 100 lines. Agents load this file every session — every
  line costs context. No essays, no marketing prose, no filler.
- Commands must be EXACT invocations you verified from the repo (package.json
  scripts, Makefile targets, pyproject/tox/CI config, existing docs). Write
  `npm run test:unit` or `scripts/run_tests.sh tests/foo`, never "run the
  tests". NEVER invent a command you didn't see evidence for.
- No generic advice. "Write tests for new code" and "follow best practices"
  are banned — if a line would be true of any repo, cut it.
- Conventions must be OBSERVED, not assumed: naming patterns, module layout,
  error-handling style, commit-message format — only what the code actually
  shows.
- Include pitfalls that would genuinely trip up a newcomer or an agent
  (required env vars, generated files not to hand-edit, slow test suites,
  ports already in use), if you found any. Skip the section if you found none.
- Markdown structure: a short title + one-paragraph overview, then focused
  sections (e.g. "Dev environment", "Build & test", "Conventions",
  "Pitfalls"). Flat and scannable — no deep nesting."""


def build_init_prompt(
    cwd: str,
    existing_file: str | None = None,
    extra: str = "",
    harness_instructions: list[tuple[str, str]] | None = None,
) -> str:
    """Build the agent prompt for a ``/init`` request.

    Args:
        cwd: the project directory the agent should scan and write
            ``AGENTS.md`` into (usually the session working directory).
        existing_file: the current content of ``AGENTS.md`` if one already
            exists, else ``None``. When present the prompt switches to
            update-and-merge discipline instead of fresh generation.
        extra: free-text the user gave after ``/init`` — emphasis or notes to
            honor while authoring (e.g. "focus on the test setup").
        harness_instructions: ``(rel_path, content)`` pairs collected from
            other harnesses (`.github/instructions/`, `CLAUDE.md`,
            `.cursorrules`). When present, the prompt instructs the agent to
            fold them into the AGENTS.md it writes so rules that only live in
            Copilot/Claude/Cursor files stay active under Hermes.

    Returns:
        A complete instruction the agent runs as a normal turn.
    """
    extra = (extra or "").strip()
    update = existing_file is not None
    parts: list[str] = [
        "[/init] The user wants you to "
        + ("UPDATE the existing" if update else "generate an")
        + f" AGENTS.md project-instructions file for the project at: {cwd}\n",
        "AGENTS.md is the instruction file coding agents (Hermes included) "
        "load as project context every session. It should teach an agent how "
        "to work in THIS repo: what the project is, how to set up, the exact "
        "build/test/lint commands, the conventions the code actually follows, "
        "and the pitfalls that waste time.\n",
        "Do this:\n"
        "1. Inspect the project with your read-only tools (`read_file`, "
        "`search_files`) — start with manifests and toolchain files "
        "(package.json, pyproject.toml, Cargo.toml, go.mod, Makefile, "
        "CI workflow configs, lockfiles), then the directory layout, existing "
        "README/docs, and test/lint configuration. Learn the real commands, "
        "don't guess them.\n"
        "2. Write the file to "
        f"{cwd.rstrip('/')}/AGENTS.md with `write_file`"
        + (" — but this is an UPDATE, so follow the merge discipline below." if update else ".")
        + "\n"
        "3. Confirm to the user the exact path you wrote and summarize in one "
        "or two lines what the file covers.\n",
    ]
    if update:
        parts.append(
            "MERGE DISCIPLINE — an AGENTS.md already exists (its current "
            "content is below). Do NOT overwrite or regenerate it from "
            "scratch. Preserve the user's existing content — their wording, "
            "their sections, their rules — and merge in only what is missing "
            "or verifiably stale (e.g. a command that no longer exists in the "
            "repo). When existing content conflicts with what you observed, "
            "prefer minimal surgical edits over rewrites, and keep the "
            "user's intent. The result must still meet the quality bar.\n\n"
            "CURRENT AGENTS.md CONTENT:\n"
            "<<<EXISTING_AGENTS_MD\n"
            f"{existing_file}\n"
            "EXISTING_AGENTS_MD\n"
        )
    parts.append(_QUALITY_BAR)

    if harness_instructions:
        parts.append(
            "EXTERNAL HARNESS INSTRUCTIONS — this repo carries instruction "
            "docs written for OTHER coding agents (GitHub Copilot's "
            "`.github/instructions/`, Claude Code's `CLAUDE.md`, Cursor's "
            "`.cursorrules`). Hermes auto-loads only AGENTS.md every session, "
            "so those rules are invisible to it unless you fold them in. "
            "EMBED the content below into the AGENTS.md you write — preserving "
            "the rules and intent verbatim (adapt headers to AGENTS.md "
            "section structure, drop only YAML frontmatter), so the file is "
            "self-contained. Content that duplicates what the existing "
            "AGENTS.md already covers may be consolidated, but never dropped. "
            "Do not edit these files in place.\n\n"
            + "\n\n".join(
                f"===== FILE: {rel} =====\n{content}"
                for rel, content in harness_instructions
            )
        )

    if extra:
        parts.append(
            "\nUSER NOTES — honor these while authoring (they override the "
            f"defaults above where they conflict):\n{extra}"
        )
    return "\n".join(parts)


def build_init_prompt_for_cwd(cwd: str | None = None, extra: str = "") -> str:
    """Convenience wrapper used by the dispatch surfaces.

    Resolves ``cwd`` (defaults to the process working directory), reads an
    existing ``AGENTS.md`` there if present, collects instruction docs from
    other agent harnesses in the same directory, and returns the full prompt.
    """
    resolved = os.path.abspath(cwd or os.getcwd())
    existing: str | None = None
    agents_path = os.path.join(resolved, "AGENTS.md")
    try:
        if os.path.isfile(agents_path):
            with open(agents_path, encoding="utf-8", errors="replace") as fh:
                existing = fh.read()
    except OSError:
        existing = None
    collected = _collect_harness_instructions(Path(resolved))
    return build_init_prompt(
        resolved,
        existing_file=existing,
        extra=extra,
        harness_instructions=collected,
    )
