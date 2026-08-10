import importlib.util
import argparse
import subprocess
import warnings
from pathlib import Path

from hypothesis.errors import HypothesisWarning, NonInteractiveExampleWarning


# ============================================================
# Configuration
# ============================================================

HARNESS = Path("harness/harness")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run one bounded fuzzing iteration against the Parson harness."
    )
    parser.add_argument(
        "--iteration",
        type=int,
        required=True,
        help="Iteration number, e.g. 2 for experiments/iteration_02.",
    )
    parser.add_argument(
        "--tests",
        type=int,
        default=500,
        help="Number of generated inputs to run. Assignment cap is 500.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="Per-input timeout in seconds.",
    )
    return parser.parse_args()


# Suppress warning caused by using strategy.example()
warnings.filterwarnings(
    "ignore",
    category=NonInteractiveExampleWarning,
)
warnings.filterwarnings(
    "ignore",
    category=HypothesisWarning,
)


# ============================================================
# Load Hypothesis Strategy
# ============================================================

def load_strategy(strategy_file):
    spec = importlib.util.spec_from_file_location(
        "iteration_strategy",
        strategy_file,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Could not load strategy from {strategy_file}"
        )

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    if not hasattr(module, "json_strategy"):
        raise AttributeError(
            f"{strategy_file} does not contain "
            f"'json_strategy'"
        )

    return module.json_strategy


# ============================================================
# Run Harness
# ============================================================

def run_harness(input_file, timeout):
    try:
        result = subprocess.run(
            [
                str(HARNESS),
                str(input_file),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return result, False

    except subprocess.TimeoutExpired as error:
        return error, True


# ============================================================
# Main Fuzzing Loop
# ============================================================

def main():
    args = parse_args()

    strategy_file = Path(
        f"experiments/iteration_{args.iteration:02d}/strategy.py"
    )
    input_dir = Path(
        f"experiments/iteration_{args.iteration:02d}/inputs"
    )
    crash_dir = Path(
        f"experiments/iteration_{args.iteration:02d}/crashes"
    )
    log_file = Path(
        f"experiments/iteration_{args.iteration:02d}/results.log"
    )

    # --------------------------------------------------------
    # Create directories
    # --------------------------------------------------------

    input_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    crash_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Load strategy
    # --------------------------------------------------------

    print("=" * 50)
    print(f"AGENTIC FUZZING - ITERATION {args.iteration}")
    print("=" * 50)

    print(f"Strategy : {strategy_file}")
    print(f"Harness  : {HARNESS}")
    print(f"Tests    : {args.tests}")
    print(f"Timeout  : {args.timeout}s")
    print()

    strategy = load_strategy(strategy_file)

    # --------------------------------------------------------
    # Counters
    # --------------------------------------------------------

    valid = 0
    invalid = 0
    crashes = 0
    timeouts = 0
    unknown = 0

    logs = []

    print(
        f"Generating {args.tests} test cases...\n"
    )

    # --------------------------------------------------------
    # Generate and test inputs
    # --------------------------------------------------------

    for i in range(1, args.tests + 1):

        try:

            # Generate JSON using the refined
            # LLM-generated Hypothesis strategy
            value = strategy.example()

        except Exception as error:

            print(
                f"[{i:04d}/{args.tests}] "
                f"GENERATION ERROR"
            )

            logs.append(
                f"Input: generation_failed_{i:04d}\n"
                f"Status: GENERATION_ERROR\n"
                f"Error: {error}\n"
                f"{'-' * 70}\n"
            )

            unknown += 1
            continue

        # ----------------------------------------------------
        # Save generated input
        # ----------------------------------------------------

        input_file = (
            input_dir /
            f"input_{i:04d}.json"
        )

        input_file.write_text(
            value,
            encoding="utf-8",
        )

        # ----------------------------------------------------
        # Run target harness
        # ----------------------------------------------------

        result, timed_out = run_harness(
            input_file,
            args.timeout,
        )

        # ----------------------------------------------------
        # Determine result
        # ----------------------------------------------------

        if timed_out:

            status = "TIMEOUT"

            timeouts += 1

            output = ""
            error = (
                "Harness execution "
                "timed out."
            )

            exit_code = "TIMEOUT"

        else:

            output = (
                result.stdout.strip()
            )

            error = (
                result.stderr.strip()
            )

            exit_code = result.returncode

            # Non-zero exit code means crash
            sanitizer_error = any(
                marker in error
                for marker in (
                    "AddressSanitizer",
                    "UndefinedBehaviorSanitizer",
                    "runtime error:",
                )
            )
            if result.returncode != 0 or sanitizer_error:
                status = "CRASH"
                crashes += 1
           

            elif output == "VALID JSON":

                status = "VALID"

                valid += 1

            elif output == "INVALID JSON":

                status = "INVALID"

                invalid += 1

            else:

                status = "UNKNOWN"

                unknown += 1

        # ----------------------------------------------------
        # Save log
        # ----------------------------------------------------

        log_entry = (
            f"Input: {input_file}\n"
            f"Status: {status}\n"
            f"Exit code: {exit_code}\n"
            f"Stdout: {output}\n"
            f"Stderr: {error}\n"
            f"{'-' * 70}\n"
        )

        logs.append(log_entry)

        # ----------------------------------------------------
        # Print progress
        # ----------------------------------------------------

        print(
            f"[{i:04d}/{args.tests}] "
            f"{status}"
        )

        # ----------------------------------------------------
        # Save crashes and timeouts
        # ----------------------------------------------------

        if status in ("CRASH", "TIMEOUT"):

            crash_file = crash_dir / input_file.name

            crash_file.write_text(
                value,
                encoding="utf-8",
            )

            print(
                f"    !!! Saved: "
                f"{crash_file}"
            )

    # ========================================================
    # Save complete log
    # ========================================================

    log_file.write_text(
        "\n".join(logs),
        encoding="utf-8",
    )

    # ========================================================
    # Summary
    # ========================================================

    print()
    print("=" * 50)
    print(
        f"ITERATION {args.iteration} SUMMARY"
    )
    print("=" * 50)

    print(
        f"Total     : {args.tests}"
    )

    print(
        f"Valid     : {valid}"
    )

    print(
        f"Invalid   : {invalid}"
    )

    print(
        f"Crashes   : {crashes}"
    )

    print(
        f"Timeouts  : {timeouts}"
    )

    print(
        f"Unknown   : {unknown}"
    )

    print("=" * 50)

    print(
        f"Inputs    : {input_dir}"
    )

    print(
        f"Crashes   : {crash_dir}"
    )

    print(
        f"Log       : {log_file}"
    )

    print("=" * 50)


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    main()
