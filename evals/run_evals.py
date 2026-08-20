import os
import sys
import json
from decimal import Decimal

# Ensure backend package is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from approval_loop.domain.models import ActionType
from approval_loop.agent.drafter import GeminiAgentDrafter

def run_evals():
    eval_file = os.path.join(os.path.dirname(__file__), "eval_scenarios.json")
    with open(eval_file, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    drafter = GeminiAgentDrafter()
    print("==================================================")
    print("ApprovalLoop LLM Drafter & Output Eval Suite")
    print("==================================================")

    passed_count = 0
    total_count = len(scenarios)

    for sc in scenarios:
        sc_id = sc["id"]
        inp = sc["input"]
        rubric = sc["rubric"]

        output = drafter.draft_wording(
            action_type=ActionType(inp["action_type"]),
            report_id=inp["report_id"],
            submitter=inp["submitter"],
            amount=Decimal(inp["amount"]),
            currency=inp["currency"],
            description=inp["description"]
        )

        failures = []
        for term in rubric.get("must_contain", []):
            if term not in output:
                failures.append(f"Missing required term: '{term}'")

        for term in rubric.get("prohibited_terms", []):
            if term.lower() in output.lower():
                failures.append(f"Contains prohibited term: '{term}'")

        if len(output) < rubric.get("min_length", 0):
            failures.append(f"Output too short ({len(output)} chars)")
        if len(output) > rubric.get("max_length", 1000):
            failures.append(f"Output too long ({len(output)} chars)")

        if not failures:
            passed_count += 1
            print(f"[PASS] {sc_id}: {sc['description']}")
            print(f"       Preview: {output[:70]}...")
        else:
            print(f"[FAIL] {sc_id}: {sc['description']}")
            print(f"       Generated: {output}")
            for f in failures:
                print(f"       - {f}")

    print("==================================================")
    print(f"Eval Results: {passed_count}/{total_count} passed ({passed_count/total_count*100:.1f}%)")
    print("==================================================")
    return passed_count == total_count

if __name__ == "__main__":
    success = run_evals()
    sys.exit(0 if success else 1)
