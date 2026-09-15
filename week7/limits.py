"""Circuit breakers and telemetry accounting for both architectures."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from week7.schemas import BenchmarkLimits, ToolEvent


def estimate_tokens(value: Any) -> int:
    """Conservative offline token estimate used when no provider is called."""

    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return max(1, (len(value) + 3) // 4)


class CircuitBreakerTriggered(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class CircuitBreaker:
    limits: BenchmarkLimits
    started_ns: int = 0
    iterations: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    abort_reason: str | None = None

    # These are intentionally transparent defaults. The offline benchmark has
    # no provider charge, while the projected estimate shows how caps would
    # behave when a priced model is plugged in.
    input_price_per_million: float = 0.15
    output_price_per_million: float = 0.60

    def start(self) -> None:
        self.started_ns = time.perf_counter_ns()

    @property
    def elapsed_seconds(self) -> float:
        if not self.started_ns:
            return 0.0
        return (time.perf_counter_ns() - self.started_ns) / 1_000_000_000

    def _abort(self, reason: str) -> None:
        self.abort_reason = reason
        raise CircuitBreakerTriggered(reason)

    def check_time(self) -> None:
        if self.elapsed_seconds > self.limits.max_latency_seconds:
            self._abort(f"latency cap exceeded: {self.limits.max_latency_seconds:.3f}s")

    def begin_iteration(self) -> None:
        self.check_time()
        if self.iterations >= self.limits.max_iterations:
            self._abort(f"max iterations exceeded: {self.limits.max_iterations}")
        self.iterations += 1

    def before_tool_call(self) -> None:
        self.check_time()
        if self.tool_calls >= self.limits.max_tool_calls:
            self._abort(f"max tool calls exceeded: {self.limits.max_tool_calls}")

    def record_tool_call(self, input_value: Any, output_value: Any, tool_name: str) -> ToolEvent:
        self.before_tool_call()
        input_tokens = estimate_tokens(input_value)
        output_tokens = estimate_tokens(output_value)
        projected_input = self.input_tokens + input_tokens
        projected_output = self.output_tokens + output_tokens
        projected_cost = (
            projected_input * self.input_price_per_million / 1_000_000
            + projected_output * self.output_price_per_million / 1_000_000
        )
        if projected_input > self.limits.max_input_tokens:
            self._abort(f"input token cap exceeded: {self.limits.max_input_tokens}")
        if projected_output > self.limits.max_output_tokens:
            self._abort(f"output token cap exceeded: {self.limits.max_output_tokens}")
        if projected_cost > self.limits.max_cost_usd:
            self._abort(f"projected cost cap exceeded: ${self.limits.max_cost_usd:.4f}")

        self.tool_calls += 1
        self.input_tokens = projected_input
        self.output_tokens = projected_output
        self.estimated_cost_usd = projected_cost
        return ToolEvent(
            event_type="tool_call",
            name=tool_name,
            timestamp_ms=self.elapsed_seconds * 1000,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def record_reasoning(self, text: str) -> ToolEvent:
        output_tokens = estimate_tokens(text)
        projected_output = self.output_tokens + output_tokens
        if projected_output > self.limits.max_output_tokens:
            self._abort(f"reasoning token cap exceeded: {self.limits.max_output_tokens}")
        projected_cost = (
            self.input_tokens * self.input_price_per_million / 1_000_000
            + projected_output * self.output_price_per_million / 1_000_000
        )
        if projected_cost > self.limits.max_cost_usd:
            self._abort(f"projected cost cap exceeded: ${self.limits.max_cost_usd:.4f}")
        self.output_tokens = projected_output
        self.estimated_cost_usd = projected_cost
        return ToolEvent(
            event_type="reasoning",
            name="agent_reasoning",
            timestamp_ms=self.elapsed_seconds * 1000,
            output_tokens=output_tokens,
            detail=text,
        )
