"""CLI for patch-pilot: clean git workflow tool."""

from __future__ import annotations

from pathlib import Path

import click

from .analyzer import analyze_diff, group_changes
from .splitter import plan_split, execute_split, suggest_split_from_staged
from .stack import get_stack, suggest_reorder, suggest_squash
from .changelog import generate_changelog
from .exporter import export_pr_description, export_html_report, export_to_files


@click.group()
@click.version_option()
def cli():
    """patch-pilot: Turn messy branches into clean, reviewable patch stacks."""


@cli.command()
@click.option("--base", default="main", help="Base branch to diff against")
@click.option("--head", default="HEAD", help="Head ref")
@click.option("--execute", "do_execute", is_flag=True, help="Actually create the commits (default: dry-run)")
def split(base: str, head: str, do_execute: bool):
    """Split current branch changes into logical atomic commits.

    Analyzes the diff between base and HEAD, groups changes by concern
    (feature, test, docs, config, etc.), and creates individual commits.

    By default runs as dry-run. Use --execute to apply.
    """
    try:
        plan = plan_split(base=base, head=head)
    except RuntimeError as e:
        click.echo(f"Error: {e}")
        click.echo("Make sure you're in a git repository with commits ahead of the base branch.")
        return

    click.echo(plan.summary())

    if do_execute:
        click.echo("\nExecuting split...")
        messages = execute_split(plan, base=base, dry_run=False)
        click.echo(f"Created {len(messages)} commits.")
    else:
        click.echo("(dry-run) Use --execute to apply this split.")


@cli.command()
@click.option("--base", default="main", help="Base branch")
@click.option("--head", default="HEAD", help="Head ref")
@click.option("--stats/--no-stats", default=True, help="Show file stats")
def stack(base: str, head: str, stats: bool):
    """Show the current patch stack with visual representation.

    Displays all commits between base and HEAD as a visual stack
    with concern classification, file counts, and change stats.
    """
    try:
        patch_stack = get_stack(base=base, head=head)
    except RuntimeError as e:
        click.echo(f"Error: {e}")
        return

    click.echo(patch_stack.format_stack(show_stats=stats))
    click.echo("")
    click.echo(patch_stack.format_dependency_graph())


@cli.command()
@click.option("--base", default="main", help="Base branch")
@click.option("--head", default="HEAD", help="Head ref")
def reorder(base: str, head: str):
    """Suggest optimal commit ordering for reviewability.

    Recommends putting deps/config first, then refactors, features,
    tests, and docs last.
    """
    try:
        patch_stack = get_stack(base=base, head=head)
    except RuntimeError as e:
        click.echo(f"Error: {e}")
        return

    if not patch_stack.entries:
        click.echo("No commits to reorder.")
        return

    click.echo("Current order:")
    for i, e in enumerate(patch_stack.entries, 1):
        concern = f"[{e.concern.value}]" if e.concern else "[?]"
        click.echo(f"  {i}. {e.short_sha} {concern} {e.message}")

    suggested = suggest_reorder(patch_stack)
    click.echo("\nSuggested order:")
    for i, e in enumerate(suggested, 1):
        concern = f"[{e.concern.value}]" if e.concern else "[?]"
        click.echo(f"  {i}. {e.short_sha} {concern} {e.message}")

    squash_groups = suggest_squash(patch_stack)
    squashable = [g for g in squash_groups if len(g) > 1]
    if squashable:
        click.echo("\nSquash suggestions:")
        for group in squashable:
            shas = ", ".join(e.short_sha for e in group)
            concern = group[0].concern.value if group[0].concern else "mixed"
            click.echo(f"  Squash [{concern}]: {shas}")


@cli.command()
@click.option("--base", default="main", help="Base branch")
@click.option("--head", default="HEAD", help="Head ref")
@click.option("-v", "--version", "ver", default=None, help="Version string (e.g., 1.2.0)")
@click.option("--shas/--no-shas", default=True, help="Include commit SHAs")
@click.option("--authors/--no-authors", default=False, help="Include author names")
def changelog(base: str, head: str, ver: str | None, shas: bool, authors: bool):
    """Generate a changelog from the patch stack.

    Outputs a markdown changelog grouped by concern type with
    conventional commit formatting.
    """
    try:
        patch_stack = get_stack(base=base, head=head)
    except RuntimeError as e:
        click.echo(f"Error: {e}")
        return

    output = generate_changelog(patch_stack, version=ver, include_shas=shas, include_authors=authors)
    click.echo(output)


@cli.command()
@click.option("--base", default="main", help="Base branch")
@click.option("--head", default="HEAD", help="Head ref")
@click.option("-o", "--output", default="patch-pilot-export/", help="Output directory")
@click.option("-f", "--format", "formats", multiple=True,
              type=click.Choice(["pr", "html", "changelog", "commits"]),
              help="Output formats (default: pr, html, changelog)")
def export(base: str, head: str, output: str, formats: tuple[str, ...]):
    """Export the patch stack in various formats.

    Generates PR descriptions, HTML reports, changelogs, and commit summaries.
    """
    try:
        patch_stack = get_stack(base=base, head=head)
    except RuntimeError as e:
        click.echo(f"Error: {e}")
        return

    fmt_list = list(formats) if formats else None
    files = export_to_files(patch_stack, output_dir=output, formats=fmt_list)

    click.echo(f"Exported {len(files)} files to {output}/:")
    for f in files:
        click.echo(f"  - {f.name}")


@cli.command()
@click.option("--base", default="main", help="Base branch")
@click.option("--head", default="HEAD", help="Head ref")
def analyze(base: str, head: str):
    """Analyze branch changes and show classification.

    Shows how each changed file is classified by concern (feature,
    test, docs, config, etc.) and how they group together.
    """
    try:
        changes = analyze_diff(base=base, head=head)
    except RuntimeError as e:
        click.echo(f"Error: {e}")
        return

    if not changes:
        click.echo("No changes found.")
        return

    groups = group_changes(changes)

    click.echo(f"Found {len(changes)} changed files in {len(groups)} groups:\n")
    for group in groups:
        click.echo(f"  [{group.concern.value}] {group.description}")
        for f in group.files:
            status_symbol = {"A": "+", "M": "~", "D": "-", "R": ">"}.get(f.status, "?")
            click.echo(f"    {status_symbol} {f.path} (+{f.insertions}/-{f.deletions})")
        click.echo("")


if __name__ == "__main__":
    cli()
