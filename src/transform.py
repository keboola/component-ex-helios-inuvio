import json
import re

_NON_SAFE = re.compile(r"[^A-Za-z0-9_]")


def sanitize_column(name: str) -> str:
    """Map a Helios fieldSysName like 'TabCisOrg.ID' to a Storage-safe column 'TabCisOrg_ID'."""
    return _NON_SAFE.sub("_", name)


def coerce_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def flatten_row(row: dict) -> dict:
    return {sanitize_column(k): coerce_value(v) for k, v in row.items()}
