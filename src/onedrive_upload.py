"""Upload markdown-fil til OneDrive personal via Microsoft Graph API.

Auth-flow: refresh_token (engangs-konfiguration). Se SETUP.md for hvordan du laver
en Azure app-registrering og får refresh token.
"""
from __future__ import annotations

import logging

import requests

LOG = logging.getLogger("onedrive")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
SCOPE = "Files.ReadWrite offline_access"


def get_access_token(client_id: str, refresh_token: str, tenant: str = "consumers") -> str:
    """Bytter refresh token til access token (gyldig ~1 time)."""
    url = TOKEN_URL_TEMPLATE.format(tenant=tenant)
    data = {
        "client_id": client_id,
        "scope": SCOPE,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    r = requests.post(url, data=data, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def upload_markdown(content: str, onedrive_path: str, filename: str,
                    client_id: str, refresh_token: str,
                    tenant: str = "consumers") -> str:
    """Upload tekst-indhold som .md fil til OneDrive.

    Returnerer URL til filen (browser-link).
    """
    token = get_access_token(client_id, refresh_token, tenant)
    # Sti i OneDrive: /drive/root:/MyFolder/file.md:/content
    path = onedrive_path.strip("/")
    target = f"{GRAPH_BASE}/me/drive/root:/{path}/{filename}:/content"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/markdown; charset=utf-8",
    }
    r = requests.put(target, headers=headers, data=content.encode("utf-8"), timeout=60)
    r.raise_for_status()
    item = r.json()
    web_url = item.get("webUrl", "")
    LOG.info("Uploaded til OneDrive: %s", web_url)
    return web_url
