import ipaddress

from starlette.requests import HTTPConnection


def _to_ip_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _forwarded_ip(connection: HTTPConnection) -> str | None:
    """Read the client address overwritten by the sole trusted ingress proxy.

    Deployment must prevent direct API access and replace client-supplied
    X-Real-IP headers. This function validates header shape, not peer identity.
    """
    forwarded_values = connection.headers.getlist('x-real-ip')
    if len(forwarded_values) != 1:
        return None
    forwarded = forwarded_values[0]
    if not forwarded or ',' in forwarded:
        return None
    forwarded_ip = forwarded.strip()
    if not forwarded_ip or _to_ip_address(forwarded_ip) is None:
        return None
    return forwarded_ip


def client_ip(connection: HTTPConnection) -> str | None:
    peer_ip = connection.client.host if connection.client else None
    return _forwarded_ip(connection) or peer_ip


def country(connection: HTTPConnection) -> str | None:
    if _forwarded_ip(connection) is None:
        return None
    country_code = connection.headers.get('cf-ipcountry')
    if not country_code:
        return None
    country_code = country_code.strip()
    return country_code or None
