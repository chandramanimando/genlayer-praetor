"""
Praetor — a two-instance AI adjudication primitive for GenLayer.

Praetor is a reusable "court-as-oracle": other intelligent contracts call it
to resolve subjective conditions (deliverable accepted? SLA breached?
insurance event occurred?) without each contract re-implementing AI logic.

Design principles (consensus-aware):
1. NORMALIZED STATE — raw model output is never stored. Only a verdict enum
   and a bucketed confidence level are written to state, so independent
   validator re-executions converge on identical state (equivalence-friendly).
2. TWO-INSTANCE FLOW — a trial verdict (model A) can be appealed to an
   independent appellate model (model B), mirroring real adjudication and
   reducing single-model bias.
3. STRICT SCHEMA — models must answer in JSON; schema violations are retried
   once, then the transaction fails cleanly instead of corrupting state.
"""
import json

from genlayer import *

# --- Normalized enums (the ONLY things ever written to state) ---
AFFIRMED = "AFFIRMED"
REJECTED = "REJECTED"

CONF_LOW = "LOW"
CONF_MED = "MEDIUM"
CONF_HIGH = "HIGH"

FIRST_INSTANCE = "FIRST_INSTANCE"
FINAL = "FINAL"


class Praetor(Contract):
    """
    State layout:
        claims[claim_id] = {
            "subject":    str,   # what is being adjudicated
            "criteria":   str,   # the acceptance rule / contract clause
            "evidence":   str,   # pointer to evidence (URI / hash / text)
            "status":     FIRST_INSTANCE | FINAL,
            "verdict":    AFFIRMED | REJECTED,
            "confidence": LOW | MEDIUM | HIGH,
            "appealed":   bool,
        }
    """

    def __init__(self, first_model: str = "gpt-4o", appellate_model: str = "gpt-4o-mini"):
        super().__init__()
        self.first_model = first_model
        self.appellate_model = appellate_model
        self.next_claim_id = 0
        self.claims = {}

    # ------------------------------ ENTRIES ------------------------------

    @contract.entry
    def submit_claim(self, subject: str, evidence: str, criteria: str) -> int:
        """Open a claim and hear the first instance."""
        verdict, confidence = self._hear(
            model=self.first_model,
            subject=subject,
            evidence=evidence,
            criteria=criteria,
            prior_verdict=None,
        )
        claim_id = self.next_claim_id
        self.next_claim_id += 1
        self.claims[claim_id] = {
            "subject": subject,
            "criteria": criteria,
            "evidence": evidence,
            "status": FIRST_INSTANCE,
            "verdict": verdict,
            "confidence": confidence,
            "appealed": False,
        }
        return claim_id

    @contract.entry
    def appeal(self, claim_id: int):
        """Escalate a first-instance verdict to the appellate model."""
        claim = self.claims[claim_id]
        assert claim["status"] == FIRST_INSTANCE, "claim is already final"

        verdict, confidence = self._hear(
            model=self.appellate_model,
            subject=claim["subject"],
            evidence=claim["evidence"],
            criteria=claim["criteria"],
            prior_verdict=claim["verdict"],
        )
        claim["verdict"] = verdict
        claim["confidence"] = confidence
        claim["status"] = FINAL
        claim["appealed"] = True

    @contract.entry
    def finalize(self, claim_id: int):
        """Waive the appeal window and make the first-instance verdict final."""
        claim = self.claims[claim_id]
        assert claim["status"] == FIRST_INSTANCE, "claim is already final"
        claim["status"] = FINAL

    # ------------------------------- VIEWS -------------------------------

    @contract.view
    def get_claim(self, claim_id: int):
        return self.claims[claim_id]

    @contract.view
    def get_final_verdict(self, claim_id: int):
        """Client contracts use this: returns None until the claim is final."""
        claim = self.claims[claim_id]
        if claim["status"] != FINAL:
            return None
        return claim["verdict"]

    @contract.view
    def get_court_config(self):
        return {
            "first_model": self.first_model,
            "appellate_model": self.appellate_model,
            "claims": self.next_claim_id,
        }

    # ---------------------------- EQUIVALENCE ----------------------------

    @contract.equivalence
    def equivalence(self, a, b):
        """
        Equivalence-aware design: because state contains ONLY normalized
        enums (verdict + bucketed confidence) and never raw model text,
        exact state equality is achievable across independent validator
        re-executions whenever validators agree on the decision.
        """
        return a == b

    # ----------------------------- INTERNALS -----------------------------

    def _hear(self, model, subject, evidence, criteria, prior_verdict):
        """Run one judicial round: prompt -> model -> strict parse (1 retry)."""
        prompt = self._build_prompt(subject, evidence, criteria, prior_verdict)
        last_error = None
        for _ in range(2):  # retry once on schema violation, then fail clean
            raw = self.calls.ask_ai(prompt=prompt, model=model)
            try:
                return self._parse_verdict(raw)
            except ValueError as error:
                last_error = error
        raise last_error

    @staticmethod
    def _build_prompt(subject, evidence, criteria, prior_verdict):
        prior = (
            f"A first-instance court already ruled: {prior_verdict}. "
            "You are the appellate court. Review independently.\n"
            if prior_verdict
            else ""
        )
        return (
            "You are a judge on a decentralized adjudication network.\n"
            f"SUBJECT: {subject}\n"
            f"EVIDENCE: {evidence}\n"
            f"RULE TO APPLY: {criteria}\n"
            f"{prior}"
            "Decide strictly by applying the RULE to the EVIDENCE.\n"
            'Respond with ONLY this JSON: {"verdict": "AFFIRMED"|"REJECTED", '
            '"confidence": 0-100}'
        )

    @staticmethod
    def _parse_verdict(raw: str):
        """Extract and validate the JSON verdict; normalize confidence."""
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("no JSON object in model response")
        data = json.loads(raw[start:end + 1])

        verdict = str(data.get("verdict", "")).upper()
        if verdict not in (AFFIRMED, REJECTED):
            raise ValueError("verdict outside schema")

        try:
            score = float(data.get("confidence", 50))
        except (TypeError, ValueError):
            score = 50.0
        if score >= 80:
            confidence = CONF_HIGH
        elif score >= 55:
            confidence = CONF_MED
        else:
            confidence = CONF_LOW
        return verdict, confidence
