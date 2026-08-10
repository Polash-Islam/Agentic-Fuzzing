# Agentic Fuzzing of the Parson JSON Parser

## Abstract

This project implements an LLM-driven grammar-based fuzzer for Parson, a lightweight C JSON parser pinned to commit `ba29f4eda9ea7703a9f6a9cf2b0532a2605723c3`. Starting from the ANTLR JSON grammar in `grammar/JSON.g4`, the loop asks an LLM to generate Hypothesis strategies, runs them through a sanitizer-enabled C harness, summarizes feedback, and refines the next strategy. The official campaign used one 100-input baseline and five 500-input agentic iterations. No crashes, timeouts, sanitizer reports, or nonzero exits were found.

## Design

The target format is JSON. The grammar covers objects, arrays, strings, numbers, booleans, null, whitespace, escape sequences, and Unicode escapes. I kept `grammar/JSON.g4` as the formal seed and adapted the generated strategies, not the grammar file: the valid branch avoids raw control characters, duplicate keys, and zero-with-exponent forms that the campaign feedback showed were frequently rejected, while a small malformed branch keeps those cases as parser-boundary probes.

The harness in `harness/harness.c` reads one file, calls Parson's `json_parse_string`, prints `VALID JSON` or `INVALID JSON`, frees allocated values, and exits normally for both accepted inputs and clean parser rejections. Parson's public parse API returns `NULL` on parse failure but does not expose a detailed parser error message, so the feedback loop used the `INVALID JSON` outcome plus analyzer-derived rejection categories. `harness/build.sh` compiles the harness and Parson with `-fsanitize=address,undefined`. The runner classifies nonzero exits or sanitizer markers as `CRASH`; per-input timeouts are logged as `TIMEOUT` for diagnosis but counted as crash-equivalent for grading. The current runner also enforces a 600-second wall-clock cap as a backstop.

The agentic loop is implemented in `runner/agentic_loop.py`. For each iteration, it builds a prompt from the grammar, previous strategy, and analyzer feedback; calls the OpenAI API; saves prompt/response artifacts; extracts a candidate `strategy.py`; validates that `json_strategy` generates strings; applies a 40-sample quality gate requiring at least 70% Parson-valid examples; runs 500 inputs through `runner/iteration_runner.py`; and saves `analysis.txt` for the next prompt.

Because the assignment is black-box beyond sanitizers, the feedback signals were parser acceptance rate, invalid-input categories, and cumulative structural counts from `scripts/analyze_results.py`. Structural counts are only a proxy for diversity, not code coverage.

## Findings

The random-text baseline confirmed the pipeline but produced only 3 valid inputs out of 100. The quality-gated LLM loop then produced high-validity strategies:

| Experiment | Total | Valid | Invalid | Crash | Timeout | Valid Rate |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 100 | 3 | 97 | 0 | 0 | 3.00% |
| Iteration 1 | 500 | 464 | 36 | 0 | 0 | 92.80% |
| Iteration 2 | 500 | 473 | 27 | 0 | 0 | 94.60% |
| Iteration 3 | 500 | 468 | 32 | 0 | 0 | 93.60% |
| Iteration 4 | 500 | 460 | 40 | 0 | 0 | 92.00% |
| Iteration 5 | 500 | 463 | 37 | 0 | 0 | 92.60% |

Validity was not strictly monotonic, but it stayed above 92% in all five iterations. Iteration 4 had lower validity than Iteration 2, but it increased structural stress substantially, including `array_items: 6199` and `object_keys: 6168`. This reflects a tradeoff between acceptance rate and parser-boundary exploration rather than a pipeline failure.

The remaining invalid inputs were a small minority. Because Parson did not provide textual parse errors through `json_parse_string`, the report records rejection categories instead of raw parser messages. They were mainly categorized as `syntax_invalid_for_python_json`, `duplicate_key`, and `zero_with_exponent`. These labels are campaign-specific analyzer categories, not claims that Parson violates the JSON standard. The campaign distinguishes generated strings, Python `json.loads` acceptance during analysis, Parson acceptance through `json_parse_string`, clean rejection, crash, and timeout outcomes.

No crash-equivalent failures were found. No timeout files, sanitizer reports, nonzero exits, or crash inputs were produced, so there were no crash signatures to deduplicate and no minimized reproducers to verify. The repository still includes future-crash support: `scripts/triage_crashes.py` normalizes sanitizer stack frames into `SIG-...` groups, and `scripts/minimize_crash.py` uses `hypothesis.find()` to shrink strategy-reproducible crashing inputs before standalone verification. This does not prove that Parson is bug-free; it means the executed budget did not reach a crashing path or hang.

The most under-tested areas are very large documents, extremely long escape-heavy strings, and Parson APIs beyond the parser entry point. The fuzzer generated stress cases, but process-per-input execution and the 500-example cap limited how far those dimensions could be pushed.

The five LLM iterations used `gpt-5-mini` with 19,620 input tokens, 19,325 output tokens, 38,945 total tokens, and an estimated cost of about `$0.04`. Token records are stored in `experiments/iteration_*/agentic_metadata.json` and summarized in `experiments/agentic_loop_usage.json`.

## Challenges

The main challenge was steering the LLM toward inputs that were both syntactically useful and accepted deeply enough by Parson. Early LLM-generated approaches could produce too many rejected examples, so I added the quality gate required by the assignment's generator-validation step. This improved the official campaign to a stable 92%+ valid rate.

A second challenge was balancing high valid throughput with malformed or near-valid probes. Too many malformed examples waste the parser budget; too few reduce rejection-path testing. The final loop kept malformed cases as a controlled minority while preserving structural diversity.

The harness is intentionally parser-entry focused. With more time, I would add a broader Parson API harness for serialization, pretty serialization, validation, persistence, comment parsing, and deep copy. I would also add richer structural goals or differential checks, while still respecting the assignment's no-coverage-guidance constraint.

## References

Primary artifacts: `grammar/JSON.g4`, `harness/harness.c`, `harness/build.sh`, `runner/agentic_loop.py`, `runner/iteration_runner.py`, `scripts/analyze_results.py`, `scripts/triage_crashes.py`, `scripts/minimize_crash.py`, `docs/iteration_summary.md`, and `docs/agentic_loop_log.md`.
