from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FRAME_RE = re.compile(
    r"^\s*#\d+\s+(?:0x[0-9a-fA-F]+\s+)?(?:in\s+)?"
    r"(?P<func>[A-Za-z_.$:<>{}~][A-Za-z0-9_.$:<>{}~@/-]*)"
)
LOG_ENTRY_SEPARATOR = "-" * 70


@dataclass
class CrashCase:
    input_path: str
    status: str
    stderr: str
    exit_code: str
    metadata: dict[str, Any]
    source: str


def normalize_function(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"\.cold(?:\.\d+)?$", "", name)
    name = re.sub(r"\.isra\.\d+$", "", name)
    name = re.sub(r"\.constprop\.\d+$", "", name)
    return name


def stack_frames(stderr: str, limit: int) -> list[str]:
    frames: list[str] = []

    for line in stderr.splitlines():
        match = FRAME_RE.match(line)
        if not match:
            continue
        frames.append(normalize_function(match.group("func")))
        if len(frames) >= limit:
            break

    return frames


def fallback_key(case: CrashCase) -> list[str]:
    first_error_line = ""
    for line in case.stderr.splitlines():
        stripped = line.strip()
        if stripped:
            first_error_line = stripped
            break

    if case.status == "TIMEOUT":
        return ["TIMEOUT", case.exit_code]

    return [
        case.status,
        case.exit_code,
        first_error_line[:160],
    ]


def signature_for(case: CrashCase, frame_limit: int) -> tuple[str, list[str]]:
    frames = stack_frames(case.stderr, frame_limit)
    normalized = frames if frames else fallback_key(case)
    digest = hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()[:12]
    return f"SIG-{digest}", normalized


def parse_metadata(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def parse_log_entry(entry: str, log_file: Path) -> CrashCase | None:
    fields: dict[str, str] = {}
    current_key: str | None = None
    current_value: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_value
        if current_key is not None:
            fields[current_key] = "\n".join(current_value).strip()
        current_key = None
        current_value = []

    for line in entry.splitlines():
        match = re.match(r"^(Input|Status|Exit code|Stdout|Stderr):\s*(.*)$", line)
        if match:
            flush()
            current_key = match.group(1)
            current_value = [match.group(2)]
        elif current_key is not None:
            current_value.append(line)
    flush()

    status = fields.get("Status", "")
    if status not in {"CRASH", "TIMEOUT"}:
        return None

    return CrashCase(
        input_path=fields.get("Input", ""),
        status=status,
        stderr=fields.get("Stderr", ""),
        exit_code=fields.get("Exit code", ""),
        metadata={},
        source=str(log_file),
    )


def cases_from_log(log_file: Path) -> list[CrashCase]:
    if not log_file.exists():
        return []

    text = log_file.read_text(encoding="utf-8", errors="replace")
    cases: list[CrashCase] = []
    for entry in text.split(LOG_ENTRY_SEPARATOR):
        case = parse_log_entry(entry, log_file)
        if case is not None:
            cases.append(case)
    return cases


def cases_from_crash_dir(crash_dir: Path) -> list[CrashCase]:
    cases: list[CrashCase] = []

    if not crash_dir.exists():
        return cases

    for child in sorted(crash_dir.iterdir()):
        if child.is_dir():
            stderr_path = child / "stderr.txt"
            metadata_path = child / "metadata.json"
            input_candidates = [
                child / "input.json",
                child / "input.txt",
                child / "input",
            ]
            input_path = next((path for path in input_candidates if path.exists()), child)
            metadata = parse_metadata(metadata_path)
            stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
            cases.append(
                CrashCase(
                    input_path=str(input_path),
                    status=str(metadata.get("status", "CRASH")),
                    stderr=stderr,
                    exit_code=str(metadata.get("exit_code", "")),
                    metadata=metadata,
                    source=str(child),
                )
            )

    return cases


def default_inputs() -> tuple[list[Path], list[Path]]:
    logs = sorted(Path("experiments").glob("iteration_*/results.log"))
    crash_dirs = sorted(Path("experiments").glob("iteration_*/crashes"))
    return logs, crash_dirs


def triage(cases: list[CrashCase], frame_limit: int) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    grouped_cases: dict[str, list[CrashCase]] = defaultdict(list)
    normalized_by_sig: dict[str, list[str]] = {}

    for case in cases:
        signature, normalized = signature_for(case, frame_limit)
        grouped_cases[signature].append(case)
        normalized_by_sig.setdefault(signature, normalized)

    for signature, signature_cases in sorted(grouped_cases.items()):
        groups[signature] = {
            "count": len(signature_cases),
            "normalized_frames_or_key": normalized_by_sig[signature],
            "cases": [
                {
                    "input": case.input_path,
                    "status": case.status,
                    "exit_code": case.exit_code,
                    "source": case.source,
                    "metadata": case.metadata,
                }
                for case in signature_cases
            ],
        }

    return {
        "total_crash_equivalent_cases": len(cases),
        "unique_signatures": len(groups),
        "groups": groups,
    }


def print_text_report(report: dict[str, Any]) -> None:
    print(f"total_crash_equivalent_cases: {report['total_crash_equivalent_cases']}")
    print(f"unique_signatures           : {report['unique_signatures']}")

    if not report["groups"]:
        print("groups                      : none")
        return

    for signature, group in report["groups"].items():
        print()
        print(signature)
        print("-" * len(signature))
        print(f"count: {group['count']}")
        print("normalized_frames_or_key:")
        for frame in group["normalized_frames_or_key"]:
            print(f"  - {frame}")
        print("cases:")
        for case in group["cases"]:
            print(f"  - input={case['input']} status={case['status']} source={case['source']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Deduplicate crash-equivalent fuzzing results by normalizing the "
            "top sanitizer stack frames and hashing them into signatures."
        )
    )
    parser.add_argument(
        "--logs",
        nargs="*",
        type=Path,
        help="results.log files to scan for CRASH/TIMEOUT entries.",
    )
    parser.add_argument(
        "--crash-dirs",
        nargs="*",
        type=Path,
        help="Crash directories containing case folders with stderr.txt and metadata.json.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=5,
        help="Number of top stack frames to normalize into the signature.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a text summary.",
    )
    args = parser.parse_args()

    logs, crash_dirs = default_inputs()
    if args.logs is not None:
        logs = args.logs
    if args.crash_dirs is not None:
        crash_dirs = args.crash_dirs

    cases: list[CrashCase] = []
    for log_file in logs:
        cases.extend(cases_from_log(log_file))
    for crash_dir in crash_dirs:
        cases.extend(cases_from_crash_dir(crash_dir))

    report = triage(cases, max(1, args.frames))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text_report(report)


if __name__ == "__main__":
    main()
