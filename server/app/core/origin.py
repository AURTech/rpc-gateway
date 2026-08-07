from urllib.parse import urlsplit, urlunsplit


def normalize_origin(value: str) -> str:
    origin = value.strip()
    parts = urlsplit(origin)
    if parts.scheme not in {'http', 'https'} or not parts.hostname:
        raise ValueError('Origin must use http:// or https://.')
    if parts.username is not None or parts.password is not None:
        raise ValueError('Origin must not contain user information.')
    if parts.path not in {'', '/'} or parts.query or parts.fragment:
        raise ValueError('Origin must contain only scheme, host, and optional port.')

    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError('Origin port is invalid.') from exc

    hostname = parts.hostname.rstrip('.').encode('idna').decode('ascii').lower()
    if not hostname:
        raise ValueError('Origin host is invalid.')
    formatted_host = f'[{hostname}]' if ':' in hostname else hostname
    default_port = 80 if parts.scheme == 'http' else 443
    netloc = formatted_host if port in {None, default_port} else f'{formatted_host}:{port}'
    return urlunsplit((parts.scheme, netloc, '', '', ''))
