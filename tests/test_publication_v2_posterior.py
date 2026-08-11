from mcx.publication_v2_posterior import stable_seed


def test_particle_seed_is_stable_and_archive_specific():
    assert stable_seed("a", 10) == stable_seed("a", 10)
    assert stable_seed("a", 10) != stable_seed("b", 10)
