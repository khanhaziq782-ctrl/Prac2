"""Visualize Cargo dependencies for Configuration Management, Variant 23."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections import deque, defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

DEFAULT_REGISTRY = "https://index.crates.io"
USER_AGENT = "variant23-dependency-visualizer/1.0"
MIN_SVG_WIDTH = 560
MIN_SVG_HEIGHT = 180
LAYER_WIDTH = 230
NODE_SPACING = 105
CANVAS_MARGIN = 80
NODE_WIDTH = 150
NODE_HEIGHT = 54
ZERO = 0
ONE = 1
TWO = 2
THREE = 3
SEMVER_COMPONENTS = 3
MAJOR_INDEX = 0
MINOR_INDEX = 1
CARGO_REQUEST_TIMEOUT = 20
FINISHED_COLOR = 2
CRATE_PATH_PREFIX_LENGTH = 2
CRATE_PATH_SEGMENT_END = 4
NODE_X_OFFSET = 10
NODE_Y_OFFSET = 25
TEXT_BASELINE_OFFSET = 7
SUCCESS_EXIT_CODE = 0
ERROR_EXIT_CODE = 1


class DependencyError(Exception):
    """Raised when dependency data cannot be loaded or validated."""


def crate_index_path(name: str) -> str:
    """Return the sparse-index relative path for a Cargo crate."""
    value = name.lower()
    if len(value) == ONE:
        return "1/" + value
    if len(value) == TWO:
        return "2/" + value
    if len(value) == THREE:
        return "3/" + value[0] + "/" + value
    return (
        value[:CRATE_PATH_PREFIX_LENGTH]
        + "/"
        + value[CRATE_PATH_PREFIX_LENGTH:CRATE_PATH_SEGMENT_END]
        + "/"
        + value
    )


def version_key(version: str) -> Tuple[int, int, int, str]:
    """Create a sortable key for ordinary semantic versions."""
    clean = version.strip().lstrip("v")
    main, _, suffix = clean.partition("-")
    numbers = main.split(".")
    try:
        parts = [int(part) for part in numbers[:SEMVER_COMPONENTS]]
    except ValueError:
        parts = [ZERO] * SEMVER_COMPONENTS
    parts += [ZERO] * (SEMVER_COMPONENTS - len(parts))
    return tuple(parts[:SEMVER_COMPONENTS]) + (suffix,)


def _wildcard_matches(version: str, clause: str) -> bool | None:
    """Match wildcard requirements, or return None for other forms."""
    wildcard = re.match(r"^(\d+)(?:\.(\d+))?\.\*$", clause)
    if not wildcard:
        return None
    numbers = version_key(version)
    major_matches = numbers[MAJOR_INDEX] == int(wildcard.group(1))
    minor = wildcard.group(2)
    minor_matches = minor is None or numbers[MINOR_INDEX] == int(minor)
    return major_matches and minor_matches


def _caret_matches(actual: Tuple[int, int, int], wanted: Tuple[int, int, int]) -> bool:
    """Apply Cargo's default caret compatibility rule."""
    if actual < wanted:
        return False
    if wanted[MAJOR_INDEX] > ZERO:
        return actual[MAJOR_INDEX] == wanted[MAJOR_INDEX]
    if wanted[MINOR_INDEX] > ZERO:
        return actual[:TWO] == (ZERO, wanted[MINOR_INDEX])
    return actual[:TWO] == wanted[:TWO]


def _compare_version_parts(
    actual: Tuple[int, int, int],
    wanted: Tuple[int, int, int],
    operator: str,
    requested: str,
) -> bool:
    """Apply one supported comparison operator to semantic version parts."""
    if operator == ">=":
        return actual >= wanted
    if operator == "<=":
        return actual <= wanted
    if operator == ">":
        return actual > wanted
    if operator == "<":
        return actual < wanted
    if operator == "=":
        return actual == wanted
    if operator == "~":
        if actual < wanted:
            return False
        precision = len(requested.split("-")[0].split("."))
        if precision == ONE:
            return actual[MAJOR_INDEX] == wanted[MAJOR_INDEX]
        return actual[:TWO] == wanted[:TWO]
    return _caret_matches(actual, wanted)


