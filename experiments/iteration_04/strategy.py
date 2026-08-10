from hypothesis import strategies as st
import json
import string

# -----------------------------
# Basic safe text helpers
# -----------------------------
_safe_codepoint_text = st.text(min_size=0, max_size=64).filter(
    lambda s: '\x00' not in s and all(ord(c) >= 0x20 for c in s)
)

# Stress text allows larger content including non-ascii
_stress_text = st.text(min_size=0, max_size=8192)

# short key text for object keys (no embedded NULs, prefer printable)
_key_text = st.text(min_size=0, max_size=30).filter(
    lambda s: '\x00' not in s and all(ord(c) >= 0x20 for c in s)
)

# identifier-like keys for malformed unquoted-keys probe
_unquoted_key_text = st.text(min_size=1, max_size=12, alphabet=string.ascii_letters)

# -----------------------------
# Number strategies (produce JSON numeric text)
# -----------------------------
@st.composite
def _valid_number_text(draw):
    # Build a number string consistent with JSON NUMBER production,
    # avoiding zero-with-exponent forms like "0E1" and keeping exponents within [-250,250].
    is_negative = draw(st.booleans())
    kind = draw(st.sampled_from(["int", "frac", "exp"]))
    # integer part: "0" or non-zero-leading
    if draw(st.booleans()):
        int_part = "0"
    else:
        first = draw(st.sampled_from(list("123456789")))
        rest = draw(st.text(alphabet=string.digits, min_size=0, max_size=8))
        int_part = first + rest

    frac_part = ""
    if kind == "frac":
        frac_digits = draw(st.text(alphabet=string.digits, min_size=1, max_size=14))
        frac_part = "." + frac_digits

    exp_part = ""
    if kind == "exp":
        # avoid exponent when mantissa is exactly zero (i.e., "0" with no fraction)
        if not (int_part == "0" and frac_part == ""):
            exp_sign = draw(st.sampled_from(["", "+", "-"]))
            exp_val = draw(st.integers(min_value=0, max_value=250))
            # use lowercase 'e' to be consistent and avoid Parson-specific zero-with-exponent issues
            exp_part = "e" + (exp_sign if exp_sign != "" else "") + str(exp_val)

    s = ("-" if is_negative else "") + int_part + frac_part + exp_part
    return s

@st.composite
def _stress_number_text(draw):
    # Produce stressy numeric forms: very large ints, many fractional digits, exponents at bounds.
    kind = draw(st.integers(min_value=0, max_value=4))
    if kind == 0:
        # very large positive integer
        n = draw(st.integers(min_value=10**8, max_value=10**60))
        return str(n)
    if kind == 1:
        # very large negative integer
        n = draw(st.integers(min_value=-(10**60), max_value=-(10**6)))
        return str(n)
    if kind == 2:
        # many fractional digits
        whole = draw(st.integers(min_value=0, max_value=10**6))
        frac = draw(st.text(alphabet=string.digits, min_size=50, max_size=1000))
        return f"{whole}.{frac}"
    if kind == 3:
        # exponent forms but avoid zero-with-exponent by ensuring mantissa != 0
        mantissa = draw(st.integers(min_value=1, max_value=10**18))
        exp = draw(st.integers(min_value=-250, max_value=250))
        sign = "-" if draw(st.booleans()) else ""
        return f"{sign}{mantissa}e{exp}"
    # kind == 4: many leading fractional zeros then a digit
    whole = draw(st.integers(min_value=0, max_value=1000000))
    zeros = "0" * draw(st.integers(min_value=200, max_value=2000))
    return f"{whole}.{zeros}1"

# -----------------------------
# String strategies (produce JSON-quoted strings via json.dumps)
# -----------------------------
_valid_string_json = _safe_codepoint_text.map(lambda s: json.dumps(s, ensure_ascii=True))
_stress_string_json = st.one_of(
    # long non-ascii content that may produce many Unicode characters
    _stress_text.map(lambda s: json.dumps(s, ensure_ascii=False)),
    # many escapes by repeating backslashes/quotes
    st.builds(lambda n: json.dumps("\\" * n + '"' * (n % 10), ensure_ascii=True), st.integers(min_value=0, max_value=2000)),
    # sequences that include characters that json.dumps will turn into \uXXXX escapes
    st.text(min_size=0, max_size=1024).map(lambda s: json.dumps(s, ensure_ascii=True)),
)

# -----------------------------
# Primitive JSON text strategies
# -----------------------------
_valid_primitive_json = st.one_of(
    st.just("null"),
    st.just("true"),
    st.just("false"),
    _valid_number_text(),
    _valid_string_json,
)

_stress_primitive_json = st.one_of(
    st.just("null"),
    st.just("true"),
    st.just("false"),
    _stress_number_text(),
    _stress_string_json,
)

# -----------------------------
# Object and Array factories
# -----------------------------
def _object_strategy(children: st.SearchStrategy, max_keys: int = 6, allow_duplicate_keys: bool = False):
    @st.composite
    def _obj(draw):
        # For valid branches enforce unique keys; allow_duplicate_keys used only for malformed generator
        if allow_duplicate_keys:
            # produce at least one duplicated key
            if draw(st.booleans()):
                k = draw(_key_text.filter(lambda s: s != ""))  # non-empty to make duplicates visible
                # produce two entries with same key among possibly other unique keys
                extra = draw(st.lists(_key_text.filter(lambda s: s != k), min_size=0, max_size=max_keys - 2, unique=True))
                keys = [k] + extra + [k]
            else:
                keys = draw(st.lists(_key_text, min_size=1, max_size=max_keys))
        else:
            keys = draw(st.lists(_key_text, unique=True, min_size=0, max_size=max_keys))
        vals = [draw(children) for _ in keys]
        if not keys:
            return "{}"
        pairs = [f"{json.dumps(k, ensure_ascii=True)}:{v}" for k, v in zip(keys, vals)]
        return "{" + ",".join(pairs) + "}"
    return _obj()

