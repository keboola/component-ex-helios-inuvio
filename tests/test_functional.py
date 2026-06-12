"""Functional tests: browse extraction replayed from VCR cassettes.

VCRDataDirTester runs component.py in-process so vcrpy intercepts all HTTP
calls and replays them from cassettes/requests.json.  No live network access
is required during replay.
"""

import json
from pathlib import Path

import pytest
from keboola.datadirtest.vcr import VCRDataDirTester

FUNCTIONAL_DIR = Path(__file__).parent / "functional"
COMPONENT_SCRIPT = Path(__file__).parent.parent / "src" / "component.py"

# The 10 browse endpoints recorded against the live sandbox.
BROWSE_TESTS = [
    "organizace",
    "kmenove_karty",
    "psc",
    "meny",
    "merne_jednotky",
    "zurnal",
    "uzivatele",
    "skupiny_karet",
    "globalni_konfigurace",
    "sazby_dph",
]


@pytest.mark.parametrize("test_name", BROWSE_TESTS)
def test_functional(test_name):
    tester = VCRDataDirTester(
        data_dir=str(FUNCTIONAL_DIR),
        component_script=str(COMPONENT_SCRIPT),
        vcr_mode="replay",
        selected_tests=[test_name],
    )
    tester.run()


# ---------------------------------------------------------------------------
# Spot-check the organizace expected output for schema and row-count sanity.
# ---------------------------------------------------------------------------

ORGANIZACE_DIR = FUNCTIONAL_DIR / "organizace" / "expected" / "data" / "out" / "tables"
EXPECTED_COLUMNS = ["TabCisOrg_ID", "TabCisOrg_Nazev"]


def test_organizace_manifest_has_header_and_typed_schema():
    manifest = json.loads((ORGANIZACE_DIR / "organizace.csv.manifest").read_text(encoding="utf-8"))
    assert manifest["has_header"] is True
    names = [col["name"] for col in manifest["schema"]]
    assert names == EXPECTED_COLUMNS
    types = {col["name"]: col["data_type"]["base"]["type"] for col in manifest["schema"]}
    assert types["TabCisOrg_ID"] == "INTEGER"
    assert types["TabCisOrg_Nazev"] == "STRING"


def test_organizace_csv_has_header_and_data_rows():
    csv_path = ORGANIZACE_DIR / "organizace.csv"
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "TabCisOrg_ID,TabCisOrg_Nazev", f"Expected header line, got: {lines[0]!r}"
    assert len(lines) > 1, "organizace.csv must contain at least one data row"


def test_organizace_row_count_matches_cassette():
    import csv as csv_mod

    csv_path = ORGANIZACE_DIR / "organizace.csv"
    with csv_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv_mod.DictReader(fh))
    assert len(rows) == 14, f"Expected 14 rows, got {len(rows)}"