def _version_clause_matches(version: str, clause: str) -> bool:
    """Check one comma-separated Cargo version requirement clause."""
    clause = clause.strip()
    pattern = r"^(>=|<=|>|<|=|\^|~)?\s*" r"(\d+(?:\.\d+){0,2}(?:-[0-9A-Za-z.-]+)?)$"
    match = re.match(pattern, clause)
    if not match:
        wildcard_result = _wildcard_matches(version, clause)
        return wildcard_result if wildcard_result is not None else True
    operator, requested = match.groups()
    return _compare_version_parts(
        version_key(version)[:SEMVER_COMPONENTS],
        version_key(requested)[:SEMVER_COMPONENTS],
        operator or "^",
        requested,
    )


def satisfies(version: str, requirement: str) -> bool:
    """Check common Cargo semantic-version requirement expressions."""
    requirement = (requirement or "*").strip()
    if requirement in ("", "*"):
        return True
    alternatives = requirement.split("||")
    return any(
        all(
            _version_clause_matches(version, clause)
            for clause in alternative.split(",")
        )
        for alternative in alternatives
    )


class CargoIndex:
    """Read Cargo sparse-index records over HTTP without Cargo tooling."""

    def __init__(self, base_url: str = DEFAULT_REGISTRY):
        """Document   init   behavior."""
        self.base_url = base_url.rstrip("/") + "/"
        self.cache: Dict[str, List[dict]] = {}

    def records(self, crate: str) -> List[dict]:
        """Document records behavior."""
        if crate in self.cache:
            return self.cache[crate]
        url = self.base_url + crate_index_path(crate)
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "text/plain"}
        )
        try:
            with urllib.request.urlopen(
                request, timeout=CARGO_REQUEST_TIMEOUT
            ) as response:
                body = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
            message = f"Cannot read Cargo index for '{crate}': {exc}"
            raise DependencyError(message) from exc

        records = []
        for line in body.splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise DependencyError(
                        f"Invalid index data for crate '{crate}'."
                    ) from exc
        if not records:
            message = f"Crate '{crate}' was not found in this registry."
            raise DependencyError(message)
        self.cache[crate] = records
        return records

    def exact_version(self, crate: str, version: str) -> dict:
        """Document exact version behavior."""
        for record in self.records(crate):
            if record.get("vers") == version:
                if record.get("yanked"):
                    raise DependencyError(f"Version {crate} {version} is yanked.")
                return record
        message = f"Version '{version}' of crate '{crate}' was not found."
        raise DependencyError(message)

    def latest_compatible(self, crate: str, requirement: str) -> dict:
        """Document latest compatible behavior."""
        candidates = [
            item
            for item in self.records(crate)
            if not item.get("yanked") and satisfies(item.get("vers", ""), requirement)
        ]
        stable = [item for item in candidates if "-" not in item.get("vers", "")]
        if stable:
            candidates = stable
        if not candidates:
            raise DependencyError(
                f"No non-yanked version of '{crate}' matches '{requirement}'."
            )
        return max(candidates, key=lambda item: version_key(item["vers"]))


def dependencies_from_record(record: dict) -> List[str]:
    """Return names for all declared dependency entries."""
    names = []
    for dependency in record.get("deps", []):
        name = dependency.get("name")
        if name:
            names.append(name)
    return sorted(set(names))


