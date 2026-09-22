from __future__ import annotations

import json

from week8.evaluation import DEFAULT_OUTPUT_DIR, run_trajectory_evaluation


def main() -> None:
    report = run_trajectory_evaluation()
    print(json.dumps({
        "before": report["before"]["metrics"],
        "after": report["after"]["metrics"],
        "mitigation": report["mitigation"],
    }, indent=2))
    print(f"Report saved to {DEFAULT_OUTPUT_DIR / 'trajectory_results.md'}")


if __name__ == "__main__":
    main()
