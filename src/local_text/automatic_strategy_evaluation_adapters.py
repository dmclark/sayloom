"""Evaluation-only adapters for automatic correction strategy candidates."""

from types import MappingProxyType

from local_text.automatic_strategy_evaluation import AdapterRequest, ExecutionResult


def abstain(_request: AdapterRequest) -> ExecutionResult:
    """Deterministically preserve Original through the harness fail-open path."""

    return ExecutionResult(
        outcome="abstention",
        prepared_text=None,
        selected_method=None,
        repairs=[],
        internal_retries=0,
        latency_ms=0,
        provider_calls=0,
        input_tokens=0,
        output_tokens=0,
        cost_usd_micros=0,
    )


EVALUATION_ADAPTERS = MappingProxyType({"abstention-v1": abstain})
