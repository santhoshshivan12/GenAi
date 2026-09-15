# Week 7 Architecture Verdict

Run timestamp (UTC): `2026-09-15T13:31:04.595669+00:00`  
Suite: `10` supplied migration questions  
Model contract: `offline-evidence-synthesizer-v1`  
Provider: `offline deterministic benchmark` (no paid API requests were made)

## Verdict: `deterministic_workflow`

The path varies for the deprecation-dependent migration class (medium-01, medium-04, medium-07): step three changes after the source page reveals a deprecated or version-sensitive parameter. This is the only class that forces agent-style branching; the other seven cases have a fixed documentation path. On this closed set, the deterministic workflow still handled the finite branch table and matched the agent at 100% pass rate, with lower p99 latency and fewer tokens. Use the workflow for these known branches; use an agent when the deprecation replacement or next source is unknown at design time.

## Required race table

| Metric | ReAct agent | Deterministic workflow |
|---|---:|---:|
| Pass rate | 100.00% | 100.00% |
| p50 latency | 0.324 ms | 0.270 ms |
| Total tokens | 14787 | 13185 |
| Cost per question | $0.00000000 | $0.00000000 |

Estimated offline cost per question:
- ReAct agent: `$0.00083354`
- Deterministic workflow: `$0.00074389`

## Required artifacts

- `race.csv` contains the eight comparable race numbers.
- `budget_termination.log` shows a clean max-tool-call termination.
- `third_tool_diff.md` records the non-overlapping check_deprecation description and enum.

## Safety boundaries

Both runners enforce maximum iterations, maximum tool calls, input/output token caps, projected cost, and wall-clock timeout. The workflow has no agent retry loop; its only repeated operation is inspecting the known source pages for a multi-document case.

## Scope

The benchmark uses the supplied PDFs and golden answers. Token counts are offline estimates and actual API expenditure is zero because no hosted model was called.
