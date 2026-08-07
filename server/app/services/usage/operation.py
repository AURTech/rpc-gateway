_OTHER_METHOD = '__other__'
_HTTP_FAMILIES = frozenset({'wallet', 'walletsolidity', 'v1'})
_V1_RESOURCES = frozenset({'accounts', 'assets', 'blocks', 'contracts', 'transactions'})
_V1_SUBRESOURCES = frozenset({'events', 'internal-transactions', 'tokens', 'transactions', 'trc10', 'trc20'})


def normalize_http_operation(verb: str, path: str) -> str:
    segments = [segment.casefold() for segment in path.strip('/').split('/') if segment]
    if len(segments) < 2 or segments[0] not in _HTTP_FAMILIES:
        return _OTHER_METHOD
    family = segments[0]
    if family == 'v1':
        resource = segments[1]
        if resource not in _V1_RESOURCES:
            return f'{verb.upper()} /v1/__other__'
        normalized = [family, resource]
        if len(segments) > 2:
            normalized.append('{id}')
        normalized.extend(segment if segment in _V1_SUBRESOURCES else '{id}' for segment in segments[3:])
    else:
        normalized = segments[:2]
        normalized.extend('{id}' for _segment in segments[2:])
    operation = f'{verb.upper()} /' + '/'.join(normalized)
    return operation if len(operation) <= 256 else _OTHER_METHOD
