import subprocess
import warnings
from pathlib import Path

from hypothesis import strategies as st
from hypothesis.errors import NonInteractiveExampleWarning


# Suppress warning caused by using .example()
warnings.filterwarnings(
    "ignore",
    category=NonInteractiveExampleWarning
)


NUM_TESTS = 100
TIMEOUT = 5

INPUT_DIR = Path("experiments/baseline")
CRASH_DIR = Path("crashes/baseline")
LOG_FILE = Path("logs/baseline.log")
HARNESS = Path("harness/harness")


def run_harness(input_file: Path):

    try:
        result = subprocess.run(
            [str(HARNESS), str(input_file)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )

        return result, False

    except subprocess.TimeoutExpired as e:
        return e, True


def main():

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    CRASH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    log_lines = []

    valid_count = 0
    invalid_count = 0
    crash_count = 0
    timeout_count = 0

    print(f"Generating {NUM_TESTS} baseline test cases...\n")

    for i in range(1, NUM_TESTS + 1):

        # Baseline: completely arbitrary text
        value = st.text().example()

        input_file = INPUT_DIR / f"input_{i:04d}.txt"

        input_file.write_text(
            value,
            encoding="utf-8",
            errors="surrogatepass"
        )

        result, timed_out = run_harness(input_file)

        # -----------------------------
        # Determine result
        # -----------------------------

        if timed_out:

            status = "TIMEOUT"
            output = ""
            error = "Harness execution timed out."

            timeout_count += 1

        else:

            output = result.stdout.strip()
            error = result.stderr.strip()

            if result.returncode != 0:

                status = "CRASH"
                crash_count += 1

            elif output == "VALID JSON":

                status = "VALID"
                valid_count += 1

            elif output == "INVALID JSON":

                status = "INVALID"
                invalid_count += 1

            else:

                status = "UNKNOWN"

        # -----------------------------
        # Save log entry
        # -----------------------------

        log_entry = (
            f"Input: {input_file}\n"
            f"Status: {status}\n"
            f"Exit code: "
            f"{'TIMEOUT' if timed_out else result.returncode}\n"
            f"Stdout: {output}\n"
            f"Stderr: {error}\n"
            f"{'-' * 70}\n"
        )

        log_lines.append(log_entry)

        print(
            f"[{i:04d}/{NUM_TESTS}] {status}"
        )

        # -----------------------------
        # Save crashes / timeouts
        # -----------------------------

        if status in ("CRASH", "TIMEOUT"):

            crash_file = CRASH_DIR / input_file.name

            crash_file.write_text(
                value,
                encoding="utf-8",
                errors="surrogatepass"
            )

            print(
                f"  !!! {status} saved: {crash_file}"
            )

    # -----------------------------
    # Save complete log
    # -----------------------------

    LOG_FILE.write_text(
        "\n".join(log_lines),
        encoding="utf-8",
        errors="surrogatepass"
    )

    # -----------------------------
    # Final summary
    # -----------------------------

    print("\n" + "=" * 50)
    print("BASELINE FUZZING SUMMARY")
    print("=" * 50)

    print(f"Total tests : {NUM_TESTS}")
    print(f"Valid       : {valid_count}")
    print(f"Invalid     : {invalid_count}")
    print(f"Crashes     : {crash_count}")
    print(f"Timeouts    : {timeout_count}")

    print("=" * 50)
    print(f"Inputs  : {INPUT_DIR}")
    print(f"Crashes : {CRASH_DIR}")
    print(f"Log     : {LOG_FILE}")
    print("=" * 50)


if __name__ == "__main__":
    main()