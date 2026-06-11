from transform import coerce_value, flatten_row, sanitize_column


def test_sanitize_column_replaces_dot_and_specials():
    assert sanitize_column("TabCisOrg.ID") == "TabCisOrg_ID"
    assert sanitize_column("A.B C-D") == "A_B_C_D"


def test_coerce_value_serializes_containers():
    assert coerce_value(5) == 5
    assert coerce_value(None) is None
    assert coerce_value({"a": 1}) == '{"a": 1}'
    assert coerce_value([1, 2]) == "[1, 2]"


def test_flatten_row_sanitizes_keys_and_coerces_values():
    row = {"TabCisOrg.ID": 1, "TabCisOrg.Meta": {"x": 1}}
    assert flatten_row(row) == {"TabCisOrg_ID": 1, "TabCisOrg_Meta": '{"x": 1}'}
