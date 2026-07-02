"""Offline tests for the judge against recorded fixture bundles.

These validate the judge's plumbing deterministically: that it surfaces the
right evidence to the model, passes the model's verdict through, and degrades to
'uncertain' on failure. Scoring quality itself is exercised in the live run.
"""

from __future__ import annotations

from pathlib import Path

from agentic_qa.judge import Verdict, build_messages, judge
from agentic_qa.schema import ObservationBundle
from tests.conftest import FakeLLM

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> ObservationBundle:
    return ObservationBundle.model_validate_json((FIXTURES / name).read_text())


def test_fixtures_load():
    good = load("bundle_good_transfer.json")
    broken = load("bundle_broken_billpay.json")
    assert good.finished_reason == "agent_finished"
    assert broken.finished_reason == "max_failures"


async def test_judge_passes_through_model_verdict():
    good = load("bundle_good_transfer.json")
    expected = Verdict(status="pass", category="functional", severity="low",
                       reasoning="Confirmation page shown, no errors.", confidence=0.9)
    llm = FakeLLM([expected])
    verdict = await judge(good, llm=llm)
    assert verdict == expected
    assert llm.calls == 1


def test_judge_prompt_surfaces_failure_evidence():
    broken = load("bundle_broken_billpay.json")
    messages = build_messages(broken)
    prompt = messages[-1]["content"]
    # The judge must see the smoking guns from the broken flow.
    assert "max_failures" in prompt
    assert "NullPointerException" in prompt
    assert '"status": 500' in prompt
    assert "internal error" in prompt.lower()


def test_judge_prompt_includes_rag_context_when_given():
    good = load("bundle_good_transfer.json")
    messages = build_messages(good, extra_context="A transfer MUST reduce the source balance.")
    assert "MUST reduce the source balance" in messages[-1]["content"]


async def test_judge_falls_back_to_uncertain_on_llm_error():
    good = load("bundle_good_transfer.json")

    class RaisingLLM:
        async def chat_structured(self, **kwargs):
            raise RuntimeError("model exploded")

    verdict = await judge(good, llm=RaisingLLM(), max_attempts=2)
    assert verdict.status == "uncertain"
    assert verdict.confidence == 0.0
    assert "model exploded" in verdict.reasoning
