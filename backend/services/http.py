import ssl
from functools import lru_cache


@lru_cache(maxsize=1)
def tls_context() -> ssl.SSLContext:
    """One TLS context for every httpx client, built once.

    By default httpx builds a fresh context, loading every trusted certificate,
    for each client it creates. Measured on this machine: ~180 ms of blocking
    work per client, more than the Ollama call itself, and it froze the event
    loop under load. A shared context makes a client cost ~2 ms.

    Verification stays fully on: this is Python's standard secure default
    (certificate and host name are checked).
    """
    return ssl.create_default_context()
