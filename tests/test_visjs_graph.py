"""Tests for app.utils.generate_visjs_data (proximity-graph data for vis.js)."""

import app.utils as utils


def _graph():
    return {
        "H1": [
            {"other_id": "H2", "similarity": 0.85},
            {"other_id": "H3", "similarity": 0.1},  # below the 0.2 display threshold
        ],
        "H2": [{"other_id": "H1", "similarity": 0.85}],
        "H3": [],
    }


def test_nodes_generated_for_every_hypothesis():
    data = utils.generate_visjs_data(_graph())
    assert {n["id"] for n in data["nodes"]} == {"H1", "H2", "H3"}
    assert all(n["label"] == n["id"] for n in data["nodes"])


def test_edges_filtered_by_similarity_threshold():
    data = utils.generate_visjs_data(_graph())
    pairs = {(e["from"], e["to"]) for e in data["edges"]}
    assert ("H1", "H2") in pairs
    assert ("H1", "H3") not in pairs  # 0.1 <= 0.2 threshold


def test_edge_labels_formatted_to_two_decimals():
    data = utils.generate_visjs_data(_graph())
    edge = next(e for e in data["edges"] if e["from"] == "H1")
    assert edge["label"] == "0.85"
    assert edge["arrows"] == "to"


def test_invalid_input_returns_empty_graph():
    assert utils.generate_visjs_data(None) == {"nodes": [], "edges": []}
    assert utils.generate_visjs_data("not a dict") == {"nodes": [], "edges": []}


def test_malformed_connections_skipped():
    graph = {"H1": [{"bad": "entry"}, {"other_id": "H2", "similarity": 0.5}], "H2": "not-a-list"}
    data = utils.generate_visjs_data(graph)
    assert len(data["edges"]) == 1
    assert data["edges"][0]["to"] == "H2"
