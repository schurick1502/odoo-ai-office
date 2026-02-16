"""Async HTTP client for DocumentFlow REST API."""

import os

import httpx


class DocFlowClient:
    """Slim async client wrapping DocumentFlow's REST API with JWT auth."""

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
    ):
        self.base_url = (base_url or os.getenv("DOCFLOW_URL", "http://localhost:8000")).rstrip("/")
        self._username = username or os.getenv("DOCFLOW_USERNAME", "")
        self._password = password or os.getenv("DOCFLOW_PASSWORD", "")
        self._token = token or os.getenv("DOCFLOW_TOKEN", "")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        if not self._token and self._username:
            await self._login()
        return self._client

    async def _login(self) -> None:
        """Authenticate and store JWT token."""
        client = self._client or httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        if self._client is None:
            self._client = client
        resp = await client.post("/api/auth/login", json={
            "username": self._username,
            "password": self._password,
        })
        resp.raise_for_status()
        data = resp.json()
        self._token = data.get("access_token", "")

    def _headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def _get(self, path: str, params: dict | None = None) -> dict:
        client = await self._get_client()
        resp = await client.get(path, headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, json_data: dict | None = None) -> dict:
        client = await self._get_client()
        resp = await client.post(path, headers=self._headers(), json=json_data)
        resp.raise_for_status()
        return resp.json()

    # ── Public API ──────────────────────────────────────────

    async def health(self) -> dict:
        return await self._get("/api/health")

    async def list_jobs(
        self,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        params: dict = {"page": page, "page_size": page_size}
        if status:
            params["status"] = status
        return await self._get("/api/jobs", params=params)

    async def get_job(self, job_id: int) -> dict:
        return await self._get(f"/api/jobs/{job_id}")

    async def get_bookings(self, job_id: int) -> list:
        result = await self._get(f"/api/jobs/{job_id}/bookings")
        return result if isinstance(result, list) else result.get("items", [])

    async def get_positions(self, job_id: int) -> list:
        result = await self._get(f"/api/jobs/{job_id}/positions")
        return result if isinstance(result, list) else result.get("items", [])

    async def approve_job(self, job_id: int) -> dict:
        return await self._post(f"/api/jobs/{job_id}/approve")

    async def export_datev(self, month: str) -> dict:
        return await self._post("/api/export/datev", json_data={"month": month})

    async def search_jobs(self, query: str) -> dict:
        return await self._get("/api/jobs", params={"search": query})

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
