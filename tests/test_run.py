import csv
import json
import os
from unittest import mock

import pytest
from keboola.component.exceptions import UserException

_FAKE_FIELDS = [
    {"fieldSysName": "T.ID", "fieldType": "integer", "fieldFormat": "int32", "fieldNullable": False},
    {"fieldSysName": "T.Name", "fieldType": "string", "fieldFormat": "", "fieldNullable": True},
]


def _params(**over):
    p = {
        "base_url": "http://x",
        "username": "u",
        "#password": "p",
        "database": "DB",
        "browse": "1",
        "load_type": "full_load",
        "columns": ["T.ID", "T.Name"],
    }
    p.update(over)
    return p


def _make_component(tmp_path, params, state=None):
    (tmp_path / "config.json").write_text(json.dumps({"parameters": params}))
    os.makedirs(tmp_path / "out" / "tables", exist_ok=True)
    if state is not None:
        os.makedirs(tmp_path / "in", exist_ok=True)
        (tmp_path / "in" / "state.json").write_text(json.dumps(state))
    os.environ["KBC_DATADIR"] = str(tmp_path)
    from component import Component

    return Component()


def test_run_full_load_writes_table_and_no_incremental_state(tmp_path, monkeypatch):
    monkeypatch.setenv("KBC_DATADIR", str(tmp_path))
    c = _make_component(tmp_path, _params())
    fake = mock.Mock()
    fake.get_browse_fields.return_value = _FAKE_FIELDS
    fake.iter_browse_rows.return_value = iter([{"T.ID": 1, "T.Name": "A"}])
    fake.last_row_version_max = "0000000000000010"
    with mock.patch("component.HeliosInuvioClient", return_value=fake):
        c.run()
    out = tmp_path / "out" / "tables" / "browse_1.csv"
    rows = list(csv.DictReader(out.open()))
    assert rows == [{"T_ID": "1", "T_Name": "A"}]
    assert out.read_text(encoding="utf-8").startswith("T_ID")
    manifest = json.loads((tmp_path / "out" / "tables" / "browse_1.csv.manifest").read_text())
    assert manifest["has_header"] is True
    schema = {col["name"]: col for col in manifest["schema"]}
    assert schema["T_ID"]["data_type"]["base"]["type"] == "INTEGER"
    assert "nullable" not in schema["T_ID"]  # nullable=False is omitted from manifest
    assert schema["T_Name"]["data_type"]["base"]["type"] == "STRING"
    assert schema["T_Name"].get("nullable") is True
    # With no PK, ordering falls back to the first selected (raw) column.
    assert fake.iter_browse_rows.call_args.kwargs["order_by"] == ["T.ID"]


def test_run_incremental_requires_primary_key(tmp_path, monkeypatch):
    monkeypatch.setenv("KBC_DATADIR", str(tmp_path))
    c = _make_component(tmp_path, _params(load_type="incremental_load", primary_key=[]))
    with mock.patch("component.HeliosInuvioClient"):
        with pytest.raises(UserException, match="primary key"):
            c.run()


def test_run_incremental_reads_and_writes_watermark(tmp_path, monkeypatch):
    monkeypatch.setenv("KBC_DATADIR", str(tmp_path))
    c = _make_component(
        tmp_path, _params(load_type="incremental_load", primary_key=["T.ID"]), state={"row_version": "0000000000000005"}
    )
    fake = mock.Mock()
    fake.get_browse_fields.return_value = _FAKE_FIELDS
    fake.iter_browse_rows.return_value = iter([{"T.ID": 2, "T.Name": "B"}])
    fake.last_row_version_max = "0000000000000020"
    with mock.patch("component.HeliosInuvioClient", return_value=fake):
        c.run()
    assert fake.iter_browse_rows.call_args.kwargs["row_version"] == "0000000000000005"
    # The user-defined primary key (raw fieldSysName) drives deterministic ordering.
    assert fake.iter_browse_rows.call_args.kwargs["order_by"] == ["T.ID"]
    state = json.loads((tmp_path / "out" / "state.json").read_text())
    assert state["row_version"] == "0000000000000020"
    # Primary key column must be flagged in schema; non-PK column must not be.
    manifest = json.loads((tmp_path / "out" / "tables" / "browse_1.csv.manifest").read_text())
    schema = {col["name"]: col for col in manifest["schema"]}
    assert schema["T_ID"].get("primary_key") is True
    assert "primary_key" not in schema["T_Name"]
