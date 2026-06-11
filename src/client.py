import logging

import requests
from keboola.component.exceptions import UserException

RETRYABLE = (500, 502, 503, 504)


class HeliosInuvioClient:
    def __init__(self, base_url, username, password, database, timeout=180):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self.database = database
        self._timeout = timeout
        self._session = requests.Session()
        self._token = None
        self.licenses = {}
        self.last_row_version_max = None

    def authenticate(self):
        url = f"{self.base_url}/api/token"
        payload = {"username": self._username, "password": self._password}
        try:
            resp = self._session.post(url, json=payload, timeout=self._timeout)
        except requests.RequestException as e:
            raise UserException(f"Cannot reach Helios server at {self.base_url}: {e}")
        if resp.status_code != 200:
            raise UserException(f"Authentication failed: {self._error_message(resp)}")
        data = resp.json()
        if not data.get("token"):
            raise UserException(f"Authentication failed: no token returned ({data})")
        self._token = data["token"]
        self.licenses = {k: v for k, v in data.items() if k.startswith("license") and isinstance(v, bool)}
        self._session.headers.update({"Authorization": f"Bearer {self._token}"})
        return data

    def _request(self, path, params=None):
        url = f"{self.base_url}{path}"
        last = None
        reauthenticated = False
        for attempt in range(3):
            try:
                resp = self._session.get(url, params=params, timeout=self._timeout)
            except requests.RequestException as e:
                last = str(e)
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401 and not reauthenticated:
                # Token may have expired mid-run; re-authenticate once and retry.
                reauthenticated = True
                logging.info("Got 401 on %s; re-authenticating once and retrying.", path)
                self.authenticate()
                continue
            if resp.status_code in RETRYABLE:
                last = self._error_message(resp)
                logging.warning("Retryable error on %s (attempt %d): %s", path, attempt + 1, last)
                continue
            raise UserException(f"Request to {path} failed ({resp.status_code}): {self._error_message(resp)}")
        raise UserException(f"Request to {path} failed after retries: {last}")

    def list_databases(self):
        return self._request("/api/v1/databases/list").get("databases", [])

    def list_browses(self):
        return self._request(f"/api/v1/browses/list/{self.database}").get("browses", [])

    def get_browse_meta(self, browse_ident):
        return self._request(f"/api/v1/browses/meta/{self.database}/{browse_ident}")

    def get_browse_fields(self, browse_ident) -> list[dict]:
        meta = self.get_browse_meta(browse_ident)
        return [f for f in meta.get("table", {}).get("tableFields", []) if f.get("fieldSysName")]

    def iter_browse_rows(  # noqa: A002
        self, browse_ident, select=None, filter=None, row_version=None, order_by=None, page_size=1000
    ):
        # rowVersion is fixed-width zero-padded hex, so lexicographic max == numeric max.
        # order_by must be stable across pages — without it top/skip paging can drop or duplicate rows.
        skip = 0
        max_rv = row_version
        path = f"/api/v1/browses/data/{self.database}/{browse_ident}"
        while True:
            params = {"top": page_size, "skip": skip}
            if select:
                params["select"] = ",".join(select)
            if filter:
                params["filter"] = filter
            if row_version:
                params["rowVersion"] = row_version
            if order_by:
                params["orderby"] = ",".join(order_by)
            data = self._request(path, params=params)
            rows = data.get("rows", [])
            rvmax = data.get("rowVersionMax")
            if rvmax and (max_rv is None or rvmax > max_rv):
                max_rv = rvmax
            for r in rows:
                yield r.get("row", r)
            if len(rows) < page_size:
                break
            skip += page_size
        self.last_row_version_max = max_rv

    @staticmethod
    def _error_message(resp):
        try:
            d = resp.json()
        except ValueError:
            return (resp.text or "")[:300]
        if isinstance(d.get("errors"), dict):
            parts = [f"{k}: {'; '.join(str(x) for x in v)}" for k, v in d["errors"].items()]
            return f"{d.get('title', '')} — {' | '.join(parts)}".strip(" —")
        if d.get("error_description"):
            return d["error_description"]
        return str(d)
