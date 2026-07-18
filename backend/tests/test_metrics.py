import pytest

from api.metrics import cost, _price, MODEL_PRICING
from pipeline.providers.metrics import MeteredProvider, drain, CallRecord, record
from pipeline.providers.base import LLMProvider


class _Fake(LLMProvider):
    """A stand-in provider: reports usage and can be told to fail."""
    model = "fake-model-1"

    def __init__(self, fail=False, usage=(10, 5)):
        self._fail = fail
        self._usage = usage

    def complete(self, system, user):
        if self._fail:
            raise RuntimeError("boom")
        self.last_usage = self._usage
        return "ok"


@pytest.fixture(autouse=True)
def _clear_buffer():
    drain()          # start each test with an empty buffer
    yield
    drain()


class TestCost:
    def test_known_model_prices_input_and_output(self):
        # claude-haiku-4: (0.80, 4.0) per 1M → 1M in + 1M out = 4.8
        assert cost("claude-haiku-4-5", 1_000_000, 1_000_000) == pytest.approx(4.8)

    def test_gemini(self):
        assert cost("gemini-2.0-flash", 1_000_000, 1_000_000) == pytest.approx(0.5)

    def test_unknown_model_is_unpriced(self):
        assert cost("mystery-9000", 100, 100) is None

    def test_none_tokens_treated_as_zero(self):
        assert cost("gemini-2.0-flash", None, None) == 0.0

    def test_longest_prefix_wins(self):
        # both "claude-haiku-4" and (hypothetically) shorter prefixes could match;
        # the most specific key should be selected
        assert _price("claude-haiku-4-5") == MODEL_PRICING["claude-haiku-4"]


class TestMeteredProvider:
    def test_records_latency_tokens_and_ok(self):
        mp = MeteredProvider(_Fake(usage=(12, 7)), "fakeprov")
        assert mp.complete("s", "u") == "ok"
        assert mp.model == "fake-model-1"
        recs = drain()
        assert len(recs) == 1
        r = recs[0]
        assert r.provider == "fakeprov" and r.model == "fake-model-1"
        assert r.ok is True and r.input_tokens == 12 and r.output_tokens == 7
        assert r.latency_ms >= 0

    def test_failure_marks_not_ok_and_reraises(self):
        mp = MeteredProvider(_Fake(fail=True), "fakeprov")
        with pytest.raises(RuntimeError):
            mp.complete("s", "u")
        recs = drain()
        assert len(recs) == 1 and recs[0].ok is False
        assert recs[0].input_tokens is None      # no usage on failure

    def test_batch_meters_each_call(self):
        mp = MeteredProvider(_Fake(), "fakeprov")
        out = mp.complete_batch([("s", "u"), ("s", "u"), ("s", "u")])
        assert out == ["ok", "ok", "ok"]
        assert len(drain()) == 3


class TestBuffer:
    def test_drain_empties(self):
        record(CallRecord("p", "m", 1, True, 1, 1))
        assert len(drain()) == 1
        assert drain() == []
