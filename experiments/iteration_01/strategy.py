from hypothesis import strategies as st
import json
import string

# -----------------------------
# Safe text helpers for valid branch
# -----------------------------
# Exclude NUL and C0 controls (U+0000..U+001F)
_safe_text = st.text(min_size=0, max_size=16).filter(
    lambda s: '\x00' not in s and all(ord(c) >= 0x20 for c in s)
)

# Stress text (allows larger sizes and broader content)
_stress_text = st.text(min_size=0, max_size=1024)

# -----------------------------
# Number strategies (produce JSON numeric text)
# -----------------------------
@st.composite
def _valid_number_text(draw):
    # INT: either '0' or non-zero first digit then digits
    is_negative = draw(st.booleans())
    kind = draw(st.sampled_from(["int", "frac", "frac_leading_nonzero"]))
    if kind == "int":
        # either zero or non-zero-leading integer
        is_zero = draw(st.booleans())
        if is_zero:
            int_part = "0"
        else:
            first = draw(st.sampled_from(list("123456789")))
            rest = draw(st.text(alphabet=string.digits, min_size=0, max_size=6))
            int_part = first + rest
        frac = None
    else:
        # fractional: integer part per INT (no leading zeros unless zero) plus fractional digits
        first = draw(st.sampled_from(list("0123456789")))
        if first == "0":
            # start with 0
            int_part = "0"
        else:
            rest = draw(st.text(alphabet=string.digits, min_size=0, max_size=6))
            int_part = first + rest
        frac_digits = draw(st.text(alphabet=string.digits, min_size=1, max_size=8))
        frac = frac_digits

    # exponent optional, but avoid applying exponent to a bare zero integer (e.g., "0E1" or "-0E-1")
    want_exp = draw(st.booleans())
    exp_part = ""
    if want_exp:
        # If the numeric text would be exactly "0" or "-0" with no fraction, disallow exponent
        if frac is None and int_part == "0":
            want_exp = False
        else:
            exp_sign = draw(st.sampled_from(["", "+", "-"]))
            exp_val = draw(st.integers(min_value=0, max_value=250))
            # Prefer lowercase 'e'
            exp_part = "e" + (exp_sign if exp_sign != "" else "") + str(exp_val)

    s = ("-" if is_negative else "") + int_part
    if frac is not None:
        s += "." + frac
    if exp_part:
        s += exp_part
    return s

@st.composite
def _stress_number_text(draw):
    kind = draw(st.integers(min_value=0, max_value=4))
    if kind == 0:
        # very large integer
        n = draw(st.integers(min_value=10**6, max_value=10**30))
        return str(n)
    if kind == 1:
        # negative large integer
        n = draw(st.integers(min_value=-(10**30), max_value=-10**6))
        return str(n)
    if kind == 2:
        # fractional with many digits
        whole = draw(st.integers(min_value=0, max_value=10**6))
        frac = draw(st.integers(min_value=1, max_value=10**8))
        return f"{whole}.{frac}"
    if kind == 3:
        # exponent forms but within bounds; avoid 0E* forms by ensuring mantissa != 0
        mantissa = draw(st.integers(min_value=1, max_value=10**12))
        exp = draw(st.integers(min_value=-250, max_value=250))
        # choose sign randomly
        sign = "-" if draw(st.booleans()) else ""
        # render using 'e'
        return f"{sign}{mantissa}e{exp}"
    # kind == 4: many leading zeros in fraction (stress)
    whole = draw(st.integers(min_value=0, max_value=1000))
    frac = "0" * draw(st.integers(min_value=10, max_value=200)) + "1"
    return f"{whole}.{frac}"

