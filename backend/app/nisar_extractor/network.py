from __future__ import annotations

import socket

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def configure_ipv4(force: bool = True) -> None:
    """Work around this Fedora host's known IPv6 route timeout when requested."""
    if not force:
        return
    import urllib3.util.connection

    urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET


def requests_session(retries: int = 3) -> requests.Session:
    """Requests session with safe retries for GET/HEAD only; auth comes from netrc."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
