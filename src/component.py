import csv
import logging
import re
from datetime import UTC, datetime

from keboola.component.base import ComponentBase, sync_action
from keboola.component.dao import BaseType, ColumnDefinition, SupportedDataTypes
from keboola.component.exceptions import UserException
from keboola.component.sync_actions import MessageType, SelectElement, ValidationResult

from client import HeliosInuvioClient
from configuration import Configuration, LoadType
from transform import flatten_row, sanitize_column

try:
    from keboola.datadirtest.vcr import UrlPatternSanitizer

    VCR_SANITIZERS = [
        UrlPatternSanitizer(patterns=[(r"http://localhost:\d+", "http://helios-inuvio-sandbox")]),
    ]
except ImportError:
    VCR_SANITIZERS = []

_HELIOS_TYPE_MAP: dict[tuple[str, str], SupportedDataTypes] = {
    ("integer", "int32"): SupportedDataTypes.INTEGER,
    ("integer", "int64"): SupportedDataTypes.INTEGER,
    ("number", "double"): SupportedDataTypes.FLOAT,
    ("boolean", ""): SupportedDataTypes.BOOLEAN,
    ("string", "date-time"): SupportedDataTypes.TIMESTAMP,
    ("string", ""): SupportedDataTypes.STRING,
    ("string", "byte"): SupportedDataTypes.STRING,
}


def _parse_browse_ident(value: str) -> str:
    # Anchors to end-of-string so captions like "Orders (confirmed) (102)" → "102"; plain "102" passes through.
    m = re.search(r"\(([^)]+)\)$", value.strip())
    return m.group(1) if m else value


def _field_to_col_def(field: dict) -> ColumnDefinition:
    kbc_type = _HELIOS_TYPE_MAP.get(
        (field.get("fieldType", "string"), field.get("fieldFormat", "")),
        SupportedDataTypes.STRING,
    )
    return ColumnDefinition(
        data_types=BaseType(dtype=kbc_type),
        nullable=field.get("fieldNullable", True),
    )


class Component(ComponentBase):
    def __init__(self):
        super().__init__()

    def _build_client(self, params: Configuration) -> HeliosInuvioClient:
        client = HeliosInuvioClient(
            params.base_url,
            params.username,
            params.password,
            params.database,
        )
        client.authenticate()
        return client

    def run(self):
        params = Configuration(**self.configuration.parameters)
        if not params.browse:
            raise UserException("No browse selected for this configuration row.")
        incremental = params.load_type == LoadType.incremental_load
        if incremental and not params.primary_key:
            raise UserException("Incremental load requires a primary key.")

        browse_ident = _parse_browse_ident(params.browse)
        client = self._build_client(params)
        fields = client.get_browse_fields(browse_ident)
        if not fields:
            raise UserException(f"Browse '{browse_ident}' returned no columns from meta.")

        field_map = {f["fieldSysName"]: f for f in fields}
        selected = params.columns or list(field_map.keys())
        schema = {sanitize_column(c): _field_to_col_def(field_map.get(c, {})) for c in selected}
        pk = [sanitize_column(c) for c in params.primary_key]
        row_version = self.get_state_file().get("row_version") if incremental else None
        table_name = params.output_table_name or f"browse_{sanitize_column(browse_ident)}"

        table = self.create_out_table_definition(
            f"{table_name}.csv",
            incremental=incremental,
            primary_key=pk,
            schema=schema,
            has_header=True,
        )
        order_by = params.primary_key or selected[:1]
        count = 0
        with open(table.full_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(schema.keys()), extrasaction="ignore", restval="")
            writer.writeheader()
            for row in client.iter_browse_rows(
                browse_ident,
                select=selected,
                filter=params.filter or None,
                row_version=row_version,
                order_by=order_by,
            ):
                writer.writerow(flatten_row(row))
                count += 1
        self.write_manifest(table)
        logging.info("Wrote %d rows to %s (incremental=%s)", count, table_name, incremental)

        self.write_state_file(
            {
                "row_version": client.last_row_version_max,
                "last_run_utc": datetime.now(UTC).isoformat(),
            }
        )

    @sync_action("testConnection")
    def test_connection(self) -> ValidationResult:
        params = Configuration(**self.configuration.parameters)
        client = self._build_client(params)
        licensed = ", ".join(k.removeprefix("license").removesuffix("API") for k, v in client.licenses.items() if v)
        return ValidationResult(
            f"Connection successful. Licensed APIs: {licensed or 'none'}.",
            MessageType.SUCCESS,
        )

    @sync_action("list_databases")
    def list_databases(self) -> list[SelectElement]:
        params = Configuration(**self.configuration.parameters)
        client = self._build_client(params)
        return [
            SelectElement(
                value=db["dbSysName"],
                label=f"{db.get('dbCaption', db['dbSysName'])} ({db['dbSysName']})",
            )
            for db in client.list_databases()
            if db.get("dbHasDBAccess", True)
        ]

    @sync_action("list_browses")
    def list_browses(self) -> list[SelectElement]:
        params = Configuration(**self.configuration.parameters)
        client = self._build_client(params)
        out = []
        for b in client.list_browses():
            if b.get("browseReadImplemented") and b.get("browseUserRightRead") and b.get("browseLisenced"):
                out.append(SelectElement(value=f"{b['browseCaption']} ({b['browseIdent']})"))
        return out

    @sync_action("list_columns")
    def list_columns(self) -> list[SelectElement]:
        params = Configuration(**self.configuration.parameters)
        if not params.browse:
            raise UserException("Select a browse first to load its columns.")
        client = self._build_client(params)
        browse_ident = _parse_browse_ident(params.browse)
        fields = client.get_browse_meta(browse_ident).get("table", {}).get("tableFields", [])
        return [
            SelectElement(
                value=f["fieldSysName"],
                label=f"{f.get('fieldDisplayName', f['fieldSysName'])} ({f['fieldSysName']})",
            )
            for f in fields
            if f.get("fieldSysName")
        ]


if __name__ == "__main__":
    try:
        Component().execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
