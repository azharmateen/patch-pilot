"""Analyze git diffs and classify changes by concern."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ChangeConcern(Enum):
    """Classification of a code change by its concern."""

    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    TEST = "test"
    DOCS = "docs"
    CONFIG = "config"
    STYLE = "style"
    DEPS = "deps"
    CI = "ci"
    CHORE = "chore"


@dataclass
class FileChange:
    """A single file change with classification."""

    path: str
    status: str  # 'A' (added), 'M' (modified), 'D' (deleted), 'R' (renamed)
    insertions: int = 0
    deletions: int = 0
    concern: ChangeConcern = ChangeConcern.FEATURE
    diff_content: str = ""

    @property
    def total_changes(self) -> int:
        return self.insertions + self.deletions


@dataclass
class ChangeGroup:
    """A group of related file changes that belong to one logical concern."""

    concern: ChangeConcern
    files: list[FileChange] = field(default_factory=list)
    description: str = ""

    @property
    def total_changes(self) -> int:
        return sum(f.total_changes for f in self.files)

    @property
    def file_count(self) -> int:
        return len(self.files)


# Path patterns for classification
_PATH_RULES: list[tuple[re.Pattern, ChangeConcern]] = [
    (re.compile(r"(^|/)tests?/|_test\.\w+$|\.test\.\w+$|\.spec\.\w+$|^test_"), ChangeConcern.TEST),
    (re.compile(r"(^|/)\.github/|Jenkinsfile|\.gitlab-ci|Dockerfile|docker-compose|\.circleci"), ChangeConcern.CI),
    (re.compile(r"requirements.*\.txt$|package\.json$|Gemfile|go\.sum$|Cargo\.lock$|poetry\.lock$|\.lock$"), ChangeConcern.DEPS),
    (re.compile(r"(^|/)docs?/|\.md$|\.rst$|\.txt$|LICENSE|CHANGELOG|AUTHORS"), ChangeConcern.DOCS),
    (re.compile(r"\.ya?ml$|\.toml$|\.ini$|\.cfg$|\.conf$|Makefile$|\.env"), ChangeConcern.CONFIG),
    (re.compile(r"\.css$|\.scss$|\.less$|\.styled\.\w+$"), ChangeConcern.STYLE),
]

# Diff content patterns
_CONTENT_RULES: list[tuple[re.Pattern, ChangeConcern]] = [
    (re.compile(r"^\+.*\b(fix|bug|patch|hotfix|resolve|workaround)\b", re.I | re.M), ChangeConcern.BUGFIX),
    (re.compile(r"^\+.*\b(rename|extract|refactor|move|reorganize|simplify|clean)\b", re.I | re.M), ChangeConcern.REFACTOR),
]


def _run_git(args: list[str], cwd: str | Path | None = None) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True, text=True, cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _classify_file(path: str, diff_content: str = "") -> ChangeConcern:
    """Classify a file change by path and diff content."""
    for pattern, concern in _PATH_RULES:
        if pattern.search(path):
            return concern

    for pattern, concern in _CONTENT_RULES:
        if pattern.search(diff_content):
            return concern

    return ChangeConcern.FEATURE


def analyze_diff(base: str = "main", head: str = "HEAD", cwd: str | Path | None = None) -> list[FileChange]:
    """Analyze the diff between two git refs.

    Args:
        base: Base ref (e.g., 'main', 'origin/main').
        head: Head ref (e.g., 'HEAD', branch name).
        cwd: Working directory (must be inside a git repo).

    Returns:
        List of FileChange objects with classifications.
    """
    # Get the list of changed files with stats
    numstat = _run_git(["diff", "--numstat", f"{base}...{head}"], cwd=cwd)
    name_status = _run_git(["diff", "--name-status", f"{base}...{head}"], cwd=cwd)

    status_map: dict[str, str] = {}
    for line in name_status.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            status = parts[0][0]  # First char: A, M, D, R
            filepath = parts[-1]  # Last part is the file path (handles renames)
            status_map[filepath] = status

    changes: list[FileChange] = []
    for line in numstat.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue

        insertions = int(parts[0]) if parts[0] != "-" else 0
        deletions = int(parts[1]) if parts[1] != "-" else 0
        filepath = parts[2]

        # Get the actual diff content for this file
        try:
            diff_content = _run_git(["diff", f"{base}...{head}", "--", filepath], cwd=cwd)
        except RuntimeError:
            diff_content = ""

        status = status_map.get(filepath, "M")
        concern = _classify_file(filepath, diff_content)

        changes.append(FileChange(
            path=filepath,
            status=status,
            insertions=insertions,
            deletions=deletions,
            concern=concern,
            diff_content=diff_content,
        ))

    return changes


def group_changes(changes: list[FileChange]) -> list[ChangeGroup]:
    """Group file changes by concern.

    Args:
        changes: List of classified file changes.

    Returns:
        List of ChangeGroup objects, one per unique concern.
    """
    groups: dict[ChangeConcern, ChangeGroup] = {}

    for change in changes:
        if change.concern not in groups:
            groups[change.concern] = ChangeGroup(
                concern=change.concern,
                description=f"{change.concern.value} changes",
            )
        groups[change.concern].files.append(change)

    # Sort by: features first, then tests, then the rest
    priority = {
        ChangeConcern.FEATURE: 0,
        ChangeConcern.BUGFIX: 1,
        ChangeConcern.REFACTOR: 2,
        ChangeConcern.TEST: 3,
        ChangeConcern.DOCS: 4,
        ChangeConcern.CONFIG: 5,
        ChangeConcern.STYLE: 6,
        ChangeConcern.DEPS: 7,
        ChangeConcern.CI: 8,
        ChangeConcern.CHORE: 9,
    }

    sorted_groups = sorted(groups.values(), key=lambda g: priority.get(g.concern, 99))

    # Generate better descriptions
    for group in sorted_groups:
        paths = [f.path for f in group.files]
        if group.concern == ChangeConcern.TEST:
            group.description = f"Add/update tests ({len(paths)} files)"
        elif group.concern == ChangeConcern.DOCS:
            group.description = f"Update documentation ({len(paths)} files)"
        elif group.concern == ChangeConcern.CONFIG:
            group.description = f"Update configuration ({', '.join(Path(p).name for p in paths[:3])})"
        elif group.concern == ChangeConcern.DEPS:
            group.description = f"Update dependencies ({', '.join(Path(p).name for p in paths[:3])})"
        elif group.concern == ChangeConcern.CI:
            group.description = f"Update CI/CD pipeline"
        elif group.concern == ChangeConcern.FEATURE:
            # Try to identify the feature area from common path prefixes
            dirs = set()
            for p in paths:
                parts = Path(p).parts
                if len(parts) > 1:
                    dirs.add(parts[0] if parts[0] != "src" and len(parts) > 1 else parts[1] if len(parts) > 1 else parts[0])
            if dirs:
                group.description = f"Implement feature in {', '.join(sorted(dirs)[:3])}"
            else:
                group.description = f"Implement feature ({len(paths)} files)"
        elif group.concern == ChangeConcern.BUGFIX:
            group.description = f"Fix bugs ({len(paths)} files)"
        elif group.concern == ChangeConcern.REFACTOR:
            group.description = f"Refactor ({len(paths)} files)"

    return sorted_groups


def analyze_staged(cwd: str | Path | None = None) -> list[FileChange]:
    """Analyze currently staged (but uncommitted) changes."""
    numstat = _run_git(["diff", "--cached", "--numstat"], cwd=cwd)
    name_status = _run_git(["diff", "--cached", "--name-status"], cwd=cwd)

    status_map: dict[str, str] = {}
    for line in name_status.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            status_map[parts[-1]] = parts[0][0]

    changes: list[FileChange] = []
    for line in numstat.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue

        insertions = int(parts[0]) if parts[0] != "-" else 0
        deletions = int(parts[1]) if parts[1] != "-" else 0
        filepath = parts[2]

        try:
            diff_content = _run_git(["diff", "--cached", "--", filepath], cwd=cwd)
        except RuntimeError:
            diff_content = ""

        status = status_map.get(filepath, "M")
        concern = _classify_file(filepath, diff_content)

        changes.append(FileChange(
            path=filepath, status=status, insertions=insertions,
            deletions=deletions, concern=concern, diff_content=diff_content,
        ))

    return changes
