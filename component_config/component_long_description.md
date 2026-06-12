The Helios iNuvio extractor connects to an Asseco Solutions Helios iNuvio Server via its REST API
and loads data into Keboola Storage. Each configuration row targets one Helios browse (data view):
the browse and its columns are selected from live dropdowns populated by the component's sync actions,
so no manual identifier look-up is needed. Rows can be loaded in full (table overwrite each run) or
incrementally using the Helios `rowVersion` cursor, which fetches only records changed since the last
successful run. Incremental mode requires a user-defined primary key that Storage uses to upsert new
and updated records. An optional server-side filter condition can be applied to limit the data returned.
