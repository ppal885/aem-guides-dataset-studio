"""Jira REST API client."""
import os
import re
from typing import Optional
import httpx

from app.utils.rate_limiter import get_jira_limiter
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def _api_version() -> str:
    """Use JIRA_API_VERSION env (2 or 3). Corporate/on-prem Jira (e.g. jira.corp.adobe.com) typically needs v2."""
    v = os.getenv("JIRA_API_VERSION", "2").strip()
    return "2" if v == "2" else "3"


def _timeout() -> float:
    """Jira request timeout. Corporate Jira can be slow."""
    try:
        return float(os.getenv("JIRA_TIMEOUT_SEC", "60"))
    except (ValueError, TypeError):
        return 60.0


class JiraClient:
    """Client for Jira REST API v2 or v3."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("JIRA_BASE_URL") or os.getenv("JIRA_URL", "")).rstrip("/")
        self.username = username or os.getenv("JIRA_USERNAME", "")
        self.password = password or os.getenv("JIRA_PASSWORD", "")
        self.email = email or os.getenv("JIRA_EMAIL", "")
        self.api_token = api_token or os.getenv("JIRA_API_TOKEN", "")
        self._api = _api_version()
        self._auth = None
        if self.username and self.password:
            self._auth = httpx.BasicAuth(self.username, self.password)
        elif self.email and self.api_token:
            self._auth = httpx.BasicAuth(self.email, self.api_token)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> dict:
        """Make HTTP request to Jira API."""
        get_jira_limiter().acquire()
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "cache-control": "no-cache",
        }
        with httpx.Client(auth=self._auth, timeout=_timeout()) as client:
            response = client.request(
                method,
                url,
                params=params,
                json=json_data,
                headers=headers,
            )
            response.raise_for_status()
            return response.json() if response.content else {}

    def _download(self, content_url: str) -> bytes:
        """Download attachment content. Jira requires same auth for content URLs."""
        get_jira_limiter().acquire()
        with httpx.Client(auth=self._auth, timeout=max(60.0, _timeout()), follow_redirects=True) as client:
            response = client.get(content_url)
            response.raise_for_status()
            return response.content

    def get_issue(self, issue_key: str) -> dict:
        """Fetch a single issue by key."""
        path = f"/rest/api/{self._api}/issue/{issue_key}"
        return self._request("GET", path)

    def search_issues(self, jql: str, max_results: int = 500) -> list[dict]:
        """Search issues by JQL. Uses minimal fields for faster response."""
        all_issues = []
        start_at = 0
        max_results = min(max_results, 1000)

        while True:
            params = {
                "jql": jql,
                "maxResults": min(100, max_results - len(all_issues)),
                "startAt": start_at,
                "fields": "summary,issuetype,status",
            }
            data = self._request("GET", f"/rest/api/{self._api}/search", params=params)
            issues = data.get("issues", [])
            all_issues.extend(issues)
            if not issues or len(all_issues) >= max_results:
                break
            start_at = data.get("startAt", 0) + len(issues)
            if start_at >= data.get("total", 0):
                break

        return all_issues[:max_results]

    def search_issues_with_fields(
        self,
        jql: str,
        fields: str = "summary,description,labels,priority,status,created,updated,issuetype",
        max_results: int = 500,
    ) -> list[dict]:
        """Search issues by JQL with custom fields for DITA analysis."""
        all_issues = []
        start_at = 0
        max_results = min(max_results, 1000)

        while True:
            params = {
                "jql": jql,
                "maxResults": min(100, max_results - len(all_issues)),
                "startAt": start_at,
                "fields": fields,
            }
            data = self._request("GET", f"/rest/api/{self._api}/search", params=params)
            issues = data.get("issues", [])
            all_issues.extend(issues)
            if not issues or len(all_issues) >= max_results:
                break
            start_at = data.get("startAt", 0) + len(issues)
            if start_at >= data.get("total", 0):
                break

        return all_issues[:max_results]

    def get_issue_attachments(self, issue_key: str) -> list[dict]:
        """Get attachment metadata for an issue (from get_issue response)."""
        issue = self.get_issue(issue_key)
        fields = issue.get("fields", {})
        attachments = fields.get("attachment", [])
        return attachments if isinstance(attachments, list) else []

    def download_attachment(self, content_url: str) -> bytes:
        """Download attachment content from Jira content URL."""
        return self._download(content_url)

    def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issuetype: str = "Task",
        assignee: Optional[str] = None,
        **optional_fields: object,
    ) -> dict:
        """Create a new Jira issue. Returns created issue dict with key, id."""
        fields: dict = {
            "project": {"key": project_key},
            "summary": summary[:255],
            "description": description[:65000] if description else "",
            "issuetype": {"name": issuetype},
        }
        if assignee:
            fields["assignee"] = {"name": assignee}
        fields.update(optional_fields)
        data = self._request("POST", f"/rest/api/{self._api}/issue", json_data={"fields": fields})
        return data

    def transition_issue(
        self,
        issue_key: str,
        transition_id: str | int,
        comment: Optional[str] = None,
    ) -> None:
        """Transition an issue (e.g. close, reopen). Transition IDs are project-specific."""
        body: dict = {"transition": {"id": str(transition_id)}}
        if comment:
            body["update"] = {"comment": [{"add": {"body": comment}}]}
        self._request("POST", f"/rest/api/{self._api}/issue/{issue_key}/transitions", json_data=body)

    def get_transitions(self, issue_key: str) -> list[dict]:
        """Get available transitions for an issue. Returns list of {id, name}."""
        data = self._request("GET", f"/rest/api/{self._api}/issue/{issue_key}/transitions")
        return data.get("transitions", [])

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        """Fetch comments for an issue. Returns list of {id, body, author, created, body_text}."""
        path = f"/rest/api/{self._api}/issue/{issue_key}/comment"
        data = self._request("GET", path)
        raw = data.get("comments", [])
        if not isinstance(raw, list):
            return []
        result = []
        for c in raw:
            body = c.get("body") or {}
            body_text = _adf_to_plain_text(body) if isinstance(body, dict) else str(body)
            author = c.get("author") or {}
            author_name = author.get("displayName", author.get("name", "")) if isinstance(author, dict) else ""
            result.append({
                "id": c.get("id"),
                "body": body,
                "body_text": body_text,
                "author": author_name,
                "created": c.get("created"),
            })
        return result


def _adf_to_plain_text(adf: dict) -> str:
    """Extract plain text from Atlassian Document Format (ADF)."""
    if not adf or not isinstance(adf, dict):
        return ""
    text = _adf_node_to_text(adf).strip()
    return _normalize_adf_text(text)


def _adf_node_to_text(node: object) -> str:
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""

    node_type = str(node.get("type") or "").strip()
    attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
    content = node.get("content") if isinstance(node.get("content"), list) else []

    if node_type == "text":
        text = str(node.get("text") or "")
        for mark in node.get("marks") or []:
            if not isinstance(mark, dict):
                continue
            if mark.get("type") == "link":
                href = str((mark.get("attrs") or {}).get("href") or "").strip()
                if href and href not in text:
                    text = f"{text} ({href})"
        return text
    if node_type == "hardBreak":
        return "\n"
    if node_type == "mention":
        return str(attrs.get("text") or attrs.get("id") or "").strip()
    if node_type == "emoji":
        return str(attrs.get("text") or attrs.get("shortName") or "").strip()
    if node_type in {"inlineCard", "blockCard", "embedCard"}:
        return str(attrs.get("url") or attrs.get("title") or "").strip()
    if node_type == "status":
        return str(attrs.get("text") or "").strip()
    if node_type == "date":
        return str(attrs.get("timestamp") or "").strip()

    child_text = [_adf_node_to_text(child) for child in content]

    if node_type in {"doc", "panel", "blockquote", "tableCell", "tableHeader"}:
        return "\n".join(part.strip() for part in child_text if part.strip())
    if node_type in {"paragraph", "heading"}:
        return "".join(child_text).strip()
    if node_type == "codeBlock":
        code = "".join(child_text).strip()
        return f"\n{code}\n" if code else ""
    if node_type == "listItem":
        parts = [part.strip() for part in child_text if part.strip()]
        return "\n".join(parts)
    if node_type == "bulletList":
        items = []
        for item in content:
            rendered = _normalize_adf_text(_adf_node_to_text(item))
            if rendered:
                items.append(f"- {rendered}")
        return "\n".join(items)
    if node_type == "orderedList":
        items = []
        for index, item in enumerate(content, start=1):
            rendered = _normalize_adf_text(_adf_node_to_text(item))
            if rendered:
                items.append(f"{index}. {rendered}")
        return "\n".join(items)
    if node_type == "tableRow":
        cells = [_normalize_adf_text(part) for part in child_text if _normalize_adf_text(part)]
        return " | ".join(cells)
    if node_type == "table":
        rows = [part.strip() for part in child_text if part.strip()]
        return "\n".join(rows)
    if node_type in {"mediaSingle", "mediaGroup"}:
        return ""

    return "".join(child_text)


def _normalize_adf_text(text: str) -> str:
    lines = []
    for raw_line in str(text or "").splitlines():
        stripped = re.sub(r"[ \t]+", " ", raw_line).strip()
        if stripped:
            lines.append(stripped)
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def extract_description_from_issue(issue: dict) -> str:
    """Extract plain text description from Jira issue fields (handles ADF)."""
    fields = issue.get("fields", {}) if isinstance(issue, dict) else {}
    desc = fields.get("description")
    if not desc:
        return ""
    if isinstance(desc, dict) and "content" in desc:
        return _adf_to_plain_text(desc)
    return str(desc)[:50000]
