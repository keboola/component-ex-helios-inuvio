# Helios iNuvio Extractor

Keboola extractor for the **Helios iNuvio Server** (Asseco Solutions ERP) System API.
Each configuration row extracts one Helios "browse" (přehled / data view) into a Keboola Storage table.

## Overview

The component authenticates via the Helios iNuvio REST API (JWT bearer token from `POST /api/token`),
then fetches browse data page by page. The output is one CSV table per configuration row.
In production the component reaches the Helios server over the customer's network or VPN.

## Configuration

### Connection (config level)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `base_url` | string | yes | Base URL of the Helios iNuvio application server, e.g. `http://my-server:8080` |
| `username` | string | yes | Account username |
| `#password` | string | yes | Account password (stored encrypted) |
| `database` | string | yes | System name of the Helios iNuvio database. Use "Load Databases" to populate the dropdown. |

A **Test Connection** button validates credentials and reports which APIs are licensed on the server.

### Row (per browse)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `browse` | string | yes | Browse to extract. Use "Load Browses" to populate the dropdown. The stored value is `Caption (ident)` (e.g. `Orders (BROWSE_ORDERS)`) but a plain ident like `BROWSE_ORDERS` is also accepted. |
| `output_table_name` | string | no | Output table name in Keboola Storage. Defaults to `browse_<ident>` when left empty. |
| `columns` | array | no | Columns to extract. Leave empty to extract **all** columns. Use "Load Columns" to populate the multi-select. |
| `load_type` | enum | no | `full_load` (default) or `incremental_load`. |
| `primary_key` | array | no | Required for `incremental_load` — columns that uniquely identify a row (enables upsert). |
| `filter` | string | no | Optional server-side Helios filter condition. |

## Incremental Loading

Incremental loading uses the Helios `rowVersion` cursor:

1. After each run the maximum `rowVersion` returned by the API is saved in the row's `state.json`.
2. The next incremental run passes that value as `rowVersion` query parameter so the server returns
   only rows changed since the last run.
3. The output table is written with `incremental=true` and the configured `primary_key`, so Keboola
   Storage performs an upsert instead of a full overwrite.

Full load (`full_load`) ignores any saved state and overwrites the output table each run.

## Output

- One CSV table per configuration row.
- Column names are sanitized: any character outside `[A-Za-z0-9_]` is replaced with `_`
  (e.g. `TabCisOrg.ID` → `TabCisOrg_ID`).
- Nested JSON values (dict/list) are serialised as JSON strings in a single cell.
- The table manifest sets `primary_key` and `incremental` flag as configured.

## Development / Tests

Install dependencies with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Run the full test suite:

```bash
uv run pytest -v
```

Lint and format checks:

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

Functional tests replay HTTP interactions from a committed VCR cassette
(`tests/functional/*/source/data/cassettes/`) so they run fully offline without a live Helios server.
