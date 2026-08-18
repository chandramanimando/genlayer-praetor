import pytest

from praetor import (
    Praetor, AFFIRMED, REJECTED, FIRST_INSTANCE, FINAL, CONF_HIGH, CONF_MED,
)


class FakeCalls:
    def __init__(self, responses):
        self.responses = list(responses)
        self.models_used = []

    def ask_ai(self, prompt, model):
        self.models_used.append(model)
        return self.responses.pop(0)


def deploy(responses):
    court = Praetor()
    court.calls = FakeCalls(responses)
    return court


def test_submit_claim_stores_normalized_verdict():
    court = deploy(['{"verdict": "AFFIRMED", "confidence": 91}'])
    cid = court.submit_claim("logo design", "ipfs://Qm...", "matches brand brief")
    claim = court.get_claim(cid)
    assert claim["verdict"] == AFFIRMED
    assert claim["confidence"] == CONF_HIGH
    assert claim["status"] == FIRST_INSTANCE
    assert court.get_final_verdict(cid) is None  # not final yet


def test_appeal_uses_independent_model_and_finalizes():
    court = deploy([
        '{"verdict": "REJECTED", "confidence": 70}',
        '{"verdict": "AFFIRMED", "confidence": 60}',
    ])
    cid = court.submit_claim("backend module", "pr:42", "passes all tests")
    court.appeal(cid)
    claim = court.get_claim(cid)
    assert claim["status"] == FINAL
    assert claim["verdict"] == AFFIRMED
    assert claim["appealed"] is True
    assert court.models_used == [court.first_model, court.appellate_model]
    assert court.get_final_verdict(cid) == AFFIRMED


def test_finalize_waives_appeal():
    court = deploy(['{"verdict": "REJECTED", "confidence": 40}'])
    cid = court.submit_claim("article", "url:...", "no plagiarism")
    court.finalize(cid)
    assert court.get_claim(cid)["status"] == FINAL
    with pytest.raises(AssertionError):
        court.appeal(cid)  # cannot appeal a final claim


def test_parse_tolerates_prose_wrapped_json():
    court = deploy(['Sure! Here is my ruling: {"verdict": "rejected", "confidence": 57} thanks'])
    cid = court.submit_claim("x", "y", "z")
    claim = court.get_claim(cid)
    assert claim["verdict"] == REJECTED
    assert claim["confidence"] == CONF_MED


def test_schema_violation_retries_then_fails():
    court = deploy(['I cannot answer in JSON', 'still no json'])
    with pytest.raises(ValueError):
        court.submit_claim("x", "y", "z")
    assert len(court.models_used) == 2  # exactly one retry


def test_equivalence_of_normalized_states():
    a = {"claims": {0: {"verdict": AFFIRMED, "status": FINAL}}}
    b = {"claims": {0: {"verdict": AFFIRMED, "status": FINAL}}}
    court = deploy([])
    assert court.equivalence(a, b) is True
    b["claims"][0]["verdict"] = REJECTED
    assert court.equivalence(a, b) is False
