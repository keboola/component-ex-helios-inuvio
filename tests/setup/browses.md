# Helios iNuvio — Browse ID Reference (database: HEE_Helios_001)

The `browse` parameter in component configs is the numeric `browseIdent` from the Helios API
(`GET /api/v1/browses/list/{database}`). Use `list_browses` sync action in the UI to discover
IDs for a given database — the dropdown shows the caption alongside the ID.

## Browses covered by functional tests

| ID   | Name (browseCaption)      | Table               | Test directory          |
|------|---------------------------|---------------------|-------------------------|
| 1    | Organizace                | TabCisOrg           | `organizace`            |
| 2    | Kmenové karty             | TabKmenZbozi        | `kmenove_karty`         |
| 3    | PSČ                       | TabPSC              | `psc`                   |
| 6    | Měny                      | TabKodMen           | `meny`                  |
| 11   | Měrné jednotky            | TabMJ               | `merne_jednotky`        |
| 13   | Žurnál                    | TabZurnal           | `zurnal`                |
| 14   | Uživatelé                 | TabUserCfg          | `uzivatele`             |
| 15   | Skupiny karet             | TabSkupinyZbozi     | `skupiny_karet`         |
| 95   | Globální konfigurace      | TabHGlob            | `globalni_konfigurace`  |
| 1540 | Sazby DPH                 | TabSazbyDPH         | `sazby_dph`             |

## How to look up a browse ID

```bash
# List all accessible browses for a database (requires a live token)
curl -s http://<host>/api/v1/browses/list/<database> \
  -H "Authorization: Bearer <token>" \
  | python3 -c "
import sys, json
for b in json.load(sys.stdin).get('browses', []):
    if b.get('browseReadImplemented') and b.get('browseUserRightRead'):
        print(b['browseIdent'], b['browseCaption'])
"
```
