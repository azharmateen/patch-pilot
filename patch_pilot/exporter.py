"""Export patch stacks as PR descriptions, HTML reports, and more."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from .stack import PatchStack, PatchEntry
from .changelog import generate_changelog, generate_conventional_commits


def export_pr_description(
    stack: PatchStack,
    title: str | None = None,
    include_checklist: bool = True,
) -> str:
    """Generate a clean PR description from the patch stack.

    Args:
        stack: The patch stack.
        title: Optional PR title (auto-generated if not provided).
        include_checklist: Include a review checklist.

    Returns:
        Markdown-formatted PR description.
    """
    if not stack.entries:
        return "No changes."

    # Auto-generate title from the most significant commit
    if not title:
        # Pick the feature/bugfix commit, or the first one
        main_entry = stack.entries[0]
        for e in stack.entries:
            if e.concern and e.concern.value in ("feature", "bugfix"):
                main_entry = e
                break
        title = main_entry.message

    lines = [f"# {title}", ""]

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"This PR contains **{stack.size} commits** affecting "
                 f"**{stack.total_files} files** "
                 f"(+{stack.total_insertions}/-{stack.total_deletions}).")
    lines.append("")

    # Changes grouped by concern
    lines.append("## Changes")
    lines.append("")
    lines.append(generate_conventional_commits(stack))
    lines.append("")

    # Commit details
    lines.append("## Commit Details")
    lines.append("")
    lines.append("| SHA | Message | Files | Changes |")
    lines.append("|-----|---------|-------|---------|")
    for entry in stack.entries:
        lines.append(f"| `{entry.short_sha}` | {entry.message} | "
                     f"{entry.files_changed} | +{entry.insertions}/-{entry.deletions} |")
    lines.append("")

    if include_checklist:
        lines.append("## Review Checklist")
        lines.append("")
        lines.append("- [ ] Code follows project conventions")
        lines.append("- [ ] Tests added/updated for new functionality")
        lines.append("- [ ] Documentation updated if needed")
        lines.append("- [ ] No sensitive data (secrets, PII) in the diff")
        lines.append("- [ ] Breaking changes documented")
        lines.append("")

    return "\n".join(lines)


def export_html_report(stack: PatchStack) -> str:
    """Generate an HTML report of the patch stack."""
    changelog_md = generate_changelog(stack)

    rows = ""
    for entry in stack.entries:
        concern_badge = ""
        if entry.concern:
            colors = {
                "feature": "#22c55e",
                "bugfix": "#ef4444",
                "refactor": "#f59e0b",
                "test": "#3b82f6",
                "docs": "#8b5cf6",
                "config": "#6b7280",
                "style": "#ec4899",
                "deps": "#14b8a6",
                "ci": "#f97316",
                "chore": "#9ca3af",
            }
            color = colors.get(entry.concern.value, "#6b7280")
            concern_badge = f'<span style="background:{color};color:white;padding:2px 8px;border-radius:12px;font-size:12px">{entry.concern.value}</span>'

        rows += f"""
        <tr>
            <td><code>{entry.short_sha}</code></td>
            <td>{entry.message} {concern_badge}</td>
            <td>{entry.author}</td>
            <td>{entry.files_changed}</td>
            <td style="color:green">+{entry.insertions}</td>
            <td style="color:red">-{entry.deletions}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Patch Stack Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 960px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; }}
        h1 {{ margin-bottom: 8px; }}
        .stats {{ color: #666; margin-bottom: 24px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
        th {{ background: #f9fafb; font-weight: 600; }}
        tr:hover {{ background: #f3f4f6; }}
        code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
        .stack-viz {{ background: #1a1a2e; color: #e2e8f0; padding: 20px; border-radius: 8px; font-family: monospace; margin: 20px 0; white-space: pre; }}
        footer {{ margin-top: 40px; color: #9ca3af; font-size: 13px; }}
    </style>
</head>
<body>
    <h1>Patch Stack Report</h1>
    <p class="stats">{stack.size} commits &middot; {stack.total_files} files &middot; +{stack.total_insertions}/-{stack.total_deletions}</p>

    <div class="stack-viz">{stack.format_stack(show_stats=True)}</div>

    <h2>Commits</h2>
    <table>
        <thead>
            <tr><th>SHA</th><th>Message</th><th>Author</th><th>Files</th><th>+</th><th>-</th></tr>
        </thead>
        <tbody>{rows}
        </tbody>
    </table>

    <footer>Generated by <a href="https://github.com/patch-pilot/patch-pilot">patch-pilot</a></footer>
</body>
</html>"""

    return html


def export_multiple_prs(stack: PatchStack) -> list[dict[str, str]]:
    """Split the stack into multiple PR descriptions, one per concern group.

    Returns:
        List of dicts with 'title', 'body', and 'commits' keys.
    """
    from .analyzer import ChangeConcern

    # Group by concern
    groups: dict[str | None, list[PatchEntry]] = {}
    for entry in stack.entries:
        key = entry.concern.value if entry.concern else "other"
        if key not in groups:
            groups[key] = []
        groups[key].append(entry)

    prs = []
    for concern_name, entries in groups.items():
        mini_stack = PatchStack(entries=entries, base_ref=stack.base_ref, head_ref=stack.head_ref)
        title = f"{concern_name}: {entries[0].message}"
        body = export_pr_description(mini_stack, title=title, include_checklist=True)
        prs.append({
            "title": title,
            "body": body,
            "commits": [e.sha for e in entries],
        })

    return prs


def export_to_files(
    stack: PatchStack,
    output_dir: str | Path,
    formats: list[str] | None = None,
) -> list[Path]:
    """Export patch stack to files in various formats.

    Args:
        stack: The patch stack.
        output_dir: Directory to write files.
        formats: List of formats: 'pr', 'html', 'changelog', 'commits'.

    Returns:
        List of generated file paths.
    """
    if formats is None:
        formats = ["pr", "html", "changelog"]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = []

    if "pr" in formats:
        path = output_dir / "PR_DESCRIPTION.md"
        path.write_text(export_pr_description(stack), encoding="utf-8")
        files.append(path)

    if "html" in formats:
        path = output_dir / "stack-report.html"
        path.write_text(export_html_report(stack), encoding="utf-8")
        files.append(path)

    if "changelog" in formats:
        path = output_dir / "CHANGELOG.md"
        path.write_text(generate_changelog(stack), encoding="utf-8")
        files.append(path)

    if "commits" in formats:
        path = output_dir / "commits.txt"
        path.write_text(generate_conventional_commits(stack), encoding="utf-8")
        files.append(path)

    return files
