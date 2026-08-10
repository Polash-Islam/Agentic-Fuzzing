# Agentic Loop Log

This document records the current official LLM-driven agentic campaign. The executable loop implementation is `runner/agentic_loop.py`.

## Loop Components

| Loop Step | Repository Artifact |
|---|---|
| Grammar seed | `grammar/JSON.g4` |
| LLM loop orchestrator | `runner/agentic_loop.py` |
| Strategy under test | `experiments/iteration_XX/strategy.py` |
| Bounded execution | `runner/iteration_runner.py --iteration N --tests 500` |
| Harness target | `harness/harness.c` calling `json_parse_string` |
| Sanitizer build | `harness/build.sh` |
| Run log | `experiments/iteration_XX/results.log` |
| Feedback summary | `scripts/analyze_results.py` and `experiments/iteration_XX/analysis.txt` |
| Prompt/response record | `experiments/iteration_XX/llm_prompt.md` and `llm_response.txt` |
| Token usage | `experiments/iteration_XX/agentic_metadata.json` |

## Feedback Signals

The loop used three feedback signals:

- parser acceptance rate from harness output;
- invalid-input categories from `scripts/analyze_results.py`;
- cumulative structural counts for parseable inputs.

No coverage-guided feedback was used.

## Iteration Evolution

| Stage | Feedback Observed | Refinement Outcome |
|---|---|---|
| Baseline | 3 valid and 97 invalid inputs out of 100 arbitrary-text inputs. | Move to LLM-generated grammar-shaped JSON strategies. |
| Iteration 1 | 464 valid and 36 invalid inputs. Quality gate accepted the strategy after retry. | Feedback was included in the Iteration 2 prompt. |
| Iteration 2 | 473 valid and 27 invalid inputs. Highest valid rate of the campaign. | Feedback was included in the Iteration 3 prompt. |
| Iteration 3 | 468 valid and 32 invalid inputs. Strong structural diversity continued. | Feedback was included in the Iteration 4 prompt. |
| Iteration 4 | 460 valid and 40 invalid inputs. Structural counts increased for arrays and objects. | Feedback was included in the final iteration prompt. |
| Iteration 5 | 463 valid and 37 invalid inputs. Final valid rate was 92.60%. | Stop at the five-iteration assignment cap. |

## Budget Accounting

| Model | Input Tokens | Output Tokens | Total Tokens | Estimated Cost |
|---|---:|---:|---:|---:|
| `gpt-5-mini` | 19,620 | 19,325 | 38,945 | about `$0.04` |

The cost estimate uses GPT-5 mini standard rates of `$0.25` per 1M input tokens and `$2.00` per 1M output tokens. Exact billing may vary by account processing mode. The recorded token counts are stored in `agentic_metadata.json` files and summarized in `experiments/agentic_loop_usage.json`.

## Crash Triage Outcome

No crashes, timeouts, sanitizer reports, or nonzero exits were present in the checked logs. No crash files were produced in the official iteration crash directories, so there were no crash signatures to deduplicate and no reproducers to minimize.
