# patch-pilot

**Turn messy git branches into clean, reviewable patch stacks.**

One command to split a giant branch into atomic commits grouped by concern, generate changelogs, and export PR descriptions your reviewers will actually read.

## Demo

```bash
# See how your branch would split
patch-pilot split --base main

# View your patch stack with dependency graph
patch-pilot stack

# Get reorder and squash suggestions
patch-pilot reorder

# Generate a changelog
patch-pilot changelog --version 1.3.0

# Export PR description + HTML report
patch-pilot export -o review/
```

## Quickstart

```bash
pip install patch-pilot

# Navigate to your git repo
cd my-project

# See how patch-pilot classifies your changes
patch-pilot analyze --base main

# Preview the split plan (dry-run by default)
patch-pilot split --base main

# Apply the split
patch-pilot split --base main --execute
```

## Features

- **Smart classification**: Automatically categorizes changes as feature, bugfix, refactor, test, docs, config, deps, or CI based on file paths and diff content
- **Atomic split**: Groups related changes and creates focused commits with conventional commit messages
- **Stack visualization**: See your entire commit stack with concern badges, file counts, and a dependency graph
- **Reorder suggestions**: Recommends optimal commit ordering (deps first, then refactors, features, tests, docs)
- **Squash detection**: Identifies consecutive commits with the same concern that should be squashed
- **Changelog generation**: Markdown changelog grouped by concern with conventional commit formatting
- **PR export**: Clean PR descriptions with summary tables, commit details, and review checklists
- **HTML reports**: Visual stack reports you can share with your team
- **Zero dependencies** beyond Click -- works with any git repository

## Commands

| Command | Purpose |
|---------|---------|
| `split` | Split branch into logical atomic commits |
| `stack` | Show current stack with visual representation |
| `reorder` | Suggest optimal commit ordering |
| `changelog` | Generate markdown changelog |
| `export` | Export as PR description, HTML, changelog |
| `analyze` | Show file classification details |

## Architecture

```
Git Branch (messy)
       |
   Analyzer (classify by path + content)
       |
   +---+---+
   |       |
 Splitter  Stack Manager
   |       |
   |   +---+---+---+
   |   |   |   |   |
   | Reorder Squash Graph
   |
   +----> Atomic Commits (clean)
              |
         +----+----+
         |    |    |
       PR   HTML  Changelog
```

1. **Analyzer** classifies each changed file by concern using path heuristics and diff content analysis
2. **Splitter** groups files by concern and generates atomic commits with conventional messages
3. **Stack Manager** provides reorder suggestions, squash detection, and dependency graphs
4. **Exporter** generates PR descriptions, HTML reports, and changelogs

## Contributing

1. Fork the repo
2. Create a feature branch
3. Use `patch-pilot` itself to review your changes
4. Submit a PR

## License

MIT
