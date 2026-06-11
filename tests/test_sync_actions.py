import json
import os
from unittest import mock

import pytest
from keboola.component.sync_actions import MessageType


def _params(**over):
    p = {
        "base_url": "http://x",
        "username": "u",
        "#password": "p",
        "database": "DB",
        "browse": "MY_BROWSE",
        "load_type": "full_load",
        "columns": [],
    }
    p.update(over)
    return p


def _make_component(tmp_path, params):
    (tmp_path / "config.json").write_text(json.dumps({"parameters": params}))
    os.makedirs(tmp_path / "out" / "tables", exist_ok=True)
    os.environ["KBC_DATADIR"] = str(tmp_path)
    from component import Component

    return Component()


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------


def test_connection_success(tmp_path, monkeypatch):
    monkeypatch.setenv("KBC_DATADIR", str(tmp_path))
    c = _make_component(tmp_path, _params())
    fake = mock.Mock()
    fake.licenses = {"licenseSystemAPI": True, "licenseReportAPI": False}
    with mock.patch("component.HeliosInuvioClient", return_value=fake):
        result = c.test_connection()
    assert result.type == MessageType.SUCCESS
    assert "System" in result.message
    assert "Connection successful" in result.message


# ---------------------------------------------------------------------------
# list_browses
# ---------------------------------------------------------------------------

BROWSE_FULL = {
    "browseIdent": "BROWSE_A",
    "browseCaption": "Browse A",
    "browseTable": "TBL_A",
    "browseReadImplemented": True,
    "browseUserRightRead": True,
    "browseLisenced": True,
}
BROWSE_NO_LICENCE = {
    "browseIdent": "BROWSE_B",
    "browseCaption": "Browse B",
    "browseTable": "TBL_B",
    "browseReadImplemented": True,
    "browseUserRightRead": True,
    "browseLisenced": False,
}


def test_list_browses_filters_correctly(tmp_path, monkeypatch):
    monkeypatch.setenv("KBC_DATADIR", str(tmp_path))
    c = _make_component(tmp_path, _params())
    fake = mock.Mock()
    fake.list_browses.return_value = [BROWSE_FULL, BROWSE_NO_LICENCE]
    with mock.patch("component.HeliosInuvioClient", return_value=fake):
        result = c.list_browses()
    values = [el.value for el in result]
    assert values == ["Browse A (BROWSE_A)"]
    assert not any("BROWSE_B" in v for v in values)


# ---------------------------------------------------------------------------
# list_columns
# ---------------------------------------------------------------------------

BROWSE_META = {
    "table": {
        "tableFields": [
            {"fieldSysName": "T.ID", "fieldDisplayName": "ID"},
            {"fieldSysName": "T.Name", "fieldDisplayName": "Name"},
        ]
    }
}


def test_list_columns_maps_fields_to_select_elements(tmp_path, monkeypatch):
    monkeypatch.setenv("KBC_DATADIR", str(tmp_path))
    c = _make_component(tmp_path, _params(browse="MY_BROWSE"))
    fake = mock.Mock()
    fake.get_browse_meta.return_value = BROWSE_META
    with mock.patch("component.HeliosInuvioClient", return_value=fake):
        result = c.list_columns()
    assert result[0].value == "T.ID"
    assert len(result) == 2
    fake.get_browse_meta.assert_called_once_with("MY_BROWSE")


def test_list_columns_parses_ident_from_caption_value(tmp_path, monkeypatch):
    # browse saved as "Caption (ident)" — list_columns must call the API with just the ident.
    monkeypatch.setenv("KBC_DATADIR", str(tmp_path))
    c = _make_component(tmp_path, _params(browse="Orders (confirmed) [myCompany] {2026} (102)"))
    fake = mock.Mock()
    fake.get_browse_meta.return_value = BROWSE_META
    with mock.patch("component.HeliosInuvioClient", return_value=fake):
        c.list_columns()
    fake.get_browse_meta.assert_called_once_with("102")


def test_list_columns_raises_when_no_browse(tmp_path, monkeypatch):
    # @sync_action wraps UserException and calls exit(1), so the outer boundary is SystemExit.
    monkeypatch.setenv("KBC_DATADIR", str(tmp_path))
    c = _make_component(tmp_path, _params(browse=""))
    with mock.patch("component.HeliosInuvioClient"):
        with pytest.raises(SystemExit):
            c.list_columns()
