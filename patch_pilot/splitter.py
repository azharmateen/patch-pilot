"""Split large commits or branches into logical atomic commits."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .analyzer import ChangeGroup, FileChange, ChangeConcern, analyze_diff, group_changes, _run_git


@dataclass
class SplitPlan:
    """A plan for splitting changes into atomic commits."""

    groups: list[ChangeGroup]
    total_files: int = 0
    total_insertions: int = 0
    total_deletions: int = 0

    def summary(self) -> str:
        lines = [
            "Split Plan",
            "=" * 50,
            f"Total: {self.total_files} files, +{self.total_insertions}/-{self.total_deletions}",
            f"Commits: {len(self.groups)}",
            "",
        ]
        for i, group in enumerate(self.groups, 1):
            lines.append(f"  {i}. [{group.concern.value}] {group.description}")
            lines.append(f"     {group.file_count} files, +{sum(f.insertions for f in group.files)}/-{sum(f.deletions for f in group.files)}")
            for f in group.files[:5]:
                status_symbol = {"A": "+", "M": "~", "D": "-", "R": ">"}.get(f.status, "?")
                lines.append(f"     {status_symbol} {f.path}")
            if group.file_count > 5:
                lines.append(f"     ... and {group.file_count - 5} more")
            lines.append("")

        return "\n".join(lines)


def plan_split(
    base: str = "main",
    head: str = "HEAD",
    cwd: str | Path | None = None,
) -> SplitPlan:
    """Analyze a branch and create a split plan.

    Args:
        base: Base ref to diff against.
        head: Head ref (current branch tip).
        cwd: Working directory.

    Returns:
        SplitPlan with grouped changes.
    """
    changes = analyze_diff(base, head, cwd=cwd)
    groups = group_changes(changes)

    return SplitPlan(
        groups=groups,
        total_files=len(changes),
        total_insertions=sum(c.insertions for c in changes),
        total_deletions=sum(c.deletions for c in changes),
    )


def _generate_commit_message(group: ChangeGroup) -> str:
    """Generate a conventional commit message for a change group."""
    prefix_map = {
        ChangeConcern.FEATURE: "feat",
        ChangeConcern.BUGFIX: "fix",
        ChangeConcern.REFACTOR: "refactor",
        ChangeConcern.TEST: "test",
        ChangeConcern.DOCS: "docs",
        ChangeConcern.CONFIG: "chore",
        ChangeConcern.STYLE: "style",
        ChangeConcern.DEPS: "build",
        ChangeConcern.CI: "ci",
        ChangeConcern.CHORE: "chore",
    }

    prefix = prefix_map.get(group.concern, "chore")

    # Try to determine scope from common directory
    paths = [Path(f.path) for f in group.files]
    dirs = set()
    for p in paths:
        if len(p.parts) > 1:
            dirs.add(p.parts[0])

    scope = ""
    if len(dirs) == 1:
        scope = f"({dirs.pop()})"
    elif len(dirs) <= 3:
        scope = f"({','.join(sorted(dirs))})"

    description = group.description.lower()
    if description.startswith(group.concern.value):
        description = description[len(group.concern.value):].strip()

    return f"{prefix}{scope}: {description}"


def execute_split(
    plan: SplitPlan,
    base: str = "main",
    cwd: str | Path | None = None,
    dry_run: bool = True,
) -> list[str]:
    """Execute the split plan by creating individual commits.

    WARNING: This modifies git history. Only use on feature branches.

    Args:
        plan: The split plan to execute.
        base: Base ref to reset to before applying.
        cwd: Working directory.
        dry_run: If True, only show what would be done.

    Returns:
        List of commit messages that were (or would be) created.
    """
    messages = []

    for group in plan.groups:
        msg = _generate_commit_message(group)
        messages.append(msg)

        if dry_run:
            continue

        # Stage only the files in this group
        file_paths = [f.path for f in group.files]
        for fp in file_paths:
            try:
                _run_git(["add", "--", fp], cwd=cwd)
            except RuntimeError:
                pass  # File might be deleted

        # Create the commit
        _run_git(["commit", "-m", msg], cwd=cwd)

    return messages


def suggest_split_from_staged(cwd: str | Path | None = None) -> SplitPlan:
    """Analyze staged changes and suggest how to split them.

    Useful when you have a large set of staged changes and want to
    split them into multiple focused commits before committing.
    """
    from .analyzer import analyze_staged
    changes = analyze_staged(cwd=cwd)
    groups = group_changes(changes)

    return SplitPlan(
        groups=groups,
        total_files=len(changes),
        total_insertions=sum(c.insertions for c in changes),
        total_deletions=sum(c.deletions for c in changes),
    )
