from __future__ import annotations

import argparse
import importlib.util
import subprocess
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, Phase, find, settings
from hypothesis.errors import NoSuchExample


SANITIZER_MARKERS = (
    "AddressSanitizer",
    "UndefinedBehaviorSanitizer",
    "runtime error:",
)


def load_strategy(strategy_file: Path):
    spec = importlib.util.spec_from_file_location("minimize_strategy", strategy_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load strategy from {strategy_file}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "json_strategy"):
        raise AttributeError(f"{strategy_file} does not contain json_strategy")

    strategy = module.json_strategy
    if callable(strategy) and not hasattr(strategy, "example"):
        strategy = strategy()
    return strategy


def run_harness(harness: Path, value: str, timeout: int):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        handle.write(value)
        input_path = Path(handle.name)

    try:
        try:
            result = subprocess.run(
                [str(harness), str(input_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stderr = result.stderr or ""
            if result.returncode != 0 or any(marker in stderr for marker in SANITIZER_MARKERS):
                return "CRASH", result.returncode, result.stdout, stderr
            if result.stdout.strip() == "VALID JSON":
                return "VALID", result.returncode, result.stdout, stderr
            if result.stdout.strip() == "INVALID JSON":
                return "INVALID", result.returncode, result.stdout, stderr
            return "UNKNOWN", result.returncode, result.stdout, stderr
        except subprocess.TimeoutExpired as error:
            return "TIMEOUT", "TIMEOUT", error.stdout or "", error.stderr or ""
    finally:
        input_path.unlink(missing_ok=True)


def is_crash_equivalent(status: str) -> bool:
    return status in {"CRASH", "TIMEOUT"}


def verify_input(harness: Path, input_file: Path, timeout: int, runs: int) -> bool:
    value = input_file.read_text(encoding="utf-8", errors="replace")
    observed: list[str] = []

    for _ in range(runs):
        status, _, _, _ = run_harness(harness, value, timeout)
        observed.append(status)

    print(f"standalone_verification_statuses: {', '.join(observed)}")
    return all(is_crash_equivalent(status) for status in observed)


def minimize_from_strategy(strategy_file: Path, harness: Path, timeout: int, max_examples: int) -> str:
    strategy = load_strategy(strategy_file)

    def predicate(value: str) -> bool:
        if not isinstance(value, str):
            return False
        status, _, _, _ = run_harness(harness, value, timeout)
        return is_crash_equivalent(status)

    shrink_settings = settings(
        max_examples=max_examples,
        deadline=None,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.filter_too_much,
            HealthCheck.data_too_large,
        ],
        phases=[
            Phase.generate,
            Phase.shrink,
        ],
    )
    return find(strategy, predicate, settings=shrink_settings)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Minimize strategy-reproducible crash-equivalent inputs with "
            "Hypothesis shrinking. Saved inputs can be verified directly, but "
            "shrinking requires a strategy that can reproduce the failing class."
        )
    )
    parser.add_argument(
        "--strategy",
        type=Path,
        help="Strategy file containing json_strategy. Required for shrinking.",
    )
    parser.add_argument(
        "--harness",
        type=Path,
        default=Path("harness/harness"),
        help="Compiled harness executable.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Existing crash input to verify before or after minimization.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("minimized_reproducer.json"),
        help="Where to write the minimized reproducer.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="Per-harness-run timeout in seconds. Timeouts are crash-equivalent.",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=5000,
        help="Hypothesis search budget for finding and shrinking a failing example.",
    )
    parser.add_argument(
        "--verify-runs",
        type=int,
        default=3,
        help="Number of standalone verification runs for crash-equivalent inputs.",
    )
    args = parser.parse_args()

    if args.input is not None:
        verified = verify_input(args.harness, args.input, args.timeout, args.verify_runs)
        print(f"saved_input_crash_equivalent: {verified}")

    if args.strategy is None:
        if args.input is None:
            raise SystemExit("Provide --strategy to shrink, --input to verify, or both.")
        return

    try:
        minimized = minimize_from_strategy(
            args.strategy,
            args.harness,
            args.timeout,
            args.max_examples,
        )
    except NoSuchExample:
        raise SystemExit(
            "No crash-equivalent input was found from this strategy within the "
            "Hypothesis budget. A saved crash may not be reproducible by the "
            "current strategy, or the crash may be outside the search budget."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(minimized, encoding="utf-8")
    print(f"minimized_reproducer: {args.output}")
    print(f"minimized_size_bytes: {len(minimized.encode('utf-8'))}")

    verified = verify_input(args.harness, args.output, args.timeout, args.verify_runs)
    print(f"minimized_crash_equivalent: {verified}")
    if not verified:
        raise SystemExit("Minimized input did not reproduce as crash-equivalent.")


if __name__ == "__main__":
    main()
