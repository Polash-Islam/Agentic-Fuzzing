from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
GRAMMAR = ROOT / "grammar" / "JSON.g4"
HARNESS_BUILD = ROOT / "harness" / "build.sh"
ITERATION_RUNNER = ROOT / "runner" / "iteration_runner.py"
ANALYZER = ROOT / "scripts" / "analyze_results.py"
EXPERIMENTS = ROOT / "experiments"


@dataclass
class LoopConfig:
    start_iteration: int
    max_iterations: int
    tests: int
    timeout: int
    wall_clock_cap: int
    model: str
    allow_overwrite: bool
    dry_run: bool
    gate_samples: int
    min_gate_valid_rate: float


def parse_args() -> argparse.Namespace:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description=(
            "Run the assignment's LLM-driven grammar-to-Hypothesis "
            "agentic fuzzing loop."
        )
    )
    parser.add_argument(
        "--start-iteration",
        type=int,
        default=1,
        help="First iteration to create or run. Default: 1.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Maximum agentic iterations. Assignment cap is 5.",
    )
    parser.add_argument(
        "--tests",
        type=int,
        default=500,
        help="Inputs per iteration. Assignment cap is 500.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="Per-input timeout in seconds.",
    )
    parser.add_argument(
        "--wall-clock-cap",
        type=int,
        default=600,
        help="Overall wall-clock cap per iteration in seconds. Assignment cap is 600.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", ""),
        help="OpenAI model name. Defaults to OPENAI_MODEL from .env.",
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Allow overwriting an existing iteration strategy and log.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write prompts only; do not call the LLM or run experiments.",
    )
    parser.add_argument(
        "--max-llm-retries",
        type=int,
        default=3,
        help="Retry strategy generation when the candidate strategy fails validation.",
    )
    parser.add_argument(
        "--gate-samples",
        type=int,
        default=40,
        help="Number of generated examples to test before a full iteration.",
    )
    parser.add_argument(
        "--min-gate-valid-rate",
        type=float,
        default=70.0,
        help="Minimum Parson-valid percentage required by the pre-run gate.",
    )
    return parser.parse_args()


