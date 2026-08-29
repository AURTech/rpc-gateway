import ast

from app.core.config import PROJECT_ROOT


def _imports(package: str) -> set[str]:
    imported: set[str] = set()
    for path in (PROJECT_ROOT / package).rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
    return imported


def _assert_no_fragment(imports: set[str], fragments: tuple[str, ...]) -> None:
    violations = sorted(name for name in imports if any(fragment in name for fragment in fragments))
    assert violations == []


def test_system_cache_core_is_protocol_neutral() -> None:
    imports = _imports('app/services/system_cache') | _imports('app/model/system_cache')

    _assert_no_fragment(imports, ('jsonrpc', 'http_api', 'app.model.public', 'app.services.public'))


def test_http_and_jsonrpc_cache_modules_do_not_cross_import() -> None:
    http_imports = _imports('app/services/system_http_api_cache') | _imports('app/model/system_http_api_cache')
    jsonrpc_imports = _imports('app/services/system_jsonrpc_cache') | _imports('app/model/system_jsonrpc_cache')

    _assert_no_fragment(http_imports, ('jsonrpc',))
    _assert_no_fragment(jsonrpc_imports, ('http_api',))
