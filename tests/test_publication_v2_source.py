from mcx.publication_v2_source import fit_source_estimator, similarity


def test_similarity_is_bounded_and_symmetric():
    assert similarity("pick red block", "red block") == similarity("red block", "pick red block")
    assert 0 <= similarity("a", "b") <= 1


def test_source_estimator_learns_separable_rows():
    rows = [((0.0, 0.0), 0), ((0.1, 0.0), 0), ((0.9, 1.0), 1), ((1.0, .9), 1)]
    model = fit_source_estimator(rows)
    assert model.score((1.0, 1.0)) > model.score((0.0, 0.0))


def test_source_prior_floor_preserves_support():
    model = fit_source_estimator([((0.0,), 0), ((0.1,), 0), ((.9,), 1), ((1.0,), 1)])
    archive = {"source_ids": ["a", "b", "c"], "target_language": "x",
               "observed_formation_edges": [], "memories": {
                   key: {"lesson": str(index), "expected_outcome": ""}
                   for index, key in enumerate(("a", "b", "c"))}}
    assert min(model.prior(archive, .05).values()) >= .05
