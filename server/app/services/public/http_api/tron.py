import orjson

from app.model.public import PublicHttpApiRequest, PublicHttpApiResult, TronHttpApiFamily

_ALLOWED_HEADERS = frozenset({'accept', 'content-type'})


class TronHttpApiAdapter:
    @staticmethod
    def parse(
        method: str,
        raw_path: str,
        *,
        headers: list[tuple[str, str]],
        query: list[tuple[str, str]],
        body: bytes,
    ) -> PublicHttpApiRequest | PublicHttpApiResult:
        path = raw_path.strip('/')
        segments = path.split('/') if path else []
        path_key: str | None = None
        if segments and segments[0].casefold() not in {'wallet', 'walletsolidity', 'v1'}:
            path_key = segments.pop(0)
        if len(segments) < 2 or segments[0].casefold() not in {'wallet', 'walletsolidity', 'v1'}:
            family = TronHttpApiFamily.V1 if segments and segments[0].casefold() == 'v1' else TronHttpApiFamily.WALLET
            return TronHttpApiAdapter.error(family, 404, 'Gateway or path not found.')
        family = TronHttpApiFamily.V1 if segments[0].casefold() == 'v1' else TronHttpApiFamily.WALLET
        if method.upper() not in {'GET', 'POST'}:
            return TronHttpApiAdapter.error(family, 405, 'Method not allowed.')
        forwarded_headers = {name: value for name, value in headers if name.casefold() in _ALLOWED_HEADERS}
        return PublicHttpApiRequest(
            method=method.upper(),
            path='/' + '/'.join(segments),
            family=family,
            path_key=path_key,
            headers=forwarded_headers,
            query=tuple(query),
            body=body,
        )

    @staticmethod
    def error(family: TronHttpApiFamily, status_code: int, message: str) -> PublicHttpApiResult:
        if family is TronHttpApiFamily.V1:
            payload = {'Success': False, 'Error': message, 'StatusCode': status_code}
        else:
            payload = {'Error': message}
        headers: tuple[tuple[str, str], ...] = (('Content-Type', 'application/json'),)
        if status_code == 429:
            headers += (('Retry-After', '1'),)
        return PublicHttpApiResult(status_code=status_code, body=orjson.dumps(payload), headers=headers)
