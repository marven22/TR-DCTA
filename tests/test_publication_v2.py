from mcx.publication_v2 import graph_spec, masked_edges, stratified_splits


def test_graph_has_three_sources_twenty_one_candidates_and_overlap():
    graph = graph_spec("example")
    assert len(graph["source_ids"]) == 3
    assert len(graph["candidate_ids"]) == 21
    assert len(graph["formation_edges"]) == 32
    indegree = {node: 0 for node in graph["candidate_ids"]}
    for _, child in graph["formation_edges"]:
        indegree[child] += 1
    assert all(indegree[node] > 1 for node in graph["shared_ids"])


def test_masks_are_exact_and_nested_only_by_count_not_assumed():
    graph = graph_spec("example")
    assert len(masked_edges("example", graph["formation_edges"], 0.0)) == 32
    assert len(masked_edges("example", graph["formation_edges"], 0.25)) == 24
    assert len(masked_edges("example", graph["formation_edges"], 0.50)) == 16


def test_stratified_split_counts():
    assert list(stratified_splits([f"a{i}" for i in range(20)]).values()).count("test") == 12
    assert list(stratified_splits([f"b{i}" for i in range(49)]).values()).count("test") == 29
