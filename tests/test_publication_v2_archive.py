from mcx.publication_v2_archive import _decoys, public_memory


def test_public_memory_strips_policy():
    value = {"recommended_policy_id": "secret", "lesson": "l",
             "expected_outcome": "e", "cited_memory_ids": ["m1"]}
    assert public_memory(value) == {"lesson": "l", "expected_outcome": "e",
                                    "cited_memory_ids": ["m1"]}


def test_decoys_are_not_true_edges():
    edges = [["s_a", "m_b"], ["m_b", "m_c"]]
    decoys = _decoys("t", ["s_a", "m_b", "m_c", "m_d"], edges, 2)
    assert len(decoys) == 2
    assert not set(map(tuple, decoys)) & set(map(tuple, edges))
