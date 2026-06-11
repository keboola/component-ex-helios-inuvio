from unittest import mock

import pytest
import requests
from keboola.component.exceptions import UserException

from client import HeliosInuvioClient


def _client():
    return HeliosInuvioClient("http://localhost:8080", "u", "p", "DB")


def _resp(status, json_body=None, text=""):
    r = mock.Mock(spec=requests.Response)
    r.status_code = status
    r.json.return_value = json_body if json_body is not None else {}
    r.text = text
    return r


def test_authenticate_sets_bearer_and_licenses():
    c = _client()
    with mock.patch.object(c._session, "post", return_value=_resp(200, {"token": "JWT", "licenseSystemAPI": True})):
        c.authenticate()
    assert c._token == "JWT"
    assert c.licenses == {"licenseSystemAPI": True}
    assert c._session.headers["Authorization"] == "Bearer JWT"


def test_authenticate_failure_raises_userexception_with_server_message():
    c = _client()
    body = {"errors": {"dispatcher": ["Uživatel nemá přístup do databáze !"]}, "title": "Autentization"}
    with mock.patch.object(c._session, "post", return_value=_resp(400, body)):
        with pytest.raises(UserException, match="přístup do databáze"):
            c.authenticate()


def test_request_4xx_raises_no_retry():
    c = _client()
    get = mock.Mock(return_value=_resp(400, {"title": "BadParam"}))
    with mock.patch.object(c._session, "get", get):
        with pytest.raises(UserException, match="BadParam"):
            c._request("/x")
    assert get.call_count == 1


def test_request_5xx_retries_then_fails():
    c = _client()
    get = mock.Mock(return_value=_resp(503, {}, text="boom"))
    with mock.patch.object(c._session, "get", get):
        with pytest.raises(UserException):
            c._request("/x")
    assert get.call_count == 3


def test_request_401_reauthenticates_once_then_succeeds():
    c = _client()
    # First GET is unauthorized, second (after re-auth) succeeds with a body.
    get = mock.Mock(side_effect=[_resp(401, {"error_description": "token expired"}), _resp(200, {"ok": True})])
    auth = mock.Mock()
    with mock.patch.object(c._session, "get", get), mock.patch.object(c, "authenticate", auth):
        result = c._request("/x")
    assert result == {"ok": True}
    assert auth.call_count == 1
    assert get.call_count == 2


def test_request_persistent_401_raises_after_single_reauth():
    c = _client()
    get = mock.Mock(return_value=_resp(401, {"error_description": "still unauthorized"}))
    auth = mock.Mock()
    with mock.patch.object(c._session, "get", get), mock.patch.object(c, "authenticate", auth):
        with pytest.raises(UserException, match="still unauthorized"):
            c._request("/x")
    # Re-auth attempted exactly once; the second 401 is raised rather than looping.
    assert auth.call_count == 1
    assert get.call_count == 2


def test_list_databases_returns_array():
    c = _client()
    with mock.patch.object(c, "_request", return_value={"count": 1, "databases": [{"dbSysName": "DB"}]}):
        assert c.list_databases() == [{"dbSysName": "DB"}]


def test_list_browses_uses_database_in_path():
    c = _client()
    with mock.patch.object(c, "_request", return_value={"browses": [{"browseIdent": "1"}]}) as req:
        out = c.list_browses()
    req.assert_called_once_with("/api/v1/browses/list/DB")
    assert out == [{"browseIdent": "1"}]


def test_get_browse_fields_returns_typed_fields():
    c = _client()
    fields = [
        {"fieldSysName": "T.ID", "fieldType": "integer", "fieldFormat": "int32", "fieldNullable": False},
        {"fieldSysName": "T.Name", "fieldType": "string", "fieldFormat": "", "fieldNullable": True},
        {"noSysName": True},
    ]
    meta = {"table": {"tableFields": fields}}
    with mock.patch.object(c, "_request", return_value=meta):
        result = c.get_browse_fields("1")
    assert [f["fieldSysName"] for f in result] == ["T.ID", "T.Name"]
    assert result[0]["fieldType"] == "integer"
    assert result[0]["fieldNullable"] is False


def test_iter_browse_rows_paginates_until_short_page():
    c = _client()
    pages = [
        {"rows": [{"row": {"T.ID": 1}}, {"row": {"T.ID": 2}}], "rowVersionMax": "0000000000000010"},
        {"rows": [{"row": {"T.ID": 3}}], "rowVersionMax": "0000000000000020"},  # short page -> stop
    ]
    with mock.patch.object(c, "_request", side_effect=pages) as req:
        rows = list(c.iter_browse_rows("1", select=["T.ID"], page_size=2))
    assert rows == [{"T.ID": 1}, {"T.ID": 2}, {"T.ID": 3}]
    assert c.last_row_version_max == "0000000000000020"
    assert req.call_args_list[0].kwargs["params"]["select"] == "T.ID"
    assert req.call_args_list[1].kwargs["params"]["skip"] == 2


def test_iter_browse_rows_passes_row_version_when_incremental():
    c = _client()
    with mock.patch.object(c, "_request", return_value={"rows": [], "rowVersionMax": None}) as req:
        list(c.iter_browse_rows("1", row_version="0000000000000005", page_size=100))
    assert req.call_args_list[0].kwargs["params"]["rowVersion"] == "0000000000000005"
    assert c.last_row_version_max == "0000000000000005"


def test_iter_browse_rows_sends_orderby_on_every_page():
    c = _client()
    pages = [
        {"rows": [{"row": {"T.ID": 1}}, {"row": {"T.ID": 2}}], "rowVersionMax": "0000000000000010"},
        {"rows": [{"row": {"T.ID": 3}}], "rowVersionMax": "0000000000000020"},  # short page -> stop
    ]
    with mock.patch.object(c, "_request", side_effect=pages) as req:
        rows = list(c.iter_browse_rows("1", select=["T.ID"], order_by=["T.ID"], page_size=2))
    # Deterministic order param is sent on every page request.
    assert all(call.kwargs["params"]["orderby"] == "T.ID" for call in req.call_args_list)
    # Multi-page iteration still yields all rows in order.
    assert rows == [{"T.ID": 1}, {"T.ID": 2}, {"T.ID": 3}]


def test_iter_browse_rows_omits_orderby_when_not_provided():
    c = _client()
    with mock.patch.object(c, "_request", return_value={"rows": [], "rowVersionMax": None}) as req:
        list(c.iter_browse_rows("1", select=["T.ID"], page_size=100))
    assert "orderby" not in req.call_args_list[0].kwargs["params"]
