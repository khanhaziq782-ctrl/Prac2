import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dependency_visualizer import (
    ascii_tree, build_test_graph, find_cycles, load_test_repository,
    reverse_dependencies, satisfies, mermaid_text, svg_text
)


class Variant23Tests(unittest.TestCase):
    def setUp(self):
        """Test setUp."""
        project_root = Path(__file__).resolve().parents[1]
        self.path = project_root / "testdata" / "repository.json"
        self.source = load_test_repository(self.path)

    def test_bfs_transitive_graph(self):
        """Test test bfs transitive graph."""
        graph = build_test_graph("A", self.source)
        self.assertEqual(set(graph), {"A", "B", "C", "D", "E", "F"})

    def test_filter(self):
        """Test test filter."""
        graph = build_test_graph("A", self.source, "C")
        self.assertNotIn("C", graph["A"])

    def test_cycle_detection(self):
        """Test test cycle detection."""
        graph = build_test_graph("A", self.source)
        self.assertTrue(find_cycles(graph))

    def test_reverse_dependencies(self):
        """Test test reverse dependencies."""
        graph = build_test_graph("A", self.source)
        self.assertEqual(reverse_dependencies(graph, "D"), ["B", "C"])

    def test_ascii_tree(self):
        """Test test ascii tree."""
        graph = build_test_graph("A", self.source)
        self.assertIn("A", ascii_tree(graph, "A"))
        self.assertIn("cycle", ascii_tree(graph, "A"))

    def test_mermaid_and_svg(self):
        """Test test mermaid and svg."""
        graph = build_test_graph("A", self.source)
        self.assertIn("flowchart TD", mermaid_text(graph))
        self.assertIn("<svg", svg_text(graph))

    def test_implicit_leaf_nodes(self):
        """Test test implicit leaf nodes."""
        from dependency_visualizer import build_test_graph
        graph = build_test_graph("A", {"A": ["Z"]})
        self.assertEqual(graph["Z"], [])

    def test_semver_requirements(self):
        """Test test semver requirements."""
        self.assertTrue(satisfies("1.5.0", "^1.2.0"))
        self.assertFalse(satisfies("2.0.0", "^1.2.0"))
        self.assertTrue(satisfies("1.2.5", "~1.2.0"))


if __name__ == "__main__":
    unittest.main()
