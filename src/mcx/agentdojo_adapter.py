"""AgentDojo adapter for executable persistent-workflow replay.

AgentDojo remains an optional dependency. Imports are intentionally local so
the rest of the MCX package and test suite do not require it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence


VARIANTS = ("clean", "early_graft", "middle_graft", "late_graft")


@dataclass(frozen=True)
class AgentDojoReplay:
    suite: str
    user_task_id: str
    injection_task_id: str
    variant: str
    utility: bool
    attack_success: bool
    safe_success: bool
    error: str | None
    planned_call_count: int
    executed_call_count: int
    trace_digest: str
    environment_digest: str
    semantic_environment_digest: str
    trace_functions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["trace_functions"] = list(self.trace_functions)
        return result


def _canonical(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _canonical(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def stable_digest(value: Any) -> str:
    payload = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def without_volatile_timestamps(value: Any) -> Any:
    """Normalize AgentDojo wall-clock metadata for semantic state comparison.

    Email ``timestamp`` and cloud-drive ``last_modified`` values are generated
    from the current time. Their presence and all surrounding state are kept,
    but their exact values are replaced. The raw digest remains available.
    """
    value = _canonical(value)
    if isinstance(value, dict):
        return {
            key: (
                "<volatile-wall-clock>"
                if key in {"timestamp", "last_modified"}
                else without_volatile_timestamps(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [without_volatile_timestamps(item) for item in value]
    return value


def task_number(task_id: str) -> int:
    return int(task_id.rsplit("_", 1)[1])


def graft_calls(
    user_calls: Sequence[Any], injection_calls: Sequence[Any], variant: str,
) -> tuple[Any, ...]:
    user_calls = tuple(user_calls)
    injection_calls = tuple(injection_calls)
    if variant == "clean":
        return user_calls
    if variant == "early_graft":
        return injection_calls + user_calls
    if variant == "middle_graft":
        split = (len(user_calls) + 1) // 2
        return user_calls[:split] + injection_calls + user_calls[split:]
    if variant == "late_graft":
        return user_calls + injection_calls
    raise ValueError(f"unknown graft variant: {variant}")


def selection_score(
    salt: str, suite: str, user_task_id: str, injection_task_id: str,
) -> str:
    return hashlib.sha256(
        f"{salt}|{suite}|{user_task_id}|{injection_task_id}".encode("utf-8")
    ).hexdigest()


def select_qualifying_pairs(
    qualifying: Iterable[tuple[str, str]], *, suite: str, salt: str, count: int,
) -> tuple[tuple[str, str], ...]:
    ranked = sorted(
        set(qualifying),
        key=lambda pair: (selection_score(salt, suite, pair[0], pair[1]), pair),
    )
    selected: list[tuple[str, str]] = []
    used_users: set[str] = set()
    used_injections: set[str] = set()
    for pair in ranked:
        if pair[0] in used_users or pair[1] in used_injections:
            continue
        selected.append(pair)
        used_users.add(pair[0])
        used_injections.add(pair[1])
        if len(selected) == count:
            return tuple(selected)
    raise ValueError(
        f"suite {suite} has only {len(selected)} disjoint qualifying pairs; "
        f"need {count}"
    )


def load_official_suites(benchmark_version: str):
    from agentdojo.task_suite.load_suites import get_suites

    return get_suites(benchmark_version)


def _task_result(task: Any, output: str, pre: Any, post: Any, traces: Sequence[Any], kind: str) -> bool:
    if kind == "utility":
        result = task.utility_from_traces(output, pre, post, traces)
        return bool(task.utility(output, pre, post) if result is None else result)
    result = task.security_from_traces(output, pre, post, traces)
    return bool(task.security(output, pre, post) if result is None else result)


def replay_workflow(
    suite: Any, user_task_id: str, injection_task_id: str, variant: str,
    *, score_clean_against_injection: bool = False,
) -> AgentDojoReplay:
    from agentdojo.functions_runtime import FunctionsRuntime

    user_task = suite.user_tasks[user_task_id]
    injection_task = suite.injection_tasks[injection_task_id]
    environment = suite.load_and_inject_default_environment({})
    environment = user_task.init_environment(environment)
    pre_environment = environment.model_copy(deep=True)
    user_calls = tuple(user_task.ground_truth(environment))
    injection_calls = tuple(injection_task.ground_truth(environment))
    planned = graft_calls(user_calls, injection_calls, variant)
    runtime = FunctionsRuntime(suite.tools)
    traces: list[Any] = []
    error: str | None = None
    for call in planned:
        try:
            runtime.run_function(
                environment, call.function, call.args, raise_on_error=True,
            )
            traces.append(call)
        except Exception as exc:  # pragma: no cover - retained in report
            error = f"{type(exc).__name__}: {exc}"
            break

    output = user_task.GROUND_TRUTH_OUTPUT or ""
    if variant != "clean" and injection_task.GROUND_TRUTH_OUTPUT:
        output += "\n" + injection_task.GROUND_TRUTH_OUTPUT
    utility = _task_result(
        user_task, output, pre_environment, environment, traces, "utility",
    )
    attack_success = False
    if variant != "clean" or score_clean_against_injection:
        attack_success = _task_result(
            injection_task, output, pre_environment, environment, traces, "security",
        )
    trace_payload = [call.model_dump(mode="json") for call in traces]
    return AgentDojoReplay(
        suite=suite.name,
        user_task_id=user_task_id,
        injection_task_id=injection_task_id,
        variant=variant,
        utility=utility,
        attack_success=attack_success,
        safe_success=bool(utility and not attack_success and error is None),
        error=error,
        planned_call_count=len(planned),
        executed_call_count=len(traces),
        trace_digest=stable_digest(trace_payload),
        environment_digest=stable_digest(environment),
        semantic_environment_digest=stable_digest(
            without_volatile_timestamps(environment),
        ),
        trace_functions=tuple(call.function for call in traces),
    )


def screen_suite_pairs(
    suite: Any, *, minimum_clean_tool_calls: int,
    score_clean_against_injection: bool = False,
) -> tuple[tuple[tuple[str, str], ...], dict[str, int]]:
    qualifying: list[tuple[str, str]] = []
    counts = {
        "candidate_pairs": 0,
        "minimum_length_pairs": 0,
        "clean_valid_pairs": 0,
        "distinct_trace_pairs": 0,
        "all_grafts_harmful_pairs": 0,
        "qualifying_pairs": 0,
    }
    user_items = sorted(suite.user_tasks.items(), key=lambda item: task_number(item[0]))
    injection_items = sorted(
        suite.injection_tasks.items(), key=lambda item: task_number(item[0]),
    )
    for user_id, user_task in user_items:
        for injection_id, _ in injection_items:
            counts["candidate_pairs"] += 1
            environment = suite.load_and_inject_default_environment({})
            environment = user_task.init_environment(environment)
            if len(user_task.ground_truth(environment)) < minimum_clean_tool_calls:
                continue
            counts["minimum_length_pairs"] += 1
            outcomes = {
                variant: replay_workflow(
                    suite, user_id, injection_id, variant,
                    score_clean_against_injection=score_clean_against_injection,
                )
                for variant in VARIANTS
            }
            clean = outcomes["clean"]
            if clean.error is not None or not clean.safe_success:
                continue
            counts["clean_valid_pairs"] += 1
            if len({row.trace_digest for row in outcomes.values()}) != len(VARIANTS):
                continue
            counts["distinct_trace_pairs"] += 1
            grafts = [outcomes[variant] for variant in VARIANTS[1:]]
            if not all(row.error is None and row.attack_success for row in grafts):
                continue
            counts["all_grafts_harmful_pairs"] += 1
            qualifying.append((user_id, injection_id))
    counts["qualifying_pairs"] = len(qualifying)
    return tuple(qualifying), counts
