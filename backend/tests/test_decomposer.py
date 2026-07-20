"""The decomposer both PLANS the charts and VALIDATES the prompt in one LLM call —
an off-topic or misuse prompt is rejected deterministically via an `ok: false` verdict,
so no chart is ever produced for 'what is 2+2'."""

import pytest

from models import ColumnInfo, ColumnType, Schema
from pipeline.decomposer import Decomposer, PromptRejected
from pipeline.providers.base import LLMProvider


class StubProvider(LLMProvider):
    def __init__(self, response: str):
        self.response = response
        self.model = "stub"

    def complete(self, system: str, user: str) -> str:
        return self.response


def _schema():
    cols = [ColumnInfo(name="team", type=ColumnType.STRING, sample=[]),
            ColumnInfo(name="points", type=ColumnType.FLOAT, sample=[])]
    return Schema(columns=cols, row_count=10)


def _decompose(response: str):
    return Decomposer(StubProvider(response)).decompose("prompt", _schema())


class TestDecomposerValidation:
    def test_accepts_object_form(self):
        subs = _decompose('{"ok": true, "charts": [{"sub_prompt": "points by team"}]}')
        assert subs == ["points by team"]

    def test_accepts_multiple_charts(self):
        subs = _decompose('{"ok": true, "charts": ['
                          '{"sub_prompt": "a"}, {"sub_prompt": "b"}]}')
        assert subs == ["a", "b"]

    def test_rejects_off_topic_prompt_with_reason(self):
        with pytest.raises(PromptRejected) as exc:
            _decompose('{"ok": false, "reason": "That is a math question, not a chart."}')
        assert "math question" in exc.value.reason

    def test_rejection_has_default_reason_when_missing(self):
        with pytest.raises(PromptRejected) as exc:
            _decompose('{"ok": false}')
        assert exc.value.reason                      # non-empty fallback

    def test_still_parses_bare_array_form(self):
        # Backward-compatible: a plain array is treated as an accepted plan.
        subs = _decompose('[{"sub_prompt": "points by team"}]')
        assert subs == ["points by team"]

    def test_tolerates_code_fences(self):
        subs = _decompose('```json\n{"ok": true, "charts": [{"sub_prompt": "x"}]}\n```')
        assert subs == ["x"]

    def test_raises_on_no_json(self):
        with pytest.raises(ValueError):
            _decompose("I cannot help with that.")