# -----------------------------
# String strategies (produce JSON-quoted strings via json.dumps)
# -----------------------------
_valid_string_json = _safe_text.map(lambda s: json.dumps(s, ensure_ascii=True))
_stress_string_json = st.one_of(
    _stress_text.map(lambda s: json.dumps(s, ensure_ascii=True)),
    st.builds(lambda n: json.dumps("\\" * n + '"' * (n % 5), ensure_ascii=True), st.integers(min_value=0, max_value=200)),
    st.builds(lambda s: json.dumps(s, ensure_ascii=True), st.text(min_size=0, max_size=200)),
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
# Object and Array factories (given children strategy -> produce composite strategy)
# -----------------------------
def _object_strategy(children: st.SearchStrategy, max_keys: int = 6):
    @st.composite
    def _obj(draw):
        # unique keys and no embedded NULs for valid branch; when used in stress branch,
        # children may still be stress strings which were created via json.dumps
        keys = draw(st.lists(_safe_text, unique=True, min_size=0, max_size=max_keys))
        vals = [draw(children) for _ in keys]
        if not keys:
            return "{}"
        pairs = []
        for k, v in zip(keys, vals):
            pairs.append(f"{json.dumps(k, ensure_ascii=True)}:{v}")
        return "{" + ",".join(pairs) + "}"
    return _obj()

def _array_strategy(children: st.SearchStrategy, max_elems: int = 6):
    @st.composite
    def _arr(draw):
        items = draw(st.lists(children, min_size=0, max_size=max_elems))
        return "[" + ",".join(items) + "]"
    return _arr()

# -----------------------------
# Valid recursive JSON (majority)
# -----------------------------
_valid_recursive_json = st.recursive(
    _valid_primitive_json,
    lambda children: st.one_of(
        _array_strategy(children, max_elems=5),
        _object_strategy(children, max_keys=5),
    ),
    max_leaves=60,
)

# -----------------------------
# Stress-valid recursive JSON (~15%)
# -----------------------------
_stress_recursive_json = st.recursive(
    _stress_primitive_json,
    lambda children: st.one_of(
        _array_strategy(children, max_elems=80),
        _object_strategy(children, max_keys=80),
    ),
    max_leaves=500,
)

# -----------------------------
# Malformed (near-valid) probes (rare, explicit)
# -----------------------------
@st.composite
def _trailing_comma_array(draw):
    items = draw(st.lists(_valid_primitive_json, min_size=1, max_size=5))
    return "[" + ",".join(items) + ",]"

@st.composite
def _trailing_comma_object(draw):
    ks = draw(st.lists(_safe_text, unique=True, min_size=1, max_size=5))
    vals = [draw(_valid_primitive_json) for _ in ks]
    pairs = [f'{json.dumps(k, ensure_ascii=True)}:{v}' for k, v in zip(ks, vals)]
    return "{" + ",".join(pairs) + ",}"

@st.composite
def _unquoted_keys(draw):
    k = draw(st.text(min_size=1, max_size=10, alphabet=string.ascii_letters))
    v = draw(_valid_primitive_json)
    return "{" + f"{k}:{v}" + "}"

@st.composite
def _single_quoted_string(draw):
    s = draw(st.text(min_size=0, max_size=50))
    dumped = json.dumps(s, ensure_ascii=True)
    # replace surrounding quotes with single quotes
    if dumped.startswith('"') and dumped.endswith('"'):
        inner = dumped[1:-1]
        return "'" + inner + "'"
    return "'" + s + "'"

@st.composite
def _invalid_unicode_escape(draw):
    s = draw(st.text(min_size=0, max_size=10))
    # insert an invalid unicode escape sequence inside a quoted string
    base = json.dumps(s, ensure_ascii=False)
    if len(base) >= 2 and base[0] == '"' and base[-1] == '"':
        return base[:-1] + "\\uZZZZ" + base[1:]
    return '"' + s + "\\uZZZZ" + '"'

@st.composite
def _zero_exponent_forms(draw):
    choice = draw(st.sampled_from([0, 1]))
    return "0E1" if choice == 0 else "-0E-1"

@st.composite
def _duplicate_keys_object(draw):
    k = draw(_safe_text)
    v1 = draw(_valid_primitive_json)
    v2 = draw(_valid_primitive_json)
    return "{" + f'{json.dumps(k, ensure_ascii=True)}:{v1},{json.dumps(k, ensure_ascii=True)}:{v2}' + "}"

@st.composite
def _missing_closing_brace(draw):
    ks = draw(st.lists(_safe_text, unique=True, min_size=1, max_size=3))
    vals = [draw(_valid_primitive_json) for _ in ks]
    pairs = [f'{json.dumps(k, ensure_ascii=True)}:{v}' for k, v in zip(ks, vals)]
    return "{" + ",".join(pairs)  # missing closing brace

_malformed_json = st.one_of(
    _trailing_comma_array(),
    _trailing_comma_object(),
    _unquoted_keys(),
    _single_quoted_string(),
    _invalid_unicode_escape(),
    _zero_exponent_forms(),
    _duplicate_keys_object(),
    _missing_closing_brace(),
)

# -----------------------------
# Top-level weighted mix:
# ~75% valid recursive, ~15% stress valid, <=10% malformed
# -----------------------------
def _chooser(n):
    if n <= 75:
        return _valid_recursive_json
    if n <= 90:
        return _stress_recursive_json
    return _malformed_json

json_strategy = st.integers(min_value=1, max_value=100).flatmap(lambda n: _chooser(n))
