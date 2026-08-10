from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any


STATUS_NAMES = (
    "VALID",
    "INVALID",
    "CRASH",
    "TIMEOUT",
    "UNKNOWN",
    "GENERATION_ERROR",
)

NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.+-])-?"
    r"(?:0|[1-9][0-9]*)"
    r"(?:\.[0-9]+)?"
    r"(?:[eE][+-]?[0-9]+)?"
)


def mask_strings(text: str) -> str:
    masked: list[str] = []
    in_string = False
    escaped = False

    for char in text:
        if in_string:
            masked.append(" ")
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
                masked.append(" ")
            else:
                masked.append(char)

    return "".join(masked)


def extract_input_paths(log_text: str, status: str | None = None) -> list[Path]:
    paths: list[Path] = []

    for entry in log_text.split("-" * 70):
        if status is not None and f"Status: {status}" not in entry:
            continue
        match = re.search(r"^Input:\s*(.+)$", entry, flags=re.MULTILINE)
        if match:
            paths.append(Path(match.group(1).strip()))

    return paths


def load_json_with_duplicate_tracking(text: str) -> tuple[Any, bool]:
    duplicate_key_seen = False

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        nonlocal duplicate_key_seen
        seen: set[str] = set()
        result: dict[str, Any] = {}

        for key, value in pairs:
            if key in seen:
                duplicate_key_seen = True
            seen.add(key)
            result[key] = value

        return result

    value = json.loads(text, object_pairs_hook=hook)
    return value, duplicate_key_seen


def walk_json(value: Any, depth: int = 0) -> Counter[str]:
    counts: Counter[str] = Counter()
    stack = [(value, depth)]

    while stack:
        current, current_depth = stack.pop()
        counts["max_depth"] = max(counts["max_depth"], current_depth)

        if isinstance(current, dict):
            counts["objects"] += 1
            counts["object_keys"] += len(current)
            for key, child in current.items():
                if "\x00" in key:
                    counts["nul_keys"] += 1
                stack.append((child, current_depth + 1))
        elif isinstance(current, list):
            counts["arrays"] += 1
            counts["array_items"] += len(current)
            for child in current:
                stack.append((child, current_depth + 1))
        elif isinstance(current, str):
            counts["strings"] += 1
            if "\x00" in current:
                counts["nul_string_values"] += 1
            if any(ord(char) > 0x7F for char in current):
                counts["unicode_strings"] += 1
        elif isinstance(current, bool):
            counts["booleans"] += 1
        elif current is None:
            counts["nulls"] += 1
        elif isinstance(current, (int, float)):
            counts["numbers"] += 1

    return counts


def number_issue_counts(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()

    for match in NUMBER_RE.finditer(mask_strings(text)):
        token = match.group(0)
        exponent_match = re.search(r"[eE]([+-]?[0-9]+)$", token)

        if re.match(r"-?0[eE]", token):
            counts["zero_with_exponent"] += 1

        try:
            value = float(token)
        except ValueError:
            continue

        if not math.isfinite(value):
            counts["number_overflow"] += 1
        elif exponent_match and int(exponent_match.group(1)) > 308:
            counts["number_overflow"] += 1

    return counts


def classify_invalid_input(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        counts["missing_input_file"] += 1
        return counts

    try:
        parsed, duplicate_key_seen = load_json_with_duplicate_tracking(text)
    except json.JSONDecodeError:
        counts["syntax_invalid_for_python_json"] += 1
        counts.update(number_issue_counts(text))
        return counts

    if duplicate_key_seen:
        counts["duplicate_key"] += 1

    structural = walk_json(parsed)
    if structural["nul_keys"]:
        counts["nul_in_key"] += 1
    if structural["nul_string_values"]:
        counts["nul_in_string_value"] += 1

    counts.update(number_issue_counts(text))

    if not counts:
        counts["parson_specific_rejection"] += 1

    return counts


def analyze_log(log_file: Path) -> dict[str, Any]:
    text = log_file.read_text(encoding="utf-8", errors="replace")
    total = len(re.findall(r"^Input:", text, flags=re.MULTILINE))
    statuses = {
        status.lower(): len(re.findall(rf"^Status: {status}\b", text, flags=re.MULTILINE))
        for status in STATUS_NAMES
    }

    invalid_causes: Counter[str] = Counter()
    for path in extract_input_paths(text, "INVALID"):
        invalid_causes.update(classify_invalid_input(path))

    structural: Counter[str] = Counter()
    parsed_inputs = 0
    for path in extract_input_paths(text):
        if not path.exists():
            continue
        try:
            parsed, duplicate_key_seen = load_json_with_duplicate_tracking(
                path.read_text(encoding="utf-8", errors="replace")
            )
        except json.JSONDecodeError:
            continue
        parsed_inputs += 1
        structural.update(walk_json(parsed))
        if duplicate_key_seen:
            structural["inputs_with_duplicate_keys"] += 1

    return {
        "log": str(log_file),
        "total": total,
        **statuses,
        "valid_rate": statuses["valid"] / total * 100 if total else 0.0,
        "crash_rate": statuses["crash"] / total * 100 if total else 0.0,
        "invalid_causes": invalid_causes,
        "parsed_inputs": parsed_inputs,
        "structural": structural,
    }


def print_counter(title: str, counter: Counter[str], limit: int = 12) -> None:
    print(title)
    if not counter:
        print("  none")
        return

    for key, value in counter.most_common(limit):
        print(f"  {key:28}: {value}")


def print_result(result: dict[str, Any]) -> None:
    print(f"\n{result['log']}")
    print("=" * 70)
    print(f"{'total':18}: {result['total']}")

    for status in STATUS_NAMES:
        print(f"{status.lower():18}: {result[status.lower()]}")

    print(f"{'valid_rate':18}: {result['valid_rate']:.2f}%")
    print(f"{'crash_rate':18}: {result['crash_rate']:.2f}%")
    print(f"{'parsed_inputs':18}: {result['parsed_inputs']}")
    print_counter("invalid causes", result["invalid_causes"])
    print_counter("structure coverage", result["structural"])


def default_logs() -> list[Path]:
    candidates = [
        Path("logs/baseline.log"),
        *sorted(Path("experiments").glob("iteration_*/results.log")),
    ]
    return [path for path in candidates if path.exists()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze fuzzing logs and classify Parson JSON rejections."
    )
    parser.add_argument(
        "logs",
        nargs="*",
        type=Path,
        help="Log files to analyze. Defaults to baseline plus discovered iterations.",
    )
    args = parser.parse_args()

    logs = args.logs or default_logs()
    if not logs:
        raise SystemExit("No log files found.")

    for log in logs:
        print_result(analyze_log(log))


if __name__ == "__main__":
    main()
