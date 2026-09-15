# Week 7 Agent Loop vs Deterministic Workflow

This package implements the Week 7 race using the supplied golden sets and PDF documentation. It is an extension of the existing project, not a new application.

## What is compared

- `ReActAgent`: observes documentation results, chooses the next tool, and can refine the search.
- `DeterministicWorkflow`: fixed search -> inspect -> optional deprecation branch -> output validation stages with no agent retry loop.
- Both use the same `offline-evidence-synthesizer-v1` output model contract and the same three tools.

## Registered tools

1. `search_documentation` - search documentation pages.
2. `inspect_source` - read one source page.
3. `check_deprecation` - check one endpoint parameter for deprecation in a selected API version.

The third tool uses the enum `2022-11-28 | 2025-06-01`. Migration output validation remains an internal evaluator so the required third tool is unambiguously the deprecation tool.

## Run commands

Run both architectures and generate the race artifacts:

```powershell
python -m week7
```

Run each architecture independently:

```powershell
python -m week7.agent
python -m week7.workflow
```

Optional controls include `--scenario-count`, `--max-iterations`, `--max-tool-calls`, `--max-input-tokens`, `--max-output-tokens`, `--max-cost-usd`, and `--max-latency-seconds`.

## Chatbot UI

The Week 7 runner is available inside the existing FastAPI chatbot UI. Start the application from the project root:

```powershell
python main.py
```

Open `http://127.0.0.1:8000`, select the **Week 7 Agent Race** tab, choose one of the 10 supplied migration questions, choose **ReAct Agent** or **Deterministic Workflow**, and click **Run migration**. The page displays the answer, validation result, latency, token count, tool-call count, and a live execution log. ReAct runs include reasoning and adaptive tool calls; workflow runs show the fixed tool sequence. UI run payloads are also appended to `results/ui_runs.jsonl`.

The UI uses these endpoints:

- `GET /week7/scenarios` - returns the selectable migration questions.
- `POST /week7/chat` - accepts `{"scenario_id": "medium-01", "architecture": "react_agent"}`.
## Required artifacts

- `results/race.csv` - pass rate, p50 latency, total tokens, and actual cost per question for both systems;
- `results/benchmark_results.json` - complete per-case telemetry and all budget settings;
- `results/architecture_verdict.md` - under-150-word decision-rule verdict plus supporting metrics;
- `results/budget_termination.log` - clean forced circuit-breaker termination;
- `third_tool_diff.md` - description and enum diff for `check_deprecation`.

The default run uses the same 10 questions for both systems. Three supplied migration cases are explicitly deprecation-dependent: `medium-01`, `medium-04`, and `medium-07`. Their next lookup is selected after the inspected source page reveals a deprecated or version-sensitive parameter.

The benchmark is offline-first. Actual API cost is `$0` because no hosted model request is made; estimated cost is calculated from offline token estimates for comparison.