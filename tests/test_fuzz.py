from benchmarks import checks, fuzz


def test_random_documents_round_trip():
    assert [seed for seed, _ in fuzz.failures(checks.Engine(), 300)] == []
