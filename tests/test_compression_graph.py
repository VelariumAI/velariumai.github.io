"""Tests for graph compression."""

from vcse.compression.graph import GraphIndex


def test_graph_add_claim():
    g = GraphIndex()
    g.add_claim("A", "is_a", "B")
    assert ("is_a", "B") in g.neighbors("A")


def test_graph_no_duplicate_edges():
    g = GraphIndex()
    g.add_claim("A", "is_a", "B")
    g.add_claim("A", "is_a", "B")
    g.add_claim("A", "is_a", "B")
    edges = g.neighbors("A")
    assert edges.count(("is_a", "B")) == 1


def test_graph_multiple_neighbors():
    g = GraphIndex()
    g.add_claim("A", "is_a", "B")
    g.add_claim("A", "related_to", "C")
    edges = g.neighbors("A")
    assert len(edges) == 2


def test_graph_sorted_neighbors():
    g = GraphIndex()
    g.add_claim("A", "z_relation", "Z")
    g.add_claim("A", "a_relation", "B")
    edges = g.neighbors("A")
    assert edges[0][0] == "a_relation"
    assert edges[1][0] == "z_relation"


def test_graph_nodes_sorted():
    g = GraphIndex()
    g.add_claim("zebra", "is_a", "animal")
    g.add_claim("apple", "is_a", "fruit")
    nodes = g.nodes()
    assert nodes == ["apple", "zebra"]


def test_graph_edge_count():
    g = GraphIndex()
    g.add_claim("A", "is_a", "B")
    g.add_claim("A", "related_to", "C")
    g.add_claim("X", "is_a", "Y")
    assert g.edge_count() == 3


def test_graph_missing_node():
    g = GraphIndex()
    g.add_claim("A", "is_a", "B")
    assert g.neighbors("Z") == []


def test_graph_to_dict():
    g = GraphIndex()
    g.add_claim("A", "is_a", "B")
    g.add_claim("A", "related_to", "C")
    d = g.to_dict()
    assert "A" in d
    assert len(d["A"]) == 2


def test_graph_from_dict():
    data = {"A": [["is_a", "B"], ["related_to", "C"]], "X": [["part_of", "Y"]]}
    g = GraphIndex.from_dict(data)
    assert ("is_a", "B") in g.neighbors("A")
    assert ("part_of", "Y") in g.neighbors("X")
    assert g.edge_count() == 3


def test_graph_bidirectional():
    g = GraphIndex()
    g.add_claim("A", "is_a", "B")
    g.add_claim("B", "related_to", "A")
    assert ("is_a", "B") in g.neighbors("A")
    assert ("related_to", "A") in g.neighbors("B")