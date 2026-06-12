import logging

import requests
import tenacity
from keboola.component.exceptions import UserException

RETRYABLE = (500, 502, 503, 504)
DEFAULT_MAX_ATTEMPTS = 3


class _RetryableHttpError(Exception):
    """Internal signal that a request should be retried (transient 5xx or a one-time 401 re-auth)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class HeliosInuvioClient:
    def __init__(
        self, base_url, username, password, database, timeout=180, max_attempts=DEFAULT_MAX_ATTEMPTS, retry_wait=None
    ):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self.database = database
        self._timeout = timeout
        self._max_attempts = max_attempts
        # Exponential backoff between retries by default; tests pass wait_none() to stay fast.
        self._retry_wait = retry_wait if retry_wait is not None else tenacity.wait_exponential(multiplier=1, max=30)
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
        reauthenticated = False
        retryer = tenacity.Retrying(
            retry=tenacity.retry_if_exception_type((requests.RequestException, _RetryableHttpError)),
            wait=self._retry_wait,
            stop=tenacity.stop_after_attempt(self._max_attempts),
            reraise=True,
        )
        try:
            for attempt in retryer:
                with attempt:
                    resp = self._session.get(url, params=params, timeout=self._timeout)
                    if resp.status_code == 200:
                        return resp.json()
                    if resp.status_code == 401 and not reauthenticated:
                        # Token may have expired mid-run; re-authenticate once and retry.
                        reauthenticated = True
                        logging.info("Got 401 on %s; re-authenticating once and retrying.", path)
                        self.authenticate()
                        raise _RetryableHttpError("re-authenticated after 401")
                    if resp.status_code in RETRYABLE:
                        msg = self._error_message(resp)
                        logging.warning("Retryable error on %s: %s", path, msg)
                        raise _RetryableHttpError(msg)
                    raise UserException(f"Request to {path} failed ({resp.status_code}): {self._error_message(resp)}")
        except _RetryableHttpError as e:
            raise UserException(f"Request to {path} failed after retries: {e.message}") from e
        except requests.RequestException as e:
            raise UserException(f"Cannot reach Helios server at {self.base_url}: {e}") from e

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
