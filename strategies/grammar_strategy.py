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