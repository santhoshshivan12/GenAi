# Week 8 Trajectory Evaluation

Run timestamp (UTC): `2026-09-21T17:37:28.192149+00:00`  
Cases: `10` Week 7 documentation migrations  
Single mitigation: `re-planning exact source/page pairs after search`

## Flow

`question -> agent tool calls -> trajectory capture -> path/argument scoring -> gap -> one mitigation -> re-run -> regression check`

## Required trajectory metrics

| Metric | Before | After |
|---|---:|---:|
| Tool-choice accuracy | 85.29% | 100.00% |
| Argument validity | 100.00% | 100.00% |
| Step efficiency (taken / needed; 1.0 is optimal) | 1.1667 | 1.0000 |
| Cost/question p50 | $0.00095378 | $0.00080948 |
| Cost/question max | $0.00152355 | $0.00099885 |
| Outcome pass rate | 100.00% | 100.00% |
| Trajectory pass rate | 70.00% | 100.00% |
| Outcome - trajectory gap | 30.00 pp | 0.00 pp |

## Right answer, wrong path

`hard-10` passed the outcome eval but failed the trajectory eval.
Observed path: `search_documentation -> inspect_source -> inspect_source -> inspect_source -> search_documentation -> inspect_source`.
It took 6 tool steps; the accepted path needs 3.

## Exactly one mitigation

Top mode `unnecessary_steps`: **3 -> 0** cases.
Measured price: **15.00 p50 added tokens/question** (max 15).
No other mitigation was applied.

## Regression matrix

| Failure mode | Before | After | Delta |
|---|---:|---:|---:|
| wrong_tool_choice | 0 | 0 | +0 |
| invalid_arguments | 0 | 0 | +0 |
| missing_required_step | 0 | 0 | +0 |
| unnecessary_steps | 3 | 0 | -3 |
| repeated_tool_loop | 0 | 0 | +0 |
| premature_termination | 0 | 0 | +0 |
| outcome_failure | 0 | 0 | +0 |
| right_answer_wrong_path | 3 | 0 | -3 |

Modes that worsened or appeared: none.

## Accepted alternate paths

The two-document cases `hard-03`, `hard-05`, and `hard-10` accept either source inspection order. All other cases assert one valid tool order.

Token and cost values use Week 7's transparent offline estimator. Actual provider spend remains $0 because this suite makes no hosted-model call.