def _read_test_repository(path: Path) -> dict:
    """Read and parse the test repository JSON file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DependencyError(f"Test repository file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DependencyError(f"Invalid JSON in test repository: {exc}") from exc


def _validate_test_entry(package: str, dependencies: object) -> List[str]:
    """Validate one uppercase package name and its dependency list."""
    if not isinstance(package, str) or not re.fullmatch(r"[A-Z]+", package):
        raise DependencyError(
            "Test package names must contain uppercase Latin letters only."
        )
    if not isinstance(dependencies, list):
        raise DependencyError(f"Dependencies for '{package}' must be a list.")
    if any(not isinstance(item, str) for item in dependencies):
        raise DependencyError(f"Dependencies for '{package}' must be names.")
    if any(not re.fullmatch(r"[A-Z]+", item) for item in dependencies):
        raise DependencyError(
            f"Dependencies of '{package}' must be uppercase Latin names."
        )
    return sorted(set(dependencies))


def load_test_repository(path: Path) -> Dict[str, List[str]]:
    """Load and validate the uppercase test repository graph."""
    raw = _read_test_repository(path)
    if not isinstance(raw, dict):
        raise DependencyError("Test repository must be a JSON object.")
    graph = {
        package: _validate_test_entry(package, dependencies)
        for package, dependencies in raw.items()
    }
    for dependencies in list(graph.values()):
        for dependency in dependencies:
            graph.setdefault(dependency, [])
    return graph


def _matches_filter(package: str, filter_text: str) -> bool:
    """Return whether a package name is excluded by the substring filter."""
    return bool(filter_text and filter_text.lower() in package.lower())


def _matches_filter(package: str, filter_text: str) -> bool:
    """Return whether a package name is excluded by the substring filter."""
    return bool(filter_text and filter_text.lower() in package.lower())


def build_test_graph(
    root: str, source: Dict[str, List[str]], filter_text: str = ""
) -> Dict[str, List[str]]:
    """Document build test graph behavior."""
    if root not in source:
        raise DependencyError(
            f"Package '{root}' is not present in the test repository."
        )
    graph: Dict[str, List[str]] = {}
    queue = deque([root])
    visited: Set[str] = set()
    while queue:
        package = queue.popleft()
        if package in visited:
            continue
        visited.add(package)
        accepted = [
            dep
            for dep in source.get(package, [])
            if not filter_text or filter_text.lower() not in dep.lower()
        ]
        graph[package] = accepted
        for dep in accepted:
            if dep not in visited:
                queue.append(dep)
    return graph


def build_cargo_graph(
    root: str, version: str, index: CargoIndex, filter_text: str = ""
) -> Dict[str, List[str]]:
    """Document build cargo graph behavior."""
    graph: Dict[str, List[str]] = {}
    selected: Dict[str, dict] = {root: index.exact_version(root, version)}
    queue = deque([root])
    visited: Set[str] = set()

    while queue:
        package = queue.popleft()
        if package in visited:
            continue
        visited.add(package)
        record = selected[package]
        accepted = []
        for dependency in record.get("deps", []):
            name = dependency.get("name")
            if not name or _matches_filter(name, filter_text):
                continue
            accepted.append(name)
            if name not in selected:
                selected[name] = index.latest_compatible(
                    name, dependency.get("req", "*")
                )
            if name not in visited:
                queue.append(name)
        graph[package] = sorted(set(accepted))
    return graph


def _finish_dfs_node(stack, path, positions, color, node) -> None:
    """Mark a fully explored node and remove it from the active DFS path."""
    stack.pop()
    color[node] = FINISHED_COLOR
    positions.pop(node, None)
    path.pop()


def _visit_dfs_neighbor(neighbor, path, positions, color, stack, cycles) -> None:
    """Process a DFS edge and record a back-edge cycle when found."""
    if neighbor not in color:
        color[neighbor] = ZERO
    if color[neighbor] == ZERO:
        color[neighbor] = ONE
        positions[neighbor] = len(path)
        path.append(neighbor)
        stack.append((neighbor, ZERO))
    elif color[neighbor] == ONE and neighbor in positions:
        cycle = path[positions[neighbor] :] + [neighbor]
        if cycle not in cycles:
            cycles.append(cycle)


def _cycles_from_start(start, graph, color) -> List[List[str]]:
    """Explore one DFS component and return cycles found in that component."""
    stack = [(start, ZERO)]
    path = [start]
    positions = {start: ZERO}
    color[start] = ONE
    cycles = []
    while stack:
        node, index = stack[-1]
        neighbors = graph.get(node, [])
        if index >= len(neighbors):
            _finish_dfs_node(stack, path, positions, color, node)
            continue
        neighbor = neighbors[index]
        stack[-1] = (node, index + ONE)
        _visit_dfs_neighbor(neighbor, path, positions, color, stack, cycles)
    return cycles


def find_cycles(graph: Dict[str, List[str]]) -> List[List[str]]:
    """Find directed cycles using iterative depth-first search."""
    color = {node: ZERO for node in graph}
    cycles = []
    for start in graph:
        if color[start] == ZERO:
            cycles.extend(_cycles_from_start(start, graph, color))
    return cycles


def reverse_dependencies(graph: Dict[str, List[str]], target: str) -> List[str]:
    """Document reverse dependencies behavior."""
    return sorted(package for package, deps in graph.items() if target in deps)


def ascii_tree(graph: Dict[str, List[str]], root: str) -> str:
    """Document ascii tree behavior."""
    lines = [root]
    seen = {root}

    def walk(node: str, prefix: str, ancestors: Set[str]) -> None:
        """Document walk behavior."""
        children = graph.get(node, [])
        for index, child in enumerate(children):
            last = index == len(children) - ONE
            branch = "`-- " if last else "|-- "
            if child in ancestors:
                lines.append(prefix + branch + child + " (cycle)")
                continue
            if child in seen:
                lines.append(prefix + branch + child + " (already shown)")
                continue
            lines.append(prefix + branch + child)
            seen.add(child)
            next_prefix = prefix + ("    " if last else "|   ")
            walk(child, next_prefix, ancestors | {child})

    walk(root, "", {root})
    return "\n".join(lines)


def mermaid_text(graph: Dict[str, List[str]]) -> str:
    """Document mermaid text behavior."""
    lines = ["flowchart TD"]
    for node in sorted(graph):
        if not graph[node]:
            lines.append(f'    {node}["{node}"]')
        for dependency in graph[node]:
            lines.append(f"    {node} --> {dependency}")
    return "\n".join(lines) + "\n"


def _svg_dimensions(layers: Dict[int, List[str]]) -> Tuple[int, int]:
    """Calculate canvas dimensions for the layered dependency layout."""
    max_layer = max(layers)
    width = max(MIN_SVG_WIDTH, (max_layer + 1) * LAYER_WIDTH + CANVAS_MARGIN)
    tallest_layer = max(len(items) for items in layers.values())
    height = max(MIN_SVG_HEIGHT, tallest_layer * NODE_SPACING + CANVAS_MARGIN)
    return width, height


def _svg_positions(layers: Dict[int, List[str]]) -> Dict[str, Tuple[int, int]]:
    """Assign each package a coordinate in its graph layer."""
    positions = {}
    for layer, items in layers.items():
        for index, node in enumerate(items):
            x = CANVAS_MARGIN - NODE_X_OFFSET + layer * LAYER_WIDTH
            y = CANVAS_MARGIN - NODE_Y_OFFSET + index * NODE_SPACING
            positions[node] = (x, y)
    return positions


def _svg_header(width: int, height: int) -> List[str]:
    """Return the SVG document header and arrow marker."""
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="7" '
        'refX="9" refY="3.5" orient="auto">',
        '<polygon points="0 0, 10 3.5, 0 7" fill="#526477"/>',
        "</marker></defs>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]


def _svg_edge_lines(
    graph: Dict[str, List[str]], positions: Dict[str, Tuple[int, int]]
) -> List[str]:
    """Create SVG path elements for all dependency edges."""
    parts = []
    for node, dependencies in graph.items():
        x1, y1 = positions[node]
        for dependency in dependencies:
            x2, y2 = positions[dependency]
            parts.append(
                f'<path d="M {x1 + NODE_WIDTH} {y1 + NODE_HEIGHT // TWO} '
                f'L {x2} {y2 + NODE_HEIGHT // TWO}" '
                'stroke="#526477" stroke-width="2" fill="none" '
                'marker-end="url(#arrow)"/>'
            )
    return parts


def _svg_node_lines(
    nodes: List[str], positions: Dict[str, Tuple[int, int]]
) -> List[str]:
    """Create SVG rectangles and labels for package nodes."""
    parts = []
    for node in nodes:
        x, y = positions[node]
        safe_name = node.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append(
            f'<rect x="{x}" y="{y}" width="{NODE_WIDTH}" '
            f'height="{NODE_HEIGHT}" rx="9" fill="#eaf2fb" '
            'stroke="#526477" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{x + NODE_WIDTH // TWO}" '
            f'y="{y + NODE_HEIGHT // TWO + TEXT_BASELINE_OFFSET}" '
            'text-anchor="middle" '
            'font-family="Arial, sans-serif" font-size="16" '
            f'fill="#172b4d">{safe_name}</text>'
        )
    return parts


def svg_text(graph: Dict[str, List[str]]) -> str:
    """Create a self-contained SVG diagram of the dependency graph."""
    nodes = list(graph)
    if not nodes:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" ' 'width="400" height="120"></svg>'
        )
    root = nodes[0]
    depths = {root: 0}
    queue = deque([root])
    while queue:
        current = queue.popleft()
        for child in graph.get(current, []):
            if child not in depths:
                depths[child] = depths[current] + 1
                queue.append(child)
    layers: Dict[int, List[str]] = defaultdict(list)
    for node in nodes:
        layers[depths.get(node, 0)].append(node)
    width, height = _svg_dimensions(layers)
    positions = _svg_positions(layers)
    parts = _svg_header(width, height)
    parts.extend(_svg_edge_lines(graph, positions))
    parts.extend(_svg_node_lines(nodes, positions))
    parts.append("</svg>")
    return "\n".join(parts)


def write_outputs(graph: Dict[str, List[str]], output: Path) -> Tuple[Path, Path]:
    """Document write outputs behavior."""
    output.parent.mkdir(parents=True, exist_ok=True)
    svg_path = output if output.suffix.lower() == ".svg" else output.with_suffix(".svg")
    mermaid_path = svg_path.with_suffix(".mmd")
    svg_path.write_text(svg_text(graph), encoding="utf-8")
    mermaid_path.write_text(mermaid_text(graph), encoding="utf-8")
    return svg_path, mermaid_path


def _validate_package_args(args, parser) -> None:
    """Validate package names and repository URL settings."""
    if not args.package.strip():
        parser.error("--package cannot be empty")
    if not args.test_mode and not re.fullmatch(r"[A-Za-z0-9_-]+", args.package):
        parser.error("--package must be a valid Cargo crate name")
    if args.test_mode and not re.fullmatch(r"[A-Z]+", args.package):
        parser.error("--package must use uppercase Latin letters in test mode")
    if not args.test_mode and not args.repository.startswith(("https://", "http://")):
        parser.error("--repository must use HTTP or HTTPS")


def _validate_mode_args(args, parser) -> None:
    """Validate test-mode and reverse-dependency options."""
    if args.test_mode and not args.test_repo:
        parser.error("--test-mode requires --test-repo PATH")
    if args.test_repo and not args.test_mode:
        parser.error("--test-repo requires --test-mode")
    if args.reverse and args.test_mode:
        if not re.fullmatch(r"[A-Z]+", args.reverse):
            parser.error("--reverse must use uppercase Latin letters in test mode")


def _validate_version_arg(args, parser) -> None:
    """Validate the requested root package version."""
    if not args.test_mode and not args.version:
        parser.error("--version is required outside test mode")
    if args.version and not re.fullmatch(
        r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", args.version
    ):
        parser.error("--version must be a semantic version such as 1.2.3")


def _validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Validate all command-line settings."""
    _validate_mode_args(args, parser)
    _validate_package_args(args, parser)
    _validate_version_arg(args, parser)


