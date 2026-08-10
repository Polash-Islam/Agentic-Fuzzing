# Deliverables Checklist

- [x] Grammar present: `grammar/JSON.g4`
- [x] Baseline strategy present: `strategies/baseline.py`
- [x] Harness present: `harness/harness.c`
- [x] Sanitizers configured: `harness/build.sh`
- [x] Iteration runner present: `runner/iteration_runner.py`
- [x] LLM-driven agentic loop implementation present: `runner/agentic_loop.py`
- [x] Feedback analyzer present: `scripts/analyze_results.py`
- [x] Crash triage/signature utility present: `scripts/triage_crashes.py`
- [x] Crash minimization utility present: `scripts/minimize_crash.py`
- [x] Iteration 1 complete: `experiments/iteration_01/strategy.py` and `experiments/iteration_01/results.log`
- [x] Iteration 2 complete: `experiments/iteration_02/strategy.py` and `experiments/iteration_02/results.log`
- [x] Iteration 3 complete: `experiments/iteration_03/strategy.py` and `experiments/iteration_03/results.log`
- [x] Iteration 4 complete: `experiments/iteration_04/strategy.py` and `experiments/iteration_04/results.log`
- [x] Iteration 5 complete: `experiments/iteration_05/strategy.py` and `experiments/iteration_05/results.log`
- [x] LLM prompt/response artifacts present in each iteration directory
- [x] Token usage recorded: `experiments/agentic_loop_usage.json`
- [x] Crash triage documented: `docs/final_report.md`
- [x] README complete: `README.md`
- [x] Final report complete: `docs/final_report.md`
- [x] Iteration summary complete: `docs/iteration_summary.md`

## Constraint Check

- Official iterations: 5
- Baseline inputs: 100
- Inputs per official iteration: 500
- Per-input timeout: 5 seconds
- Current runner wall-clock cap: 600 seconds
- LLM model: `gpt-5-mini`
- Quality gate: 40 samples, minimum 70% Parson-valid before full iteration
- LLM total tokens: 38,945
- Estimated LLM cost: about `$0.04`
- Crash result: 0
- Timeout result: 0
- Sanitizer reports: 0
- Nonzero exits: 0
