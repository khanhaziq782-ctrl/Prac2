# Variant 23 — Cargo Dependency Graph Visualizer

A command-line dependency visualizer for the Rust Cargo registry. The program reads
Cargo sparse-index records directly over HTTP using Python's standard library. It
does not invoke Cargo or use a package-manager library to retrieve dependencies.

## Requirements

- Python 3.10 or newer
- Internet access for real Cargo registry mode
- No third-party Python packages

## Project structure

```text
variant23_dependency_visualizer/
├── README.md
├── .gitignore
├── run.bat
├── src/
│   └── dependency_visualizer.py
├── tests/
│   └── test_graph.py
├── testdata/
│   └── repository.json
└── examples/
```

## Stage 1 — CLI configuration

All settings are supplied through command-line options:

| Option | Meaning |
|---|---|
| `--package` | Root package name |
| `--repository` | Cargo sparse-index URL; defaults to `https://index.crates.io` |
| `--version` | Exact root crate version |
| `--output` | Output SVG filename |
| `--ascii` | Print the dependency tree |
| `--filter` | Ignore dependency names containing the substring |
| `--test-mode` | Enable local test mode |
| `--test-repo` | JSON file describing the test graph |
| `--reverse` | Show packages that depend on the specified package |

Examples of parameter validation:

```powershell
python src/dependency_visualizer.py --package serde
python src/dependency_visualizer.py --package serde --version abc
python src/dependency_visualizer.py --package A --test-mode
python src/dependency_visualizer.py --package A --test-mode --test-repo testdata/repository.json
```

The first three commands intentionally demonstrate missing/invalid parameter errors.

## Stage 2 — Cargo data collection

Cargo uses a sparse registry index. For a crate, the program computes its index path
and downloads the corresponding newline-delimited JSON record directly with
`urllib.request`. It selects the exact requested root version, reads its `deps`
records, and resolves transitive dependency versions using their declared version
requirements. Optional and target-specific dependency records are included.

Example:

```powershell
python src/dependency_visualizer.py --package serde --version 1.0.219
```

The exact version above is an example; use a version currently present in the registry.

## Stage 3 — Graph operations

The graph is built with iterative Breadth-First Search (BFS) using a queue. A visited
set prevents infinite traversal. The filter is applied to dependency names. A
separate iterative depth-first traversal detects directed cycles.

Test repository format:

```json
{
  "A": ["B", "C"],
  "B": ["D"],
  "C": ["D", "E"],
  "D": ["F"],
  "E": [],
  "F": ["B"]
}
```

Run:

```powershell
python src/dependency_visualizer.py --package A --test-mode --test-repo testdata/repository.json --ascii
python src/dependency_visualizer.py --package A --test-mode --test-repo testdata/repository.json --filter C
```

## Stage 4 — Reverse dependencies

Reverse dependencies are incoming edges: packages that list the selected package
as a dependency in the analyzed graph.

```powershell
python src/dependency_visualizer.py --package A --test-mode --test-repo testdata/repository.json --reverse D
```

## Stage 5 — Mermaid, SVG and ASCII tree

Every successful run creates:
- an SVG image at the path supplied by `--output`;
- a Mermaid diagram source with the same base name and `.mmd` extension.

ASCII tree output is optional:

```powershell
python src/dependency_visualizer.py --package A --test-mode --test-repo testdata/repository.json --ascii --output examples/A.svg
python src/dependency_visualizer.py --package G --test-mode --test-repo testdata/repository.json --ascii --output examples/G.svg
python src/dependency_visualizer.py --package H --test-mode --test-repo testdata/repository.json --ascii --output examples/H.svg
```

These are three different demonstration roots from the uppercase test repository.
The graph is rendered to SVG by the program; the Mermaid text is also saved for
inspection or rendering by a Mermaid-compatible viewer.

## Tests

Run from the project directory:

```powershell
python -m unittest discover -s tests -v
```

## Comparison with Cargo

For a real crate, compare the dependency relationships with Cargo's standard tree
command (if the Rust toolchain is installed):

```powershell
cargo tree --manifest-path path\to\a\Cargo.toml
```

The application itself does not call `cargo tree`; this command is only an external
comparison. Results can differ because this implementation includes optional and
target-specific index dependency records, while Cargo resolves dependencies in the
context of a particular manifest, feature selection, target platform, lockfile and
resolver version. Cargo may also select versions based on a lockfile, whereas this
prototype selects the latest non-yanked version matching each requirement.

## Suggested Conventional Commits

Create commits after completing each stage:

```text
feat(config): add command line configuration and validation
feat(cargo): read direct dependencies from Cargo sparse index
feat(graph): build dependency graph with iterative BFS
feat(reverse): add reverse dependency lookup
feat(visualization): export Mermaid and SVG dependency graphs
test: add graph traversal and cycle detection tests
docs: document usage and variant 23 requirements
```

## Known limitations

This is an educational implementation. The small semver matcher covers common
Cargo requirements but is not a complete implementation of the SemVer/Cargo
resolver specification. It does not evaluate feature activation, target predicates,
workspace resolution, lockfiles, or registry authentication. Therefore, the
comparison with Cargo may show differences for complex projects.


## Code quality fixes

The source has been refactored to address the static-analysis findings:

- Functions are kept below 40 lines.
- Source lines are kept at or below 80 characters.
- Functions and test methods have docstrings.
- Complex validation, version comparison, and cycle traversal are split into
  smaller helper functions.
- Repeated layout and algorithm values use named constants.
- Generated Python cache files are excluded from version control.

Run the test suite after making changes:

```powershell
python -m unittest discover -s tests -v
```

## Conventional Commit messages

Use the Conventional Commits format `type(scope): description`. For future
changes, use messages such as:

```text
refactor(graph): simplify dependency traversal
refactor(cli): separate argument validation
refactor(cargo): split version requirement checks
refactor(svg): separate layout and SVG element generation
test: cover dependency graph behavior
docs: document code quality checks
```

The commit-message rule applies to Git history, not source files. If the remote
repository already contains non-conforming commits, changing the README cannot
rename those commits. Update the history with an interactive rebase, then push
the rewritten branch only if you are authorized to do so.

See [GIT_HISTORY_FIX.md](GIT_HISTORY_FIX.md) for safe guidance on existing commit messages.
