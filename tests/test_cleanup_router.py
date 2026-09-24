import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import pytest

from local_text.cleanup import (
    QUOTA_BREAKER_MAX_SECONDS,
    ROUTE_BREAKER_MAX_SECONDS,
    ROUTE_FAILURE_ACTIONS,
    CleanupPartitionSchedule,
    CleanupRequest,
    CleanupRoute,
    CleanupService,
    CleanupStatus,
    CorrectionMode,
    ProviderBusyError,
    ProviderCoolingDownError,
    ProviderError,
    ProviderFailure,
    ProviderFailureClass,
    ProviderHTTPError,
    ProviderOutput,
    ProviderRejectedOutputError,
    ProviderTimeoutError,
    ProviderTransportError,
    RouteFailureAction,
    SequentialCleanupProvider,
)


@dataclass
class FakeClock:
    value: float = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def source_preserving_cleanup(raw_text: str) -> str:
    return f"{raw_text[:1].upper()}{raw_text[1:]}."


class FakeAdapter:
    def __init__(
        self,
        model: str,
        *outcomes: Any,
        provider_id: str = "provider-a",
        quota_group_id: str = "quota-a",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.model = model
        self.quota_group_id = quota_group_id
        self.outcomes = list(outcomes)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls = 0

    async def clean(
        self,
        raw_text: str,
        system_prompt: str,
        *,
        task_context: str | None = None,
        relevant_curated_knowledge: tuple[str, ...] = (),
    ) -> ProviderOutput:
        self.calls += 1
        outcome = (
            self.outcomes.pop(0)
            if len(self.outcomes) > 1
            else self.outcomes[0]
            if self.outcomes
            else source_preserving_cleanup(raw_text)
        )
        if callable(outcome):
            outcome = outcome()
        if isinstance(outcome, BaseException):
            raise outcome
        return ProviderOutput(
            text=outcome,
            provider_id=self.provider_id,
            model_id=self.model,
            elapsed_ms=999,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


class FakeTimeoutRunner:
    def __init__(self, clock: FakeClock, *modes: str) -> None:
        self.clock = clock
        self.modes = list(modes)
        self.budgets: list[float] = []

    async def __call__(self, awaitable, budget: float) -> ProviderOutput:
        self.budgets.append(budget)
        mode = self.modes.pop(0) if self.modes else "run"
        if mode == "timeout":
            task = asyncio.create_task(awaitable)
            await asyncio.sleep(0)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            self.clock.advance(budget)
            raise TimeoutError
        return await awaitable


def route(adapter: FakeAdapter) -> CleanupRoute:
    return CleanupRoute(
        adapter=adapter,
        quota_group_id=adapter.quota_group_id,
    )


def router(
    *adapters: FakeAdapter,
    clock: FakeClock | None = None,
    budgets: tuple[float, ...] | None = None,
    total: float = 20.0,
    timeout_runner=None,
) -> SequentialCleanupProvider:
    selected_clock = clock or FakeClock()
    selected_budgets = budgets or tuple(total / len(adapters) for _adapter in adapters)
    kwargs = {}
    if timeout_runner is not None:
        kwargs["timeout_runner"] = timeout_runner
    return SequentialCleanupProvider(
        tuple(route(adapter) for adapter in adapters),
        partition_schedule=CleanupPartitionSchedule(total, selected_budgets),
        clock=selected_clock,
        jitter=lambda delay: delay,
        **kwargs,
    )


def run_provider(provider: SequentialCleanupProvider) -> ProviderOutput:
    return asyncio.run(provider.clean("synthetic source", "Synthetic instruction"))


def run_service(provider: SequentialCleanupProvider):
    service = CleanupService(
        provider=provider,
        model=provider.model,
        timeout_seconds=provider.total_budget_seconds,
    )
    return asyncio.run(
        service.clean(CleanupRequest(original_text="synthetic source"), "Synthetic instruction")
    )


def transient_http(status: int = 503, *, retry_after: int | None = None) -> ProviderHTTPError:
    return ProviderHTTPError(status, retry_after_seconds=retry_after)


def permanent_quota() -> ProviderHTTPError:
    error = ProviderHTTPError(429, provider_code="project_spend_limit_exceeded")
    error.failure_class = ProviderFailureClass.PERMANENT_QUOTA
    return error


def test_primary_success_uses_one_route_and_preserves_usage() -> None:
    primary = FakeAdapter("primary", input_tokens=11, output_tokens=7)
    fallback = FakeAdapter("fallback")

    result = run_service(router(primary, fallback))

    assert result.status is CleanupStatus.PREPARED
    assert result.provider == "provider-a"
    assert result.model == "primary"
    assert primary.calls == 1
    assert fallback.calls == 0
    assert [(attempt.route_index, attempt.outcome) for attempt in result.attempts] == [
        (0, "success")
    ]
    assert (result.attempts[0].input_tokens, result.attempts[0].output_tokens) == (11, 7)


def test_selected_correction_mode_reaches_route_output_validation() -> None:
    observed: list[CorrectionMode] = []

    def validate(
        original_text: str,
        prepared_text: str,
        correction_mode: CorrectionMode,
    ) -> str:
        assert original_text == "synthetic source"
        observed.append(correction_mode)
        return prepared_text

    adapter = FakeAdapter("primary")
    provider = SequentialCleanupProvider(
        (route(adapter),),
        partition_schedule=CleanupPartitionSchedule(20, (12,)),
        clock=FakeClock(),
        jitter=lambda delay: delay,
        output_validator=validate,
    )
    service = CleanupService(provider, provider.model, provider.total_budget_seconds)

    result = asyncio.run(
        service.clean(
            CleanupRequest(original_text="synthetic source", correction_mode="smart"),
            "Synthetic instruction",
        )
    )

    assert observed == [CorrectionMode.SMART]
    assert result.correction_mode is CorrectionMode.SMART


def test_eligible_failure_advances_once_with_ordered_safe_attribution() -> None:
    clock = FakeClock()

    def fail_primary():
        clock.advance(1.25)
        raise transient_http(503)

    def win_fallback():
        clock.advance(0.25)
        return source_preserving_cleanup("synthetic source")

    primary = FakeAdapter("primary", fail_primary, quota_group_id="quota-a")
    fallback = FakeAdapter(
        "fallback",
        win_fallback,
        provider_id="provider-b",
        quota_group_id="quota-b",
        input_tokens=13,
        output_tokens=5,
    )

    result = run_service(router(primary, fallback, clock=clock))

    assert result.model == "fallback"
    assert result.provider == "provider-b"
    assert [attempt.model_dump(mode="json") for attempt in result.attempts] == [
        {
            "provider": "provider-a",
            "model": "primary",
            "outcome": "failure",
            "elapsed_ms": 1250,
            "route_index": 0,
            "input_tokens": None,
            "output_tokens": None,
            "failure_class": "transient_route",
            "provider_code": "http_503",
            "http_status": 503,
            "retry_after_seconds": None,
        },
        {
            "provider": "provider-b",
            "model": "fallback",
            "outcome": "success",
            "elapsed_ms": 250,
            "route_index": 1,
            "input_tokens": 13,
            "output_tokens": 5,
            "failure_class": None,
            "provider_code": None,
            "http_status": None,
            "retry_after_seconds": None,
        },
    ]
    serialized = result.model_dump_json()
    assert "synthetic source" not in serialized
    assert "Synthetic instruction" not in serialized
    assert "quota-a" not in serialized
    assert "quota-b" not in serialized


@pytest.mark.parametrize("mode", [CorrectionMode.CONSERVATIVE, CorrectionMode.SMART])
def test_both_modes_receive_the_same_ordered_eligible_routes(mode: CorrectionMode) -> None:
    primary = FakeAdapter("primary", transient_http(503), quota_group_id="quota-a")
    fallback = FakeAdapter(
        "fallback",
        provider_id="provider-b",
        quota_group_id="quota-b",
    )
    provider = router(primary, fallback)
    service = CleanupService(provider, provider.model, provider.total_budget_seconds)

    result = asyncio.run(
        service.clean(
            CleanupRequest(original_text="synthetic source", correction_mode=mode),
            "Synthetic instruction",
        )
    )

    assert result.status is CleanupStatus.PREPARED
    assert result.model == "fallback"
    assert primary.calls == 1
    assert fallback.calls == 1
    assert [(attempt.route_index, attempt.outcome) for attempt in result.attempts] == [
        (0, "failure"),
        (1, "success"),
    ]


def test_smart_skips_a_cooling_primary_and_uses_the_next_eligible_route() -> None:
    primary = FakeAdapter("primary", transient_http(503), quota_group_id="quota-a")
    fallback = FakeAdapter("fallback", provider_id="provider-b", quota_group_id="quota-b")
    provider = router(primary, fallback)
    assert run_service(provider).model == "fallback"

    output = asyncio.run(
        provider.clean(
            "synthetic source",
            "Synthetic instruction",
            CorrectionMode.SMART,
        )
    )

    assert output.model_id == "fallback"
    assert output.route_index == 1
    assert primary.calls == 1
    assert fallback.calls == 2


@pytest.mark.parametrize(
    "error",
    [
        ProviderRejectedOutputError("private refusal", safety_policy=True),
        ProviderError(
            "private local validation detail",
            failure_class=ProviderFailureClass.INVALID_LOCAL_REQUEST,
        ),
    ],
)
def test_terminal_normalized_failures_never_advance(error: ProviderFailure) -> None:
    primary = FakeAdapter("primary", error)
    fallback = FakeAdapter("fallback", provider_id="provider-b", quota_group_id="quota-b")

    result = run_service(router(primary, fallback))

    assert result.status is CleanupStatus.PROVIDER_ERROR
    assert result.prepared_text == "synthetic source"
    assert primary.calls == 1
    assert fallback.calls == 0
    assert len(result.attempts) == 1


def test_safety_refusal_is_terminal_and_does_not_open_a_breaker() -> None:
    primary = FakeAdapter(
        "primary",
        ProviderRejectedOutputError("private refusal", safety_policy=True),
        source_preserving_cleanup("synthetic source"),
    )
    fallback = FakeAdapter("fallback", provider_id="provider-b", quota_group_id="quota-b")
    provider = router(primary, fallback)

    refused = run_service(provider)
    recovered = run_service(provider)

    assert refused.error is not None and refused.error.code == "cleanup_output_rejected"
    assert recovered.status is CleanupStatus.PREPARED
    assert primary.calls == 2
    assert fallback.calls == 0


def test_programming_exception_is_terminal_and_does_not_mutate_breakers() -> None:
    primary = FakeAdapter(
        "primary",
        ValueError("private bug detail"),
        source_preserving_cleanup("synthetic source"),
    )
    fallback = FakeAdapter("fallback", provider_id="provider-b", quota_group_id="quota-b")
    provider = router(primary, fallback)

    failed = run_service(provider)
    recovered = run_service(provider)

    assert failed.error is not None and failed.error.code == "cleanup_provider_error"
    assert failed.attempts[0].failure_class is ProviderFailureClass.UNKNOWN
    assert "private bug detail" not in failed.model_dump_json()
    assert recovered.status is CleanupStatus.PREPARED
    assert primary.calls == 2
    assert fallback.calls == 0


def test_shared_semantic_validation_advances_and_preserves_failed_attempt_usage() -> None:
    primary = FakeAdapter(
        "primary",
        "x" * 2_000,
        input_tokens=17,
        output_tokens=19,
    )
    fallback = FakeAdapter("fallback", provider_id="provider-b", quota_group_id="quota-b")

    result = run_service(router(primary, fallback))

    assert result.status is CleanupStatus.PREPARED
    assert result.model == "fallback"
    assert result.attempts[0].failure_class is ProviderFailureClass.INVALID_OUTPUT
    assert (result.attempts[0].input_tokens, result.attempts[0].output_tokens) == (17, 19)
    assert result.attempts[1].outcome == "success"


def test_asymmetric_partition_reserves_the_supplied_backup_opportunity() -> None:
    clock = FakeClock()
    timeout_runner = FakeTimeoutRunner(clock, "timeout", "run")
    primary = FakeAdapter("primary")
    fallback = FakeAdapter("fallback", provider_id="provider-b", quota_group_id="quota-b")
    provider = router(
        primary,
        fallback,
        clock=clock,
        budgets=(12.0, 8.0),
        total=20.0,
        timeout_runner=timeout_runner,
    )

    output = run_provider(provider)

    assert output.model_id == "fallback"
    assert timeout_runner.budgets == [12.0, 8.0]
    assert primary.calls == 1
    assert fallback.calls == 1


def test_adding_a_route_does_not_extend_the_supplied_total_deadline() -> None:
    elapsed: list[float] = []
    observed_budgets: list[list[float]] = []

    for budgets in ((6.0, 4.0), (6.0, 3.0, 1.0)):
        clock = FakeClock()
        timeout_runner = FakeTimeoutRunner(clock, *("timeout" for _ in budgets))
        adapters = tuple(
            FakeAdapter(
                f"route-{index}",
                provider_id=f"provider-{index}",
                quota_group_id=f"quota-{index}",
            )
            for index in range(len(budgets))
        )

        result = run_service(
            router(
                *adapters,
                clock=clock,
                budgets=budgets,
                total=10.0,
                timeout_runner=timeout_runner,
            )
        )

        assert result.status is CleanupStatus.TIMEOUT
        elapsed.append(clock.value - 100.0)
        observed_budgets.append(timeout_runner.budgets)

    assert elapsed == [10.0, 10.0]
    assert observed_budgets == [[6.0, 4.0], [6.0, 3.0, 1.0]]


def test_total_deadline_exhaustion_does_not_start_a_short_fallback() -> None:
    clock = FakeClock()
    timeout_runner = FakeTimeoutRunner(clock, "timeout")
    primary = FakeAdapter("primary")
    fallback = FakeAdapter("fallback", provider_id="provider-b", quota_group_id="quota-b")
    provider = router(
        primary,
        fallback,
        clock=clock,
        budgets=(12.0, 0.4),
        total=12.4,
        timeout_runner=timeout_runner,
    )

    result = run_service(provider)

    assert result.status is CleanupStatus.TIMEOUT
    assert result.error is not None and result.error.code == "cleanup_timeout"
    assert primary.calls == 1
    assert fallback.calls == 0
    assert len(result.attempts) == 1
    assert result.attempts[0].provider_code == "timeout"


@pytest.mark.parametrize(
    ("total", "attempt_budget"),
    [(0.499, 0.499), (20.0, 0.499)],
)
def test_attempt_never_starts_with_less_than_500ms(total: float, attempt_budget: float) -> None:
    adapter = FakeAdapter("primary")
    provider = router(adapter, budgets=(attempt_budget,), total=total)

    result = run_service(provider)

    assert result.status is CleanupStatus.TIMEOUT
    assert result.attempts == []
    assert adapter.calls == 0


def test_route_breaker_opens_skips_half_opens_and_resets_on_success() -> None:
    clock = FakeClock()
    primary = FakeAdapter(
        "primary", transient_http(), source_preserving_cleanup("synthetic source")
    )
    fallback = FakeAdapter("fallback", provider_id="provider-b", quota_group_id="quota-b")
    provider = router(primary, fallback, clock=clock)

    first = run_provider(provider)
    skipped = run_provider(provider)
    clock.advance(15)
    probe = run_provider(provider)
    assert provider._route_breakers[0].failure_count == 0
    closed = run_provider(provider)

    assert [result.model_id for result in (first, skipped, probe, closed)] == [
        "fallback",
        "fallback",
        "primary",
        "primary",
    ]
    assert primary.calls == 3
    assert fallback.calls == 2


def test_route_breaker_half_open_failures_back_off_exponentially_to_cap() -> None:
    clock = FakeClock()
    adapter = FakeAdapter("primary", *[transient_http() for _index in range(7)])
    provider = router(adapter, clock=clock)
    expected_delays = [15.0, 30.0, 60.0, 120.0, 240.0, 300.0, 300.0]

    for expected_delay in expected_delays:
        with pytest.raises(ProviderHTTPError):
            run_provider(provider)
        state = provider._route_breakers[0]
        assert state.open_until - clock() == expected_delay
        with pytest.raises(ProviderCoolingDownError):
            run_provider(provider)
        clock.advance(expected_delay)

    assert provider._route_breakers[0].open_until - (clock() - expected_delays[-1]) <= (
        ROUTE_BREAKER_MAX_SECONDS
    )
    assert adapter.calls == len(expected_delays)


def test_route_backoff_cap_does_not_compute_an_unbounded_exponent() -> None:
    clock = FakeClock()
    provider = router(FakeAdapter("primary"), clock=clock)
    state = provider._route_breakers[0]
    state.failure_count = 1_000_000
    state.base_delay_seconds = 15

    provider._open_breaker(
        state,
        clock(),
        base_seconds=15,
        max_seconds=ROUTE_BREAKER_MAX_SECONDS,
        half_open_failure=True,
    )

    assert state.open_until - clock() == ROUTE_BREAKER_MAX_SECONDS


def test_stale_concurrent_success_does_not_close_new_route_breaker() -> None:
    async def exercise() -> None:
        clock = FakeClock()
        first_started = asyncio.Event()
        second_started = asyncio.Event()
        release_success = asyncio.Event()

        class InterleavedAdapter(FakeAdapter):
            async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
                self.calls += 1
                if self.calls == 1:
                    first_started.set()
                    await second_started.wait()
                    raise transient_http(503)
                second_started.set()
                await release_success.wait()
                return ProviderOutput(
                    source_preserving_cleanup(raw_text), self.provider_id, self.model, 0
                )

        adapter = InterleavedAdapter("primary")
        provider = router(adapter, clock=clock)
        failing = asyncio.create_task(provider.clean("first", "instruction"))
        await first_started.wait()
        stale_success = asyncio.create_task(provider.clean("second", "instruction"))
        await second_started.wait()

        with pytest.raises(ProviderHTTPError):
            await failing
        release_success.set()
        assert (await stale_success).model_id == "primary"
        assert provider._route_breakers[0].failure_count == 1
        assert provider._route_breakers[0].open_until == clock() + 15
        with pytest.raises(ProviderCoolingDownError):
            await provider.clean("third", "instruction")
        assert adapter.calls == 2

    asyncio.run(exercise())


def test_only_one_route_half_open_probe_runs_concurrently() -> None:
    async def exercise() -> None:
        clock = FakeClock()
        probe_started = asyncio.Event()
        release_probe = asyncio.Event()

        class ProbeAdapter(FakeAdapter):
            async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
                self.calls += 1
                if self.calls == 1:
                    raise transient_http()
                probe_started.set()
                await release_probe.wait()
                return ProviderOutput(
                    source_preserving_cleanup(raw_text), self.provider_id, self.model, 0
                )

        primary = ProbeAdapter("primary")
        fallback = FakeAdapter("fallback", provider_id="provider-b", quota_group_id="quota-b")
        provider = router(primary, fallback, clock=clock)
        await provider.clean("source", "instruction")
        clock.advance(15)

        probe = asyncio.create_task(provider.clean("source", "instruction"))
        await probe_started.wait()
        concurrent = await provider.clean("source", "instruction")
        release_probe.set()
        probed = await probe

        assert concurrent.model_id == "fallback"
        assert probed.model_id == "primary"
        assert primary.calls == 2

    asyncio.run(exercise())


def test_429_opens_every_route_in_the_shared_quota_group() -> None:
    clock = FakeClock()
    primary = FakeAdapter("primary", transient_http(429), quota_group_id="shared")
    same_group = FakeAdapter("same-group", quota_group_id="shared")
    independent = FakeAdapter("independent", provider_id="provider-b", quota_group_id="independent")
    provider = router(primary, same_group, independent, clock=clock)

    first = run_provider(provider)
    second = run_provider(provider)

    assert first.model_id == "independent"
    assert second.model_id == "independent"
    assert primary.calls == 1
    assert same_group.calls == 0
    assert independent.calls == 2
    assert [failure.model for failure in first.prior_failures] == ["primary"]


def test_quota_breaker_honors_retry_after_then_resets_on_probe_success() -> None:
    clock = FakeClock()
    adapter = FakeAdapter(
        "primary",
        transient_http(429, retry_after=17),
        source_preserving_cleanup("synthetic source"),
    )
    provider = router(adapter, clock=clock)

    with pytest.raises(ProviderHTTPError):
        run_provider(provider)
    clock.advance(16.999)
    with pytest.raises(ProviderCoolingDownError):
        run_provider(provider)
    clock.advance(0.001)
    assert run_provider(provider).model_id == "primary"
    assert provider._quota_breakers["quota-a"].failure_count == 0
    assert run_provider(provider).model_id == "primary"
    assert adapter.calls == 3


def test_quota_breaker_does_not_probe_before_retry_after_beyond_backoff_cap() -> None:
    clock = FakeClock()
    adapter = FakeAdapter(
        "primary",
        transient_http(429, retry_after=1_200),
        source_preserving_cleanup("synthetic source"),
    )
    provider = router(adapter, clock=clock)

    with pytest.raises(ProviderHTTPError) as caught:
        run_provider(provider)
    assert caught.value.retry_after_seconds == 1_200
    assert provider._quota_breakers["quota-a"].open_until == clock() + 1_200

    clock.advance(900)
    with pytest.raises(ProviderCoolingDownError):
        run_provider(provider)
    clock.advance(299.999)
    with pytest.raises(ProviderCoolingDownError):
        run_provider(provider)
    assert adapter.calls == 1

    clock.advance(0.001)
    assert run_provider(provider).model_id == "primary"
    assert adapter.calls == 2


def test_quota_half_open_failures_back_off_to_15_minute_cap() -> None:
    clock = FakeClock()
    adapter = FakeAdapter("primary", *[transient_http(429) for _index in range(6)])
    provider = router(adapter, clock=clock)
    expected_delays = [60.0, 120.0, 240.0, 480.0, 900.0, 900.0]

    for expected_delay in expected_delays:
        with pytest.raises(ProviderHTTPError):
            run_provider(provider)
        state = provider._quota_breakers["quota-a"]
        assert state.open_until - clock() == expected_delay
        assert expected_delay <= QUOTA_BREAKER_MAX_SECONDS
        clock.advance(expected_delay)

    assert adapter.calls == len(expected_delays)


def test_stale_concurrent_success_does_not_close_new_shared_quota_breaker() -> None:
    async def exercise() -> None:
        clock = FakeClock()
        first_started = asyncio.Event()
        second_started = asyncio.Event()
        release_success = asyncio.Event()

        class InterleavedAdapter(FakeAdapter):
            async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
                self.calls += 1
                if self.calls == 1:
                    first_started.set()
                    await second_started.wait()
                    raise transient_http(429)
                second_started.set()
                await release_success.wait()
                return ProviderOutput(
                    source_preserving_cleanup(raw_text), self.provider_id, self.model, 0
                )

        adapter = InterleavedAdapter("primary", quota_group_id="shared")
        provider = router(adapter, clock=clock)
        failing = asyncio.create_task(provider.clean("first", "instruction"))
        await first_started.wait()
        stale_success = asyncio.create_task(provider.clean("second", "instruction"))
        await second_started.wait()

        with pytest.raises(ProviderHTTPError):
            await failing
        release_success.set()
        assert (await stale_success).model_id == "primary"
        assert provider._quota_breakers["shared"].failure_count == 1
        assert provider._quota_breakers["shared"].open_until == clock() + 60
        with pytest.raises(ProviderCoolingDownError):
            await provider.clean("third", "instruction")
        assert adapter.calls == 2

    asyncio.run(exercise())


def test_half_open_success_does_not_clear_concurrent_permanent_quota_disable() -> None:
    async def exercise() -> None:
        clock = FakeClock()
        old_started = asyncio.Event()
        release_old = asyncio.Event()
        probe_started = asyncio.Event()
        release_probe = asyncio.Event()

        class InterleavedAdapter(FakeAdapter):
            async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
                self.calls += 1
                if raw_text == "old":
                    old_started.set()
                    await release_old.wait()
                    raise permanent_quota()
                if raw_text == "opener":
                    raise transient_http(429)
                probe_started.set()
                await release_probe.wait()
                return ProviderOutput(
                    source_preserving_cleanup(raw_text), self.provider_id, self.model, 0
                )

        adapter = InterleavedAdapter("primary", quota_group_id="shared")
        provider = router(adapter, clock=clock, budgets=(120,), total=120)
        old = asyncio.create_task(provider.clean("old", "instruction"))
        await old_started.wait()
        with pytest.raises(ProviderHTTPError):
            await provider.clean("opener", "instruction")
        clock.advance(60)

        probe = asyncio.create_task(provider.clean("probe", "instruction"))
        await probe_started.wait()
        release_old.set()
        with pytest.raises(ProviderHTTPError):
            await old
        state = provider._quota_breakers["shared"]
        assert state.permanently_disabled is True
        assert state.probe_in_flight is True
        breaker_snapshot = (state.open_until, state.failure_count, state.base_delay_seconds)

        release_probe.set()
        assert (await probe).model_id == "primary"
        assert state.permanently_disabled is True
        assert state.probe_in_flight is False
        assert (state.open_until, state.failure_count, state.base_delay_seconds) == breaker_snapshot
        with pytest.raises(ProviderCoolingDownError):
            await provider.clean("later", "instruction")
        assert adapter.calls == 3

    asyncio.run(exercise())


def test_only_one_shared_quota_half_open_probe_runs_concurrently() -> None:
    async def exercise() -> None:
        clock = FakeClock()
        probe_started = asyncio.Event()
        release_probe = asyncio.Event()

        class ProbeAdapter(FakeAdapter):
            async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
                self.calls += 1
                if self.calls == 1:
                    raise transient_http(429)
                probe_started.set()
                await release_probe.wait()
                return ProviderOutput(
                    source_preserving_cleanup(raw_text), self.provider_id, self.model, 0
                )

        primary = ProbeAdapter("primary", quota_group_id="shared")
        same_group = FakeAdapter("same-group", quota_group_id="shared")
        independent = FakeAdapter(
            "independent", provider_id="provider-b", quota_group_id="independent"
        )
        provider = router(primary, same_group, independent, clock=clock)
        await provider.clean("source", "instruction")
        clock.advance(60)

        probe = asyncio.create_task(provider.clean("source", "instruction"))
        await probe_started.wait()
        concurrent = await provider.clean("source", "instruction")
        release_probe.set()
        probed = await probe

        assert concurrent.model_id == "independent"
        assert probed.model_id == "primary"
        assert primary.calls == 2
        assert same_group.calls == 0

    asyncio.run(exercise())


def test_permanent_route_and_quota_failures_disable_only_their_configured_scope() -> None:
    route_disabled = FakeAdapter("route-disabled", ProviderHTTPError(401), quota_group_id="shared")
    same_credential = FakeAdapter("same-credential", quota_group_id="shared")
    route_fallback = FakeAdapter(
        "route-fallback", provider_id="provider-b", quota_group_id="quota-b"
    )
    route_provider = router(route_disabled, same_credential, route_fallback)

    assert run_provider(route_provider).model_id == "route-fallback"
    assert run_provider(route_provider).model_id == "route-fallback"
    assert route_disabled.calls == 1
    assert same_credential.calls == 0

    quota_disabled = FakeAdapter("quota-disabled", permanent_quota(), quota_group_id="shared")
    same_group = FakeAdapter("same-group", quota_group_id="shared")
    independent = FakeAdapter("independent", provider_id="provider-b", quota_group_id="independent")
    quota_provider = router(quota_disabled, same_group, independent)

    assert run_provider(quota_provider).model_id == "independent"
    assert run_provider(quota_provider).model_id == "independent"
    assert quota_disabled.calls == 1
    assert same_group.calls == 0


def test_cancellation_is_terminal_and_releases_capacity_without_fallback() -> None:
    async def exercise() -> None:
        started = asyncio.Event()

        class CancelAdapter(FakeAdapter):
            async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
                self.calls += 1
                if self.calls == 1:
                    started.set()
                    await asyncio.Event().wait()
                return ProviderOutput(
                    source_preserving_cleanup(raw_text), self.provider_id, self.model, 0
                )

        primary = CancelAdapter("primary")
        fallback = FakeAdapter("fallback", provider_id="provider-b", quota_group_id="quota-b")
        provider = router(primary, fallback)
        task = asyncio.create_task(provider.clean("source", "instruction"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        recovered = await provider.clean("source", "instruction")
        assert recovered.model_id == "primary"
        assert primary.calls == 2
        assert fallback.calls == 0
        assert provider._active_cleanups == 0

    asyncio.run(exercise())


def test_bulkhead_allows_two_active_calls_and_rejects_a_third_without_queue_or_call() -> None:
    async def exercise() -> None:
        release = asyncio.Event()
        two_started = asyncio.Event()

        class BlockingAdapter(FakeAdapter):
            async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
                self.calls += 1
                if self.calls == 2:
                    two_started.set()
                await release.wait()
                return ProviderOutput(
                    source_preserving_cleanup(raw_text), self.provider_id, self.model, 0
                )

        adapter = BlockingAdapter("primary")
        provider = router(adapter)
        service = CleanupService(provider, provider.model, provider.total_budget_seconds)
        first = asyncio.create_task(provider.clean("source one", "instruction"))
        second = asyncio.create_task(provider.clean("source two", "instruction"))
        await two_started.wait()

        rejected = await service.clean(CleanupRequest(original_text="source three"), "instruction")
        assert rejected.prepared_text == "source three"
        assert rejected.error is not None
        assert rejected.error.code == "cleanup_provider_temporarily_unavailable"
        assert rejected.attempts == []
        assert adapter.calls == 2

        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        replacement = asyncio.create_task(provider.clean("source four", "instruction"))
        while adapter.calls < 3:
            await asyncio.sleep(0)
        assert adapter.calls == 3
        release.set()
        await second
        await replacement
        assert provider._active_cleanups == 0

    asyncio.run(exercise())


def test_route_failure_policy_is_typed_and_exhaustive() -> None:
    assert set(ROUTE_FAILURE_ACTIONS) == set(ProviderFailureClass)
    assert ROUTE_FAILURE_ACTIONS[ProviderFailureClass.TRANSIENT_ROUTE] is RouteFailureAction.ADVANCE
    assert ROUTE_FAILURE_ACTIONS[ProviderFailureClass.INVALID_OUTPUT] is RouteFailureAction.ADVANCE
    assert ROUTE_FAILURE_ACTIONS[ProviderFailureClass.SAFETY_POLICY] is RouteFailureAction.TERMINAL
    assert ROUTE_FAILURE_ACTIONS[ProviderFailureClass.UNKNOWN] is RouteFailureAction.TERMINAL


def test_transport_timeout_and_eligible_http_failures_make_at_most_one_call_per_route() -> None:
    eligible = (
        ProviderTransportError("private transport"),
        ProviderTimeoutError("private timeout"),
        transient_http(408),
        transient_http(500),
        transient_http(502),
        transient_http(503),
        transient_http(504),
    )
    for error in eligible:
        primary = FakeAdapter("primary", error)
        fallback = FakeAdapter("fallback", provider_id="provider-b", quota_group_id="quota-b")

        assert run_provider(router(primary, fallback)).model_id == "fallback"
        assert primary.calls == 1
        assert fallback.calls == 1


def test_route_rejects_mismatched_explicit_quota_identity() -> None:
    adapter = FakeAdapter("primary", quota_group_id="adapter-group")

    with pytest.raises(ValueError, match="quota groups must match"):
        CleanupRoute(adapter, "different-group")


def test_bulkhead_failure_type_is_normalized_without_being_an_attempt() -> None:
    error = ProviderBusyError("private queue detail", model="primary")

    assert error.failure_class is ProviderFailureClass.TRANSIENT_ROUTE
    assert error.provider_code == "bulkhead_full"
    assert error.attempted is False