def run_command(command: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def iteration_dir(iteration: int) -> Path:
    return EXPERIMENTS / f"iteration_{iteration:02d}"


def strategy_path(iteration: int) -> Path:
    return iteration_dir(iteration) / "strategy.py"


def results_path(iteration: int) -> Path:
    return iteration_dir(iteration) / "results.log"


def analyze_logs(logs: list[Path]) -> str:
    existing_logs = [str(path.relative_to(ROOT)) for path in logs if path.exists()]
    if not existing_logs:
        return "No previous logs are available."

    result = run_command(
        [sys.executable, str(ANALYZER.relative_to(ROOT)), *existing_logs]
    )
    return (result.stdout + result.stderr).strip()


def previous_strategy(iteration: int) -> str:
    previous = strategy_path(iteration - 1)
    if previous.exists():
        return read_text(previous)

    fallback = ROOT / "strategies" / "grammar_strategy.py"
    if fallback.exists():
        return read_text(fallback)

    return "No previous strategy is available."


def build_prompt(iteration: int, config: LoopConfig) -> str:
    previous_logs = [ROOT / "logs" / "baseline.log"]
    previous_logs.extend(results_path(i) for i in range(1, iteration))

    feedback = analyze_logs(previous_logs)
    grammar = read_text(GRAMMAR)
    prior_strategy = previous_strategy(iteration)

    return f"""# Agentic Fuzzing Iteration {iteration}

You are generating a Hypothesis strategy for fuzzing the Parson JSON parser.

Target:
- Library: Parson
- Format: JSON
- Harness entry point: json_parse_string
- Harness output classes: VALID, INVALID, CRASH, TIMEOUT
- Parser error text: json_parse_string returns NULL on rejection and does
  not expose line/column/reason diagnostics through this harness.

Budget:
- Iteration cap: {config.max_iterations}
- Inputs per iteration: {config.tests}
- Per-input timeout: {config.timeout} seconds
- Wall-clock cap per iteration: {config.wall_clock_cap} seconds

Assignment requirements:
- Start from the JSON grammar.
- Use composable Hypothesis strategies.
- Use st.recursive or @st.composite for recursive productions.
- Cover empty arrays/objects, nesting, strings, escapes, Unicode, numbers,
  duplicate keys, extreme numeric values, and near-valid malformed inputs.
- Optimize using feedback: crashes/timeouts, parser rejection patterns,
  and structural diversity.
- Since Parson does not provide detailed parser error messages here, use
  analyzer-derived rejection categories as the parser-error proxy.

Important Parson observations from previous runs are campaign-specific.
Do not assume they are JSON-standard violations.

Hard strategy requirements for this campaign:
- Define json_strategy as a Hypothesis SearchStrategy that returns str.
- Prefer mostly Parson-compatible valid JSON.
- Use a weighted mix: about 75% valid recursive JSON, 15% valid stress JSON,
  and at most 10% near-valid malformed probes.
- Use json.dumps for JSON strings.
- In the valid branch, avoid duplicate object keys and avoid embedded NUL keys.
- Avoid zero-with-exponent numbers such as 0E1 and -0E-1 in the valid branch.
- Keep valid numeric exponents within safe finite bounds, preferably -250..250.
- Include valid stress cases: nested arrays/objects, wide arrays/objects,
  long strings, escape-heavy strings, Unicode escapes, and numeric boundaries.
- Malformed probes should be explicit and rare, not accidental syntax mistakes.

Return only Python code for experiments/iteration_{iteration:02d}/strategy.py.
The file must define a top-level Hypothesis strategy named json_strategy.
Do not include markdown fences.

## JSON Grammar

```antlr
{grammar}
```

## Previous Strategy

```python
{prior_strategy}
```

## Previous Feedback

```text
{feedback}
```
"""


def call_openai(prompt: str, model: str) -> tuple[str, dict[str, int | None]]:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise SystemExit(
            "The openai package is not installed. Install it or run with --dry-run."
        ) from error

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is not set. Add it to .env or run with --dry-run."
        )
    if not model:
        raise SystemExit(
            "No model configured. Pass --model or set OPENAI_MODEL in .env."
        )

    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You write concise, runnable Python Hypothesis strategies. "
                    "Return only source code."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )

    usage = getattr(response, "usage", None)
    usage_data: dict[str, int | None] = {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
    return response.output_text, usage_data


def retry_prompt(original_prompt: str, candidate: str, error: Exception) -> str:
    return f"""{original_prompt}

## Candidate Strategy Validation Failure

The previous candidate strategy failed before running the harness.
Fix the strategy and return only Python code.

Validation error:

```text
{type(error).__name__}: {error}
```

Invalid candidate:

```python
{candidate}
```
"""


def quality_retry_prompt(
    original_prompt: str,
    candidate: str,
    gate: dict[str, Any],
) -> str:
    return f"""{original_prompt}

## Candidate Strategy Quality Gate Failure

The previous candidate was syntactically runnable, but it was too weak for
the assignment loop. Fix the strategy and return only Python code.

Quality gate result:

```json
{json.dumps(gate, indent=2, sort_keys=True)}
```

Required fix:
- Raise Parson VALID rate above the gate threshold.
- Reduce malformed syntax.
- Reduce number_overflow and zero_with_exponent cases.
- Keep malformed probes below 10% of generated examples.
- Preserve recursive JSON structures and valid stress cases.

Weak candidate:

```python
{candidate}
```
"""


def extract_code(llm_text: str) -> str:
    match = re.search(r"```(?:python)?\s*(.*?)```", llm_text, flags=re.DOTALL)
    code = match.group(1) if match else llm_text
    return code.strip() + "\n"


def load_strategy_module(path: Path):
    spec = importlib.util.spec_from_file_location("candidate_strategy", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "json_strategy"):
        raise RuntimeError(f"{path} does not define json_strategy")
    return module


def validate_strategy(path: Path) -> None:
    module = load_strategy_module(path)

    # Basic sanity check before spending a full fuzzing run.
    for _ in range(5):
        value = module.json_strategy.example()
        if not isinstance(value, str):
            raise RuntimeError("json_strategy.example() did not return a string")


def run_quality_gate(path: Path, config: LoopConfig) -> dict[str, Any]:
    module = load_strategy_module(path)
    valid = 0
    invalid = 0
    python_valid = 0
    python_invalid = 0
    generation_errors = 0
    samples: list[str] = []

    with tempfile.TemporaryDirectory(prefix="agentic_gate_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        for index in range(1, config.gate_samples + 1):
            try:
                value = module.json_strategy.example()
            except Exception as error:
                generation_errors += 1
                samples.append(f"generation error: {type(error).__name__}: {error}")
                continue

            if not isinstance(value, str):
                generation_errors += 1
                samples.append(f"non-string example: {type(value).__name__}")
                continue

            if len(samples) < 5:
                samples.append(value[:240])

            try:
                json.loads(value)
                python_valid += 1
            except json.JSONDecodeError:
                python_invalid += 1

            input_file = temp_dir / f"gate_{index:04d}.json"
            input_file.write_text(value, encoding="utf-8", errors="surrogatepass")
            result = run_command(
                [str((ROOT / "harness" / "harness").relative_to(ROOT)), str(input_file)]
            )
            if result.stdout.strip() == "VALID JSON":
                valid += 1
            elif result.stdout.strip() == "INVALID JSON":
                invalid += 1

    valid_rate = valid / config.gate_samples * 100 if config.gate_samples else 0.0
    python_valid_rate = (
        python_valid / config.gate_samples * 100 if config.gate_samples else 0.0
    )
    return {
        "samples": config.gate_samples,
        "valid": valid,
        "invalid": invalid,
        "valid_rate": round(valid_rate, 2),
        "python_valid": python_valid,
        "python_invalid": python_invalid,
        "python_valid_rate": round(python_valid_rate, 2),
        "generation_errors": generation_errors,
        "sample_outputs": samples,
        "passed": (
            generation_errors == 0
            and valid_rate >= config.min_gate_valid_rate
            and python_valid_rate >= config.min_gate_valid_rate
        ),
        "threshold": config.min_gate_valid_rate,
    }


def prepare_iteration_directory(path: Path, allow_overwrite: bool) -> None:
    if path.exists() and not allow_overwrite:
        raise SystemExit(
            f"{path.relative_to(ROOT)} already exists. "
            "Use --allow-overwrite to replace it, or choose a later iteration."
        )
    path.mkdir(parents=True, exist_ok=True)
    (path / "inputs").mkdir(exist_ok=True)
    (path / "crashes").mkdir(exist_ok=True)


def run_iteration(iteration: int, config: LoopConfig) -> str:
    result = run_command(
        [
            sys.executable,
            str(ITERATION_RUNNER.relative_to(ROOT)),
            "--iteration",
            str(iteration),
            "--tests",
            str(config.tests),
            "--timeout",
            str(config.timeout),
            "--wall-clock-cap",
            str(config.wall_clock_cap),
        ]
    )
    return (result.stdout + result.stderr).strip()


def write_metadata(path: Path, config: LoopConfig, usage: dict[str, int | None]) -> None:
    metadata = {
        "config": asdict(config),
        "usage": usage,
    }
    (path / "agentic_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    config = LoopConfig(
        start_iteration=args.start_iteration,
        max_iterations=args.max_iterations,
        tests=args.tests,
        timeout=args.timeout,
        wall_clock_cap=args.wall_clock_cap,
        model=args.model,
        allow_overwrite=args.allow_overwrite,
        dry_run=args.dry_run,
        gate_samples=args.gate_samples,
        min_gate_valid_rate=args.min_gate_valid_rate,
    )

    if config.tests > 500:
        raise SystemExit("Assignment cap is 500 inputs per iteration.")
    if config.max_iterations > 5:
        raise SystemExit("Assignment cap is 5 agentic iterations.")
    if config.wall_clock_cap > 600:
        raise SystemExit("Assignment wall-clock cap is 600 seconds per iteration.")

    build_result = run_command([str(HARNESS_BUILD.relative_to(ROOT))])
    if build_result.returncode != 0:
        raise SystemExit(build_result.stdout + build_result.stderr)

    stop = config.start_iteration + config.max_iterations
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    for iteration in range(config.start_iteration, stop):
        path = iteration_dir(iteration)
        prepare_iteration_directory(path, config.allow_overwrite)

        prompt = build_prompt(iteration, config)
        (path / "llm_prompt.md").write_text(prompt, encoding="utf-8")

        if config.dry_run:
            print(f"[iteration {iteration:02d}] prompt written; dry run stops here")
            continue

        usage = {"input_tokens": None, "output_tokens": None, "total_tokens": None}
        code = ""
        active_prompt = prompt
        strategy = strategy_path(iteration)

        for attempt in range(1, args.max_llm_retries + 1):
            llm_text, usage = call_openai(active_prompt, config.model)
            (path / f"llm_response_attempt_{attempt}.txt").write_text(
                llm_text,
                encoding="utf-8",
            )

            code = extract_code(llm_text)
            strategy.write_text(code, encoding="utf-8")

            try:
                validate_strategy(strategy)
                gate = run_quality_gate(strategy, config)
                (path / f"quality_gate_attempt_{attempt}.json").write_text(
                    json.dumps(gate, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                if not gate["passed"]:
                    raise RuntimeError(
                        "quality gate failed: "
                        f"valid_rate={gate['valid_rate']} "
                        f"python_valid_rate={gate['python_valid_rate']} "
                        f"threshold={gate['threshold']}"
                    )
                (path / "llm_response.txt").write_text(llm_text, encoding="utf-8")
                break
            except Exception as error:
                (path / f"validation_error_attempt_{attempt}.txt").write_text(
                    f"{type(error).__name__}: {error}\n",
                    encoding="utf-8",
                )
                if attempt == args.max_llm_retries:
                    raise
                gate_path = path / f"quality_gate_attempt_{attempt}.json"
                if gate_path.exists():
                    gate = json.loads(gate_path.read_text(encoding="utf-8"))
                    active_prompt = quality_retry_prompt(prompt, code, gate)
                else:
                    active_prompt = retry_prompt(prompt, code, error)

        run_output = run_iteration(iteration, config)
        (path / "agentic_run_output.txt").write_text(run_output + "\n", encoding="utf-8")

        analysis = analyze_logs([results_path(iteration)])
        (path / "analysis.txt").write_text(analysis + "\n", encoding="utf-8")

        write_metadata(path, config, usage)
        for key in total_usage:
            value = usage.get(key)
            if value is not None:
                total_usage[key] += value

        print(f"[iteration {iteration:02d}] complete")
        print(analysis)

    (EXPERIMENTS / "agentic_loop_usage.json").write_text(
        json.dumps(total_usage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
