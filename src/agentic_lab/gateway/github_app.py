from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import jwt


class GitHubAppInstallationAuth:
    def __init__(self, app_id: int, private_key: str, client: httpx.Client) -> None:
        self._app_id = app_id
        self._private_key = private_key
        self._client = client

    def installation_token(self, repository_id: int, permissions: dict[str, str]) -> str:
        now = datetime.now(UTC)
        app_jwt = jwt.encode(
            {
                "iat": int((now - timedelta(seconds=30)).timestamp()),
                "exp": int((now + timedelta(minutes=9)).timestamp()),
                "iss": str(self._app_id),
            },
            self._private_key,
            algorithm="RS256",
        )
        installation = self._client.get(
            f"/repositories/{repository_id}/installation", headers=self.headers(app_jwt)
        )
        installation.raise_for_status()
        installation_id = installation.json().get("id")
        if not isinstance(installation_id, int):
            raise ValueError("GitHub installation response is missing its ID")
        token_response = self._client.post(
            f"/app/installations/{installation_id}/access_tokens",
            headers=self.headers(app_jwt),
            json={"repository_ids": [repository_id], "permissions": permissions},
        )
        token_response.raise_for_status()
        token = token_response.json().get("token")
        if not isinstance(token, str) or not token:
            raise ValueError("GitHub token response is invalid")
        return token

    @staticmethod
    def headers(token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
