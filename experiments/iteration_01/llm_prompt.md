# Agentic Fuzzing Iteration 1

You are generating a Hypothesis strategy for fuzzing the Parson JSON parser.

Target:
- Library: Parson
- Format: JSON
- Harness entry point: json_parse_string
- Harness output classes: VALID, INVALID, CRASH, TIMEOUT

Budget:
- Iteration cap: 5
- Inputs per iteration: 500
- Per-input timeout: 5 seconds

Assignment requirements:
- Start from the JSON grammar.
- Use composable Hypothesis strategies.
- Use st.recursive or @st.composite for recursive productions.
- Cover empty arrays/objects, nesting, strings, escapes, Unicode, numbers,
  duplicate keys, extreme numeric values, and near-valid malformed inputs.
- Optimize using feedback: crashes/timeouts, parser rejection patterns,
  and structural diversity.

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

Return only Python code for experiments/iteration_01/strategy.py.
The file must define a top-level Hypothesis strategy named json_strategy.
Do not include markdown fences.

## JSON Grammar

```antlr
/** Taken from "The Definitive ANTLR 4 Reference" by Terence Parr */

// Derived from https://json.org

// $antlr-format alignTrailingComments true, columnLimit 150, minEmptyLines 1, maxEmptyLinesToKeep 1, reflowComments false, useTab false
// $antlr-format allowShortRulesOnASingleLine false, allowShortBlocksOnASingleLine true, alignSemicolons hanging, alignColons hanging

grammar JSON;

json
    : value EOF
    ;

obj
    : '{' pair (',' pair)* '}'
    | '{' '}'
    ;

pair
    : STRING ':' value
    ;

arr
    : '[' value (',' value)* ']'
    | '[' ']'
    ;

value
    : STRING
    | NUMBER
    | obj
    | arr
    | 'true'
    | 'false'
    | 'null'
    ;

STRING
    : '"' (ESC | SAFECODEPOINT)* '"'
    ;

fragment ESC
    : '\\' (["\\/bfnrt] | UNICODE)
    ;

fragment UNICODE
    : 'u' HEX HEX HEX HEX
    ;

fragment HEX
    : [0-9a-fA-F]
    ;

fragment SAFECODEPOINT
    : ~ ["\\\u0000-\u001F]
    ;

NUMBER
    : '-'? INT ('.' [0-9]+)? EXP?
    ;

fragment INT
    // integer part forbids leading 0s (e.g. `01`)
    : '0'
    | [1-9] [0-9]*
    ;

// no leading zeros

fragment EXP
    // exponent number permits leading 0s (e.g. `1e01`)
    : [Ee] [+-]? [0-9]+
    ;

WS
    : [ \t\n\r]+ -> skip
    ;

```

## Previous Strategy

```python
import json
import os
import subprocess

from hypothesis import given, settings
from hypothesis import strategies as st

# -----------------------------
# Output files
# -----------------------------
TEMP_FILE = "experiments/generated.json"
LOG_FILE = "logs/grammar.log"

os.makedirs("experiments", exist_ok=True)
os.makedirs("logs", exist_ok=True)


# -----------------------------
# Primitive JSON values
# -----------------------------
primitive = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=20),
)


# -----------------------------
# Recursive JSON strategy
# -----------------------------
json_strategy = st.recursive(
    primitive,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(
            st.text(max_size=10),
            children,
            max_size=5
        )
    ),
    max_leaves=20,
)


# -----------------------------
# Run Harness
# -----------------------------
@given(json_strategy)
@settings(max_examples=30)
def test_json(data):

    json_text = json.dumps(data)

    with open(TEMP_FILE, "w", encoding="utf-8") as f:
        f.write(json_text)

    result = subprocess.run(
        ["./harness/harness", TEMP_FILE],
        capture_output=True,
        text=True,
        timeout=5,
    )

    with open(LOG_FILE, "a", encoding="utf-8") as log:

        log.write("=" * 60 + "\n")

        log.write("INPUT:\n")
        log.write(json_text + "\n\n")

        log.write("STDOUT:\n")
        log.write(result.stdout)

        log.write("\nSTDERR:\n")
        log.write(result.stderr)

        log.write(f"\nEXIT CODE: {result.returncode}\n")


if __name__ == "__main__":
    test_json()
```

## Previous Feedback

```text
logs/baseline.log
======================================================================
total             : 100
valid             : 3
invalid           : 97
crash             : 0
timeout           : 0
unknown           : 0
generation_error  : 0
valid_rate        : 3.00%
crash_rate        : 0.00%
parsed_inputs     : 1
invalid causes
  syntax_invalid_for_python_json: 96
  parson_specific_rejection   : 1
structure coverage
  numbers                     : 1
  max_depth                   : 0
```
