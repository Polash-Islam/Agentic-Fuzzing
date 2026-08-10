import json

from hypothesis import given, settings
from strategies.generated_strategy import json_strategy


@given(json_strategy)
@settings(max_examples=20)
def test_generated_json(value):

    print("\n" + "=" * 80)
    print("Generated JSON (raw):")
    print(value.encode("utf-8", "backslashreplace").decode("utf-8"))

    try:
        parsed = json.loads(value)

        print("\nParsed JSON:")
        pretty = json.dumps(
            parsed,
            indent=2,
            ensure_ascii=False,
        )

        print(pretty.encode("utf-8", "backslashreplace").decode("utf-8"))

        print("\nStatus: VALID JSON")

    except json.JSONDecodeError as e:
        print("\nStatus: INVALID JSON")
        print("Error:", e)

    print("=" * 80)