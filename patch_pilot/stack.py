"""Manage and visualize patch stacks."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .analyzer import _run_git, ChangeConcern


@dataclass
class PatchEntry:
    """A single commit in the patch stack."""

    sha: str
    short_sha: str
    message: str
    author: str
    date: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    concern: ChangeConcern | None = None

    @property
    def one_line(self) -> str:
        return f"{self.short_sha} {self.message}"


@dataclass
class PatchStack:
    """An ordered stack of patches (commits)."""

    entries: list[PatchEntry] = field(default_factory=list)
    base_ref: str = "main"
    head_ref: str = "HEAD"

    @property
    def size(self) -> int:
        return len(self.entries)

    @property
    def total_files(self) -> int:
        return sum(e.files_changed for e in self.entries)

    @property
    def total_insertions(self) -> int:
        return sum(e.insertions for e in self.entries)

    @property
    def total_deletions(self) -> int:
        return sum(e.deletions for e in self.entries)

    def format_stack(self, show_stats: bool = True) -> str:
        """Format the stack as a readable string with visual indicators."""
        if not self.entries:
            return "Empty stack (no commits between {self.base_ref} and {self.head_ref})"

        lines = [
            f"Patch Stack: {self.base_ref}..{self.head_ref}",
            f"{'=' * 60}",
            f"{self.size} commits, {self.total_files} files, +{self.total_insertions}/-{self.total_deletions}",
            "",
        ]

        # Visual stack (newest on top)
        for i, entry in enumerate(self.entries):
            is_top = i == 0
            is_bottom = i == len(self.entries) - 1
            prefix = ">" if is_top else "|"

            concern_badge = ""
            if entry.concern:
                concern_badge = f" [{entry.concern.value}]"

            line = f"  {prefix} {entry.short_sha} {entry.message}{concern_badge}"
            if show_stats:
                line += f"  ({entry.files_changed} files, +{entry.insertions}/-{entry.deletions})"
            lines.append(line)

            if not is_bottom:
                lines.append("  |")

        lines.append(f"  * {self.base_ref}")

        return "\n".join(lines)

    def format_dependency_graph(self) -> str:
        """Format a simple dependency graph based on file overlap."""
        if len(self.entries) < 2:
            return "Not enough commits for dependency analysis."

        lines = ["Dependency Graph (file overlap)", "=" * 40]

        # Build file sets per commit
        # Note: We use the commit message as identifier since we may not have file lists
        # In a real implementation, we'd compute file overlap from the diffs
        for i, entry in enumerate(self.entries):
            deps = []
            for j, other in enumerate(self.entries):
                if i != j and _might_depend(entry, other):
                    deps.append(other.short_sha)

            dep_str = " -> " + ", ".join(deps) if deps else " (independent)"
            lines.append(f"  {entry.short_sha}{dep_str}")

        return "\n".join(lines)


def _might_depend(a: PatchEntry, b: PatchEntry) -> bool:
    """Heuristic: two patches might depend if they share the same concern."""
    if a.concern and b.concern and a.concern == b.concern:
        return True
    return False


def _classify_commit_message(message: str) -> ChangeConcern | None:
    """Classify a commit by its conventional commit prefix."""
    msg = message.lower().strip()
    mapping = {
        "feat": ChangeConcern.FEATURE,
        "fix": ChangeConcern.BUGFIX,
        "refactor": ChangeConcern.REFACTOR,
        "test": ChangeConcern.TEST,
        "docs": ChangeConcern.DOCS,
        "style": ChangeConcern.STYLE,
        "build": ChangeConcern.DEPS,
        "ci": ChangeConcern.CI,
        "chore": ChangeConcern.CHORE,
    }
    for prefix, concern in mapping.items():
        if msg.startswith(prefix + ":") or msg.startswith(prefix + "("):
            return concern
    return None


def get_stack(
    base: str = "main",
    head: str = "HEAD",
    cwd: str | Path | None = None,
) -> PatchStack:
    """Get the current patch stack between two refs.

    Args:
        base: Base ref (e.g., 'main', 'origin/main').
        head: Head ref (e.g., 'HEAD', branch name).
        cwd: Working directory.

    Returns:
        PatchStack with all commits between base and head.
    """
    # Get commit log with stats
    log_format = "%H%n%h%n%s%n%an%n%aI%n---"
    log_output = _run_git(
        ["log", f"--format={log_format}", "--stat", f"{base}..{head}"],
        cwd=cwd,
    )

    stack = PatchStack(base_ref=base, head_ref=head)

    if not log_output.strip():
        return stack

    # Parse log output
    entries_raw = log_output.split("---")
    for raw in entries_raw:
        lines = [l for l in raw.strip().splitlines() if l.strip()]
        if len(lines) < 5:
            continue

        sha = lines[0].strip()
        short_sha = lines[1].strip()
        message = lines[2].strip()
        author = lines[3].strip()
        date = lines[4].strip()

        # Parse stats from remaining lines
        files_changed = 0
        insertions = 0
        deletions = 0
        for line in lines[5:]:
            if "file" in line and "changed" in line:
                import re
                fc = re.search(r"(\d+) files? changed", line)
                ins = re.search(r"(\d+) insertions?", line)
                dels = re.search(r"(\d+) deletions?", line)
                if fc:
                    files_changed = int(fc.group(1))
                if ins:
                    insertions = int(ins.group(1))
                if dels:
                    deletions = int(dels.group(1))

        concern = _classify_commit_message(message)

        stack.entries.append(PatchEntry(
            sha=sha,
            short_sha=short_sha,
            message=message,
            author=author,
            date=date,
            files_changed=files_changed,
            insertions=insertions,
            deletions=deletions,
            concern=concern,
        ))

    return stack


def suggest_reorder(stack: PatchStack) -> list[PatchEntry]:
    """Suggest a reordering of patches for better reviewability.

    Order: config/deps first, then refactor, then feature, then tests, then docs.
    """
    priority = {
        ChangeConcern.DEPS: 0,
        ChangeConcern.CONFIG: 1,
        ChangeConcern.CI: 2,
        ChangeConcern.REFACTOR: 3,
        ChangeConcern.FEATURE: 4,
        ChangeConcern.BUGFIX: 5,
        ChangeConcern.TEST: 6,
        ChangeConcern.STYLE: 7,
        ChangeConcern.DOCS: 8,
        ChangeConcern.CHORE: 9,
    }

    def sort_key(entry: PatchEntry) -> tuple[int, str]:
        p = priority.get(entry.concern, 50) if entry.concern else 50
        return (p, entry.date)

    return sorted(stack.entries, key=sort_key)


def suggest_squash(stack: PatchStack) -> list[list[PatchEntry]]:
    """Suggest which commits could be squashed together.

    Groups commits with the same concern that are adjacent or near-adjacent.
    """
    if not stack.entries:
        return []

    groups: list[list[PatchEntry]] = []
    current_group = [stack.entries[0]]

    for entry in stack.entries[1:]:
        if (entry.concern and current_group[-1].concern and
                entry.concern == current_group[-1].concern):
            current_group.append(entry)
        else:
            groups.append(current_group)
            current_group = [entry]

    groups.append(current_group)
    return groups
