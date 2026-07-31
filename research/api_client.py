"""HTTP client for RobotAIGeek research agent workflows."""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import urljoin

import requests

from load_env import load_research_env

load_research_env()


class ResearchApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        # 120s: prod list pages with heavy serializers (translations/photos) can
        # exceed 60s under load — see ACY (company 1369) read timeouts.
        timeout: int = 120,
    ):
        self.base_url = (base_url or os.environ.get("IMPORT_SYNC_API_BASE_URL", "")).rstrip("/") + "/"
        self.api_key = api_key or os.environ.get("IMPORT_SYNC_API_KEY", "")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "RobotAIGeek-ResearchAgent/1.0",
        })

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = self._session.get(self._url(path), params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, data: dict[str, Any]) -> Any:
        resp = self._session.patch(self._url(path), json=data, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict[str, Any]) -> Any:
        resp = self._session.post(self._url(path), json=data, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_company_missing_data(
        self,
        exclude_ids: str = "",
        *,
        country_code: str | None = None,
        include_null_country: bool = False,
        exclude_generic_slugs: bool = False,
    ) -> dict[str, Any] | None:
        params: dict[str, str] = {}
        if exclude_ids:
            params["exclude_ids"] = exclude_ids
        if country_code:
            params["country_code"] = country_code
        if include_null_country:
            params["include_null_country"] = "true"
        if exclude_generic_slugs:
            params["exclude_generic_slugs"] = "true"
        try:
            return self._get("companies/missing-data/", params=params)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

    def get_country_id(self, country_code: str) -> int | None:
        """Resolve Country PK by ISO alpha-2 code."""
        code = (country_code or "").strip().upper()
        if not code:
            return None
        try:
            # Prefer exact code match by paging; search endpoint is unreliable.
            page = 1
            while page <= 5:
                data = self._get("countries/", params={"page": page, "page_size": 100})
                results = data.get("results", data if isinstance(data, list) else [])
                for row in results:
                    if (row.get("code") or "").upper() == code:
                        return row.get("id")
                if not (isinstance(data, dict) and data.get("next")):
                    break
                page += 1
        except requests.HTTPError:
            return None
        return None

    def get_robot_missing_data(
        self,
        detailed: bool = False,
        exclude_ids: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if detailed:
            params["detailed"] = "true"
        if exclude_ids:
            params["exclude_ids"] = exclude_ids
        return self._get("robots/robots/with-missing-data/", params=params)

    def get_company(self, slug_or_id: str | int) -> dict[str, Any]:
        return self._get(f"companies/{slug_or_id}/")

    def search_companies(self, search: str, page_size: int = 20) -> list[dict[str, Any]]:
        data = self._get("companies/", params={"search": search, "page_size": page_size})
        return data.get("results", data if isinstance(data, list) else [])

    def get_company_names(self) -> list[str]:
        data = self._get("companies/names/")
        return data if isinstance(data, list) else []

    def list_robots_missing_image(self, page_size: int = 200) -> list[dict[str, Any]]:
        """Return all robots that have no image, across all companies."""
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self._get(
                "robots/robots/",
                params={"no_image": "true", "page": page, "page_size": page_size},
            )
            batch = data.get("results", [])
            results.extend(batch)
            if not data.get("next"):
                break
            page += 1
        return results

    def list_robots_for_company(self, company_id: int, page_size: int = 50) -> list[dict[str, Any]]:
        # page_size kept small: prod intermittently 500s on large serialized pages.
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            last_exc: Exception | None = None
            for attempt in range(4):
                try:
                    data = self._get(
                        "robots/robots/",
                        params={"company_ref": company_id, "page": page, "page_size": page_size},
                    )
                    break
                except Exception as exc:
                    last_exc = exc
                    time.sleep(2 ** attempt)
            else:
                raise last_exc
            batch = data.get("results", [])
            results.extend(batch)
            if not data.get("next"):
                break
            page += 1
        return results

    def get_subcategories(self) -> list[dict[str, Any]]:
        # The endpoint returns a BARE LIST (it is not paginated), so the
        # `data.get("results", ...)` form raised AttributeError on every call —
        # the isinstance fallback was evaluated as the default argument, which
        # Python computes before `.get` runs. Check the type first.
        data = self._get("robots/subcategories/")
        if isinstance(data, list):
            return data
        return data.get("results", []) if isinstance(data, dict) else []

    def list_tags(self, *, q: str = "", page_size: int = 200) -> list[dict[str, Any]]:
        """Fetch active tags from GET /api/v1/tags/ (paginated)."""
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            params: dict[str, Any] = {"page": page, "page_size": page_size}
            if q:
                params["q"] = q
            data = self._get("tags/", params=params)
            batch = data.get("results", data if isinstance(data, list) else [])
            if not batch:
                break
            results.extend(batch)
            if not data.get("next"):
                break
            page += 1
            if page > 20:
                break
        return results

    def list_companies_missing_info(
        self,
        fields: str = "website,country,logo,description",
        page_size: int = 100,
        exclude_generic_slugs: bool = True,
        source_locale: str = "en",
    ) -> list[dict[str, Any]]:
        """Return all companies that have at least one missing field, paginated."""
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            params: dict[str, Any] = {
                "fields": fields,
                "all": "true",
                "page": page,
                "page_size": page_size,
                "exclude_generic_slugs": "true" if exclude_generic_slugs else "false",
            }
            if source_locale:
                params["source_locale"] = source_locale
            data = self._get("companies/missing-data/", params=params)
            batch = data.get("results", [])
            results.extend(batch)
            if not data.get("next"):
                break
            page += 1
        return results

    def create_company(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new company via POST /api/v1/companies/.

        Required field: ``name``.
        Optional fields: ``website``, ``slug``, ``country_id``, ``categories``
        (list of category-id ints), ``description``, ``source_locale``, etc.

        Returns the full company object on success (HTTP 201).
        Raises ``requests.HTTPError`` on failure (e.g. 400 duplicate name).
        """
        return self._post("companies/", payload)

    def patch_company(self, company_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._patch(f"companies/{company_id}/", payload)

    def patch_company_logo(self, company_id: int, logo_bytes: bytes, filename: str) -> dict[str, Any]:
        """Upload a logo image for a company via multipart PATCH."""
        import mimetypes

        url = self._url(f"companies/{company_id}/")
        # Session defaults to application/json; multipart upload must omit that header
        # so requests can set multipart/form-data with boundary.
        headers = {
            k: v for k, v in self._session.headers.items()
            if k.lower() not in ("content-type", "accept")
        }
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        resp = requests.patch(
            url,
            files={"logo": (filename, logo_bytes, mime)},
            headers={**headers, "X-API-Key": self.api_key, "Accept": "application/json"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def bulk_import_robots(
        self,
        robots: list[dict[str, Any]],
        *,
        update_existing: bool = False,
        patch_existing: bool = False,
        status: str = "pending_review",
        skip_company_update: bool = False,
        created_by_id: int | None = None,
        replace_media: bool = False,
        replace_videos: bool = False,
    ) -> dict[str, Any]:
        """``replace_videos`` deletes the robot's existing videos and recreates them
        from ``video_urls`` — patch mode alone only backfills title/description on
        videos that are already there, so it cannot correct a wrong/mis-attributed
        clip. Videos-only counterpart to ``replace_media``."""
        body: dict[str, Any] = {
            "robots": robots,
            "update_existing": update_existing,
            "patch_existing": patch_existing,
            "status": status,
            "skip_company_update": skip_company_update,
        }
        if created_by_id:
            body["created_by_id"] = created_by_id
        if replace_media:
            body["replace_media"] = True
        if replace_videos:
            body["replace_videos"] = True
        return self._post("robots/robots/bulk-import/", body)

    def resolve_country_id(self, country_code: str) -> int | None:
        return self.get_country_id(country_code)
