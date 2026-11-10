"""Shared OctoPrint configuration and authenticated request construction."""

import os
from pathlib import Path

from dotenv import dotenv_values
from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkRequest


def read_octoprint_config():
    try:
        config = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
        address = os.environ.get("OCTOPRINT_URL", config.get("OCTOPRINT_URL") or "").strip()
        key = os.environ.get("OCTOPRINT_API_KEY", config.get("OCTOPRINT_API_KEY") or "").strip()
    except (OSError, UnicodeError) as error:
        raise ValueError("Unable to read printer configuration.") from error
    if not address or not key:
        raise ValueError("OctoPrint is not configured. Set OCTOPRINT_URL and OCTOPRINT_API_KEY in .env.")
    url = QUrl(address)
    if (not url.isValid() or url.scheme() not in ("http", "https") or not url.host()
            or url.userInfo() or url.hasQuery() or url.hasFragment()
            or not key.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in key)):
        raise ValueError("Invalid OctoPrint address or API key configuration.")
    url.setPath(url.path().rstrip("/"))
    return url, key


def make_octoprint_request(config, path, *, query=""):
    """Append a decoded endpoint path without modifying the configured base URL."""
    base_url, key = config
    url = QUrl(base_url)
    url.setPath(url.path() + path, QUrl.ParsingMode.DecodedMode)
    if query:
        url.setQuery(query)
    request = QNetworkRequest(url)
    request.setRawHeader(b"X-Api-Key", key.encode("ascii"))
    request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
    return request
