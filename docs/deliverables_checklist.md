# Deliverables Checklist

- [x] Grammar source and adaptations documented: `grammar/JSON.g4` and `docs/final_report.md`
- [x] Baseline strategy present: `strategies/baseline.py`
- [x] Baseline pipeline demonstrated: `logs/baseline.log`
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
- [x] Iteration evolution documented: `docs/iteration_summary.md`
- [x] Agentic loop log present: `docs/agentic_loop_log.md`
- [x] Token usage recorded: `experiments/agentic_loop_usage.json`

- [x] Crash findings documented: no crash-equivalent inputs were found
- [x] Crash triage and deduplication workflow documented: `docs/final_report.md`
- [x] No minimized crash reproducer claimed because no crash was found
- [x] README complete: `README.md`

- [x] Final report complete: `docs/final_report.md`
- [x] Final report source: `docs/final_report.tex`
- [x] Final report PDF: `docs/final_report.pdf`

## Constraint Check

- Official iterations: 5
- Baseline inputs: 100
- Inputs per official iteration: 500
- Total agentic inputs: 2,500
- Per-input timeout: 5 seconds
- Iteration wall-clock cap: 600 seconds (10 minutes)
- Maximum agentic iterations allowed: 5
- LLM model: `gpt-5-mini`
- Quality gate: 40 samples, minimum 70% Parson-valid before full iteration
- LLM total tokens: 38,945
- Estimated LLM cost: about `$0.04`

## Crash / Failure Results

- Crash-equivalent inputs: 0
- Timeouts: 0
- Sanitizer reports: 0
- Nonzero exits: 0
- Minimized crash reproducers: none, because no crash-equivalent input was found

## Campaign Outcome

The five-iteration campaign completed within the assigned iteration and
input budget. The LLM-driven generator improved substantially over the
random-text baseline, reaching 92% or higher Parson-valid inputs in every
official iteration while retaining malformed and structurally stressful
parser-boundary cases.

No crash or timeout was observed within the executed campaign budget.
This is a bounded experimental finding and does not imply that Parson is
free of defects.