# Week 8 Trajectory Evaluation

This package extends the Week 7 documentation agent. It scores how the agent
reached its answer, measures the outcome-vs-trajectory gap, applies exactly one
mitigation, and checks every tracked failure mode for regressions.

## Execution flow

```text
10 Week 7 questions
        |
        v
Run baseline ReAct agent
        |
        v
Capture tool name + arguments + steps + tokens + latency + cost
        |
        v
Compare with asserted accepted path set
        |
        +--> tool-choice accuracy
        +--> argument validity
        +--> steps taken / steps needed
        +--> cost p50 and max
        |
        v
Outcome pass rate - trajectory pass rate
        |
        v
Apply ONE mitigation: re-plan exact source/page pairs after search
        |
        v
Re-run all 10 cases and compare every failure-mode count
```

`hard-03`, `hard-05`, and `hard-10` accept either order for their two source
inspections. The other seven cases have one accepted order. Semantic argument
validation rejects nonexistent corpus pages and invented API
version/endpoint/parameter combinations.

## Run

From the project root:

```powershell
python trajectory_eval.py
# equivalent:
python -m week8
```

Generated artifacts:

- `week8/results/trajectory_results.json` — complete per-case traces and metrics;
- `week8/results/trajectory_results.md` — submission-ready results table, gap,
  false-positive trace, mitigation price, and regression matrix.

Run tests:

```powershell
python -m unittest week8.test_week8 week7.test_week7
```
