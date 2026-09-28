"""verify's fact-check: inference counts, definitions pass, subjects must match.

The annotation axis (#1161) caught this check flagging correct core
answers as unsupported — "BTC와 비트코인은 같은 디지털 자산을 지칭한다",
"Anthropic … develops … Claude" — 5 times in 3 runs, despite the prompt
already exempting common knowledge. Two causes in the old wording: a
"directly supported" bar that rejected any equivalence the data implied
without stating, and a single common-knowledge example ("AI is a
technology") the model did not generalise.

Relaxing either is how "Alex Karp is Anthropic's CEO" gets through, so
the rewrite carries two limits, and these tests pin all four parts.
They pin the *rules*, not behaviour — whether the model follows them is
what the paired measurement is for.

Run:
  python -m pytest tests/test_verify_factcheck_rules.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.reasoning.verify import (  # noqa: E402
    FACT_CHECK_PROMPT_EN,
    FACT_CHECK_PROMPT_KO,
)

KO, EN = FACT_CHECK_PROMPT_KO, FACT_CHECK_PROMPT_EN


def test_the_literal_bar_is_gone():
    """'직접 지지' / 'directly supported' is what rejected the equivalence
    between "비트코인(BTC)" and "BTC와 비트코인은 같다"."""
    assert "직접 지지되는지" not in KO
    assert "directly supported" not in EN


@pytest.mark.parametrize("tmpl,tokens", [
    (KO, ["바꿔 말하거나 번역한 것", "곧바로 따라 나오는 결론",
          "'IBIT 는 블랙록이 발행한다' 는 뒷받침됨",
          "'BTC 와 비트코인은 같다' 는 뒷받침됨"]),
    (EN, ["paraphrase or translation", "follows directly from the data",
          "'BlackRock issues IBIT' is supported",
          "'BTC and Bitcoin are the same' is supported"]),
])
def test_paraphrase_and_direct_inference_count_as_support(tmpl, tokens):
    """Both examples are the traced failures: Q19 (reflect, same fault)
    and the BTC false alarms (this check)."""
    for tok in tokens:
        assert tok in tmpl, tok


@pytest.mark.parametrize("tmpl,defs,attrs", [
    (KO, ["정의 · 약어 · 분류", "'BTC 는 비트코인의 약어'"],
         ["특정 대상의 구체 속성", "누가 CEO 인가", "자료로만"]),
    (EN, ["definitions, abbreviations", "'BTC is the ticker for Bitcoin'"],
         ["specific entity's attributes", "who its CEO is",
          "judge them against the data only"]),
])
def test_common_knowledge_means_definitions_not_entity_attributes(
        tmpl, defs, attrs):
    """A CEO's name is 'widely known' and time-varying — the fixture files
    Q17 under 'ceo-change'. Letting it pass as common knowledge would stop
    verify flagging 'Dario Amodei' on a corpus that does not carry it."""
    for tok in defs + attrs:
        assert tok in tmpl, tok


@pytest.mark.parametrize("tmpl,tokens", [
    (KO, ["**같은 대상**", "'Palantir CEO Alex Karp'",
          "'Anthropic 의 CEO 는 Alex Karp' 는 unsupported"]),
    (EN, ["**same subject**", "'Palantir CEO Alex Karp'",
          "'Anthropic's CEO is Alex Karp' is unsupported"]),
])
def test_inference_holds_only_about_the_same_subject(tmpl, tokens):
    """The #1151 wrong-subject guard, carried into verify. Without it the
    inference rule above is exactly how 'Alex Karp' would pass."""
    for tok in tokens:
        assert tok in tmpl, tok


@pytest.mark.parametrize("tmpl", [KO, EN])
def test_template_still_formats_and_keeps_the_json_shape(tmpl):
    out = tmpl.format(query="Q", answer="A", context="C")
    for ph in ("{query}", "{answer}", "{context}"):
        assert ph not in out
    assert '{"grounded": true|false, "unsupported":' in out
