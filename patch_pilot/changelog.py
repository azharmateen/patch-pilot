"""Generate changelogs from patch stacks."""

from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from .analyzer import ChangeConcern
from .stack import PatchStack, PatchEntry


@dataclass
class ChangelogSection:
    """A section in the changelog (e.g., Features, Bug Fixes)."""

    title: str
    emoji: str
    entries: list[str]


def _section_for_concern(concern: ChangeConcern | None) -> tuple[str, str, int]:
    """Map a concern to a changelog section (title, emoji, sort order)."""
    mapping = {
        ChangeConcern.FEATURE: ("Features", "sparkles", 0),
        ChangeConcern.BUGFIX: ("Bug Fixes", "bug", 1),
        ChangeConcern.REFACTOR: ("Refactoring", "recycle", 2),
        ChangeConcern.TEST: ("Tests", "white_check_mark", 3),
        ChangeConcern.DOCS: ("Documentation", "memo", 4),
        ChangeConcern.STYLE: ("Styling", "art", 5),
        ChangeConcern.DEPS: ("Dependencies", "package", 6),
        ChangeConcern.CI: ("CI/CD", "construction_worker", 7),
        ChangeConcern.CONFIG: ("Configuration", "wrench", 8),
        ChangeConcern.CHORE: ("Chores", "broom", 9),
    }
    if concern and concern in mapping:
        return mapping[concern]
    return ("Other", "pushpin", 99)


def _clean_message(message: str) -> str:
    """Strip conventional commit prefix to get clean description."""
    import re
    # Remove conventional commit prefix like "feat(scope): "
    cleaned = re.sub(r"^(feat|fix|refactor|test|docs|style|build|ci|chore|perf)(\([^)]*\))?:\s*", "", message)
    # Capitalize first letter
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def generate_changelog(
    stack: PatchStack,
    version: str | None = None,
    include_shas: bool = True,
    include_authors: bool = False,
) -> str:
    """Generate a markdown changelog from a patch stack.

    Args:
        stack: The patch stack to generate changelog from.
        version: Optional version string (e.g., "1.2.0").
        include_shas: Include commit short SHAs.
        include_authors: Include author names.

    Returns:
        Markdown-formatted changelog string.
    """
    if not stack.entries:
        return "No changes to document."

    # Group entries by concern section
    sections: dict[str, ChangelogSection] = {}
    section_order: dict[str, int] = {}

    for entry in stack.entries:
        title, emoji, order = _section_for_concern(entry.concern)

        if title not in sections:
            sections[title] = ChangelogSection(title=title, emoji=emoji, entries=[])
            section_order[title] = order

        desc = _clean_message(entry.message)
        parts = [f"- {desc}"]
        if include_shas:
            parts.append(f" (`{entry.short_sha}`)")
        if include_authors:
            parts.append(f" - {entry.author}")
        sections[title].entries.append("".join(parts))

    # Build markdown
    date_str = datetime.now().strftime("%Y-%m-%d")
    header = f"## {version}" if version else "## Unreleased"
    header += f" ({date_str})"

    lines = [header, ""]

    sorted_sections = sorted(sections.values(), key=lambda s: section_order.get(s.title, 99))

    for section in sorted_sections:
        if section.entries:
            lines.append(f"### {section.title}")
            lines.append("")
            for entry_text in section.entries:
                lines.append(entry_text)
            lines.append("")

    # Summary stats
    lines.append("---")
    lines.append(f"*{stack.size} commits, {stack.total_files} files changed, "
                 f"+{stack.total_insertions}/-{stack.total_deletions}*")

    return "\n".join(lines)


def generate_conventional_commits(stack: PatchStack) -> str:
    """Generate a conventional commit summary (plain text, no markdown)."""
    lines = []
    for entry in stack.entries:
        prefix = "feat"
        if entry.concern:
            prefix_map = {
                ChangeConcern.FEATURE: "feat",
                ChangeConcern.BUGFIX: "fix",
                ChangeConcern.REFACTOR: "refactor",
                ChangeConcern.TEST: "test",
                ChangeConcern.DOCS: "docs",
                ChangeConcern.STYLE: "style",
                ChangeConcern.DEPS: "build",
                ChangeConcern.CI: "ci",
                ChangeConcern.CONFIG: "chore",
                ChangeConcern.CHORE: "chore",
            }
            prefix = prefix_map.get(entry.concern, "feat")

        lines.append(f"{prefix}: {_clean_message(entry.message)} ({entry.short_sha})")

    return "\n".join(lines)