def _array_strategy(children: st.SearchStrategy, max_elems: int = 6):
    @st.composite
    def _arr(draw):
        items = draw(st.lists(children, min_size=0, max_size=max_elems))
        return "[" + ",".join(items) + "]"
    return _arr()

# -----------------------------
# Valid recursive JSON (~75% of generated)
# -----------------------------
_valid_recursive_json = st.recursive(
    _valid_primitive_json,
    lambda children: st.one_of(
        _array_strategy(children, max_elems=6),
        _object_strategy(children, max_keys=6, allow_duplicate_keys=False),
    ),
    max_leaves=800,
)

# -----------------------------
# Stress-valid recursive JSON (~15%)
# -----------------------------
_stress_recursive_json = st.recursive(
    _stress_primitive_json,
    lambda children: st.one_of(
        # very deep/nested and very wide structures for stress testing
        _array_strategy(children, max_elems=300),
        _object_strategy(children, max_keys=300, allow_duplicate_keys=False),
    ),
    max_leaves=2000,
)

# -----------------------------
# Malformed (near-valid) probes (rare, explicit)
# -----------------------------
@st.composite
def _trailing_comma_array(draw):
    items = draw(st.lists(_valid_primitive_json, min_size=1, max_size=6))
    return "[" + ",".join(items) + ",]"

@st.composite
def _trailing_comma_object(draw):
    ks = draw(st.lists(_key_text, unique=True, min_size=1, max_size=6))
    vals = [draw(_valid_primitive_json) for _ in ks]
    pairs = [f'{json.dumps(k, ensure_ascii=True)}:{v}' for k, v in zip(ks, vals)]
    return "{" + ",".join(pairs) + ",}"

@st.composite
def _single_quoted_string(draw):
    s = draw(st.text(min_size=0, max_size=400))
    dumped = json.dumps(s, ensure_ascii=True)
    if len(dumped) >= 2 and dumped[0] == '"' and dumped[-1] == '"':
        inner = dumped[1:-1]
        return "'" + inner + "'"
    return "'" + s + "'"

@st.composite
def _invalid_unicode_escape(draw):
    s = draw(st.text(min_size=0, max_size=40))
    base = json.dumps(s, ensure_ascii=False)
    if len(base) >= 2 and base[0] == '"' and base[-1] == '"':
        # inject a malformed \u escape just before the closing quote
        return base[:-1] + "\\uZZZZ" + base[-1]
    return '"' + s + "\\uZZZZ" + '"'

@st.composite
def _zero_exponent_forms(draw):
    # explicit near-valid probes that should be malformed for this campaign
    choice = draw(st.sampled_from(["0E1", "-0E-1", "0e+5", "0E+10", "-0E1"]))
    return choice

@st.composite
def _duplicate_keys_object(draw):
    # produce an object with explicit duplicate keys (malformed probe)
    k = draw(_key_text.filter(lambda s: s != ""))  # visible non-empty key
    v1 = draw(_valid_primitive_json)
    v2 = draw(_valid_primitive_json)
    # order matters: duplicate adjacent
    return "{" + f'{json.dumps(k, ensure_ascii=True)}:{v1},{json.dumps(k, ensure_ascii=True)}:{v2}' + "}"

@st.composite
def _missing_closing_brace(draw):
    ks = draw(st.lists(_key_text, unique=True, min_size=1, max_size=4))
    vals = [draw(_valid_primitive_json) for _ in ks]
    pairs = [f'{json.dumps(k, ensure_ascii=True)}:{v}' for k, v in zip(ks, vals)]
    return "{" + ",".join(pairs)  # missing closing brace

@st.composite
def _unquoted_keys(draw):
    # produce simple unquoted identifier as key
    k = draw(_unquoted_key_text)
    v = draw(_valid_primitive_json)
    return "{" + f"{k}:{v}" + "}"

@st.composite
def _leading_zero_integer(draw):
    # create integers with illegal leading zeros (e.g., 0123)
    num = draw(st.integers(min_value=0, max_value=9999))
    width = draw(st.integers(min_value=2, max_value=6))
    s = str(num).rjust(width, "0")
    return s

_malformed_json = st.one_of(
    _trailing_comma_array(),
    _trailing_comma_object(),
    _single_quoted_string(),
    _invalid_unicode_escape(),
    _zero_exponent_forms(),
    _duplicate_keys_object(),
    _missing_closing_brace(),
    _unquoted_keys(),
    _leading_zero_integer(),
)

# -----------------------------
# Top-level weighted mix:
# ~75% valid recursive, ~15% stress valid, <=10% malformed
# -----------------------------
def _choose_branch(n: int):
    if n <= 75:
        return _valid_recursive_json
    if n <= 90:
        return _stress_recursive_json
    return _malformed_json

json_strategy = st.integers(min_value=1, max_value=100).flatmap(lambda n: _choose_branch(n))