def parse_args(argv=None):
    """Parse command-line options and validate their values."""
    parser = argparse.ArgumentParser(
        description="Cargo dependency graph visualizer, Variant 23"
    )
    parser.add_argument("--package", required=True, help="Package/crate name")
    parser.add_argument(
        "--repository", default=DEFAULT_REGISTRY, help="Cargo sparse registry URL"
    )
    parser.add_argument(
        "--version", help="Exact root crate version (required outside test mode)"
    )
    parser.add_argument(
        "--output", default="dependency_graph.svg", help="Output SVG filename"
    )
    parser.add_argument(
        "--ascii", action="store_true", help="Print dependencies as an ASCII tree"
    )
    parser.add_argument(
        "--filter", default="", help="Ignore package names containing this substring"
    )
    parser.add_argument(
        "--test-mode", action="store_true", help="Use a local test repository"
    )
    parser.add_argument("--test-repo", help="Path to JSON test repository file")
    parser.add_argument("--reverse", help="Print packages that depend on this package")
    args = parser.parse_args(argv)
    _validate_args(args, parser)
    return args


def _print_configuration(args: argparse.Namespace) -> None:
    """Print all user-configurable settings as key-value pairs."""
    settings = {
        "package": args.package,
        "repository": args.repository,
        "version": args.version or "(test repository)",
        "test_mode": args.test_mode,
        "test_repository": args.test_repo or "(not used)",
        "output_file": args.output,
        "ascii_tree": args.ascii,
        "filter_substring": args.filter or "(none)",
        "reverse_dependencies_for": args.reverse or "(not requested)",
    }
    print("Configuration:")
    for key, value in settings.items():
        print(f"  {key} = {value}")


