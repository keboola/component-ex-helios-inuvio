import pytest
from keboola.component.exceptions import UserException

from configuration import Configuration, LoadType


def _conn(**over):
    base = {"base_url": "http://localhost:8080", "username": "u", "#password": "p", "database": "DB"}
    base.update(over)
    return base


def test_connection_fields_parsed():
    c = Configuration(**_conn())
    assert c.base_url == "http://localhost:8080"
    assert c.username == "u"
    assert c.password == "p"  # aliased from #password
    assert c.database == "DB"


def test_row_defaults():
    c = Configuration(**_conn())
    assert c.browse == ""
    assert c.columns == []
    assert c.load_type == LoadType.full_load
    assert c.primary_key == []


def test_incremental_and_columns():
    c = Configuration(
        **_conn(browse="1", columns=["TabCisOrg.ID"], load_type="incremental_load", primary_key=["TabCisOrg.ID"])
    )
    assert c.load_type == LoadType.incremental_load
    assert c.columns == ["TabCisOrg.ID"]


def test_missing_required_raises_userexception():
    with pytest.raises(UserException):
        Configuration(username="u", **{"#password": "p"})  # no base_url/database
