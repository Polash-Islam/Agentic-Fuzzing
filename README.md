# Agentic Fuzzing

## Overview

This repository contains an assignment implementation of an LLM-driven, grammar-based fuzzer for the Parson JSON parser. The workflow starts from an ANTLR JSON grammar, asks an LLM to generate Hypothesis strategies, runs those strategies through a sanitizer-enabled C harness, analyzes feedback, and refines the next strategy within a five-iteration budget.

The current official campaign was run from a fresh baseline plus five quality-gated agentic iterations. Each official iteration generated 500 inputs. No crashes, timeouts, sanitizer reports, or nonzero exits were observed in the checked logs.

## Target

- Library: Parson
- Language: C
- Input format: JSON
- Checked target commit: `ba29f4eda9ea7703a9f6a9cf2b0532a2605723c3`
- Harnessed parser entry point: `json_parse_string`

The harness exercises Parson's parser entry point only. It does not claim full coverage of serialization, validation, persistence, comment parsing, or deep-copy APIs.

## Architecture

```text
grammar/JSON.g4
    |
    v
runner/agentic_loop.py
    |
    v
LLM-generated Hypothesis strategy.py
    |
    v
runner/iteration_runner.py
    |
    v
harness/harness.c
    |
    v
Parson json_parse_string
    |
    v
VALID / INVALID / CRASH / TIMEOUT
    |
    v
scripts/analyze_results.py
    |
    v
next LLM prompt and refined strategy
```

`runner/agentic_loop.py` implements the agentic loop. It builds prompts from the grammar, previous strategy, and analyzer feedback; calls the OpenAI API when `OPENAI_API_KEY` is configured; writes prompt/response artifacts; extracts a candidate `strategy.py`; validates that `json_strategy` exists; applies a 40-sample pre-run quality gate requiring at least 70% Parson-valid examples; runs the bounded fuzzing iteration; and saves analyzer feedback for the next prompt.

## Main Artifacts

```text
grammar/JSON.g4
harness/build.sh
harness/harness.c
strategies/baseline.py
runner/agentic_loop.py
runner/iteration_runner.py
scripts/analyze_results.py
logs/baseline.log
experiments/iteration_01/
experiments/iteration_02/
experiments/iteration_03/
experiments/iteration_04/
experiments/iteration_05/
experiments/agentic_loop_usage.json
docs/final_report.md
docs/iteration_summary.md
docs/agentic_loop_log.md
```

Each official iteration directory contains the generated `strategy.py`, `llm_prompt.md`, `llm_response.txt`, `agentic_metadata.json`, generated `inputs/`, `results.log`, and `analysis.txt`.

## Harness and Runner

The harness reads one input file, calls `json_parse_string`, prints `VALID JSON` or `INVALID JSON`, frees allocated values, and exits normally for accepted and rejected inputs.

The build script compiles with:

```text
-g -O0 -Wall -Wextra -fsanitize=address,undefined
```

The iteration runner supports:

```text
--iteration  required integer
--tests      optional integer, default 500
--timeout    optional integer, default 5 seconds
```

Timeouts are logged as `TIMEOUT`. Nonzero exits or sanitizer markers are logged as `CRASH`.

## Official Results

Verified with `scripts/analyze_results.py`:

| Experiment | Total | Valid | Invalid | Crash | Timeout | Valid Rate |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 100 | 3 | 97 | 0 | 0 | 3.00% |
| Iteration 1 | 500 | 464 | 36 | 0 | 0 | 92.80% |
| Iteration 2 | 500 | 473 | 27 | 0 | 0 | 94.60% |
| Iteration 3 | 500 | 468 | 32 | 0 | 0 | 93.60% |
| Iteration 4 | 500 | 460 | 40 | 0 | 0 | 92.00% |
| Iteration 5 | 500 | 463 | 37 | 0 | 0 | 92.60% |

The quality-gated agentic loop immediately improved over the random baseline and kept Parson acceptance above 92% in every official iteration. The remaining invalid inputs were mostly categorized as malformed syntax, duplicate keys, and zero-with-exponent numeric forms. This is documented as parser-boundary exploration and feedback-loop limitation, not as a crash finding.

## Token and Cost Budget

The five LLM strategy-generation iterations used:

| Model | Input Tokens | Output Tokens | Total Tokens | Estimated Cost |
|---|---:|---:|---:|---:|
| `gpt-5-mini` | 19,620 | 19,325 | 38,945 | about `$0.04` |

The cost estimate uses GPT-5 mini standard rates of `$0.25` per 1M input tokens and `$2.00` per 1M output tokens. The exact billing page may differ due to processing mode or account settings, but the recorded token usage is stored in `experiments/iteration_*/agentic_metadata.json`.

## Crash Triage

Verified crash-related results:

- Crashes: 0
- Timeouts: 0
- Sanitizer reports in checked logs: 0
- Nonzero exits in checked logs: 0
- Crash files under official iteration crash directories: none

No crash inputs were produced, so there were no sanitizer signatures to deduplicate and no reproducers to minimize. This means no crash was found within the executed budget; it does not prove that Parson is bug-free.

## Limitations

- The harness exercises only `json_parse_string`.
- Structural diversity is a proxy signal, not code coverage.
- Invalid-cause labels are analyzer classifications, not formal JSON-standard judgments.
- No crash or vulnerability was found.

## Reproducibility

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Build and smoke-test the harness:

```bash
./harness/build.sh
./harness/harness harness/sample_inputs/valid.json
./harness/harness harness/sample_inputs/invalid.json
```

Analyze the checked logs:

```bash
venv/bin/python scripts/analyze_results.py \
  logs/baseline.log \
  experiments/iteration_01/results.log \
  experiments/iteration_02/results.log \
  experiments/iteration_03/results.log \
  experiments/iteration_04/results.log \
  experiments/iteration_05/results.log
```

Run a new LLM-driven campaign:

```bash
venv/bin/python runner/agentic_loop.py --start-iteration 1 --max-iterations 5 --tests 500 --model gpt-5-mini
```

Use `--allow-overwrite` only if replacing existing official iteration artifacts is intentional.
