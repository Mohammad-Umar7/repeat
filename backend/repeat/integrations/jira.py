"""Jira Cloud REST v3 over basic auth (email + API token)."""

from __future__ import annotations

import base64

import httpx

from ..models import UndoToken
from .base import ActionResult, IntegrationError, JiraClient, VerifyResult


def _adf(text: str) -> dict:
    """Atlassian Document Format for a plain multi-paragraph description."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()] or [""]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p.strip()}]}
            for p in paragraphs
        ],
    }


class LiveJiraClient(JiraClient):
    def __init__(
        self, *, base_url: str, email: str, api_token: str, project_key: str, issue_type: str
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.project_key = project_key
        self.issue_type = issue_type
        token = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
            timeout=20,
        )

    async def health(self) -> tuple[bool, str]:
        try:
            r = await self._client.get("/rest/api/3/myself")
            r.raise_for_status()
            return True, f"Jira connected as {r.json().get('displayName', 'user')}"
        except Exception as e:
            return False, f"Jira unreachable: {e}"

    async def create_issue(self, *, summary: str, description: str) -> ActionResult:
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "issuetype": {"name": self.issue_type},
                "summary": summary[:255],
                "description": _adf(description),
            }
        }
        try:
            r = await self._client.post("/rest/api/3/issue", json=payload)
        except httpx.HTTPError as e:
            raise IntegrationError(f"Jira did not respond while creating the issue ({e}).") from e
        if r.status_code == 401:
            raise IntegrationError("Jira rejected the API token.", retryable=False)
        if r.status_code >= 400:
            msg = r.json().get("errors") or r.json().get("errorMessages") or r.text
            raise IntegrationError(f"Jira refused the issue: {msg}", retryable=r.status_code >= 500)
        data = r.json()
        key = data["key"]
        url = f"{self.base_url}/browse/{key}"
        return ActionResult(
            outputs={"issue_key": key, "issue_url": url, "issue_id": data["id"]},
            undo_token=UndoToken(kind="jira_issue", ref={"key": key}),
            result_url=url,
        )

    async def verify_issue(self, key: str) -> VerifyResult:
        r = await self._client.get(f"/rest/api/3/issue/{key}", params={"fields": "summary,status"})
        if r.status_code == 200:
            f = r.json()["fields"]
            return VerifyResult(
                True, f"{key} exists ({f['status']['name']})", {"summary": f["summary"]}
            )
        if r.status_code == 404:
            return VerifyResult(False, f"{key} was not found in Jira.")
        return VerifyResult(False, f"Jira returned {r.status_code} while checking {key}.")

    async def delete_issue(self, key: str) -> VerifyResult:
        r = await self._client.delete(f"/rest/api/3/issue/{key}", params={"deleteSubtasks": "true"})
        if r.status_code in (204, 404):
            check = await self.verify_issue(key)
            if not check.ok:
                return VerifyResult(True, f"{key} deleted and confirmed gone.")
            return VerifyResult(False, f"{key} still exists after delete.")
        return VerifyResult(False, f"Jira returned {r.status_code} deleting {key}: {r.text[:200]}")