def _load_graph(args: argparse.Namespace) -> Dict[str, List[str]]:
    """Load the requested graph from a test file or the Cargo index."""
    if args.test_mode:
        source = load_test_repository(Path(args.test_repo))
        return build_test_graph(args.package, source, args.filter)
    index = CargoIndex(args.repository)
    return build_cargo_graph(args.package, args.version, index, args.filter)


def _print_graph_summary(
    graph: Dict[str, List[str]], package: str, reverse_target: str = ""
) -> None:
    """Print direct dependencies, reverse dependencies, and detected cycles."""
    print("\nDirect dependencies:")
    direct = graph.get(package, [])
    for dependency in direct:
        print(f"  {dependency}")
    if not direct:
        print("  (none)")
    if reverse_target:
        print(f"\nReverse dependencies of {reverse_target}:")
        reverse = reverse_dependencies(graph, reverse_target)
        for name in reverse:
            print(f"  {name}")
        if not reverse:
            print("  (none found in the analyzed graph)")
    cycles = find_cycles(graph)
    print(f"\nPackages analyzed: {len(graph)}")
    edge_count = sum(len(dependencies) for dependencies in graph.values())
    print(f"Dependency edges: {edge_count}")
    print("Cycles detected:")
    if cycles:
        for cycle in cycles:
            print("  " + " -> ".join(cycle))
    else:
        print("  none")


def main(argv=None) -> int:
    """Run the dependency visualizer command-line application."""
    args = parse_args(argv)
    _print_configuration(args)
    try:
        graph = _load_graph(args)
        _print_graph_summary(graph, args.package, args.reverse or "")
        if args.ascii:
            print("\nASCII dependency tree:")
            print(ascii_tree(graph, args.package))
        svg_path, mermaid_path = write_outputs(graph, Path(args.output))
        print(f"\nSVG saved: {svg_path}")
        print(f"Mermaid source saved: {mermaid_path}")
        return SUCCESS_EXIT_CODE
    except DependencyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
