from curl_cffi import requests

# FRED and multpl stall on plain Python TLS clients; impersonating a browser works.
_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session(impersonate="chrome")
    return _session


def get_text(url: str, timeout: float = 30) -> str:
    resp = session().get(url, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} for {url}")
    return resp.text
