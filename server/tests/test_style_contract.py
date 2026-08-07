import ast
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PYTHON_CODE_DIRS = [
    ROOT / 'app',
    ROOT / 'jobs',
    ROOT / 'migrations',
    ROOT / 'tests',
]

RUNTIME_CODE_DIRS = [
    ROOT / 'app',
    ROOT / 'jobs',
    ROOT / 'migrations',
]

ENV_ACCESS_ALLOWED = {
    ROOT / 'app/core/config.py',
    ROOT / 'app/core/bootstrap.py',
}

DISALLOWED_NAME_PARTS = {'resolve', 'ensure', 'install'}
IDENTIFIER_PART_RE = re.compile(r'[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|\d+')


def _python_files(roots: list[Path]) -> list[Path]:
    return [path for root in roots for path in sorted(root.rglob('*.py'))]


def _relative(path: Path, node: ast.AST | None = None) -> str:
    suffix = f':{node.lineno}' if node is not None and hasattr(node, 'lineno') else ''
    return f'{path.relative_to(ROOT)}{suffix}'


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        if parent is None:
            return node.attr
        return f'{parent}.{node.attr}'
    return None


def _imported_names(tree: ast.Module, *, module: str, name: str) -> set[str]:
    imported: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module != module:
            continue
        for alias in node.names:
            if alias.name == name:
                imported.add(alias.asname or alias.name)
    return imported


def _identifier_parts(value: str) -> set[str]:
    parts: set[str] = set()
    for chunk in value.split('_'):
        parts.update(part.lower() for part in IDENTIFIER_PART_RE.findall(chunk))
    return parts


def _has_disallowed_part(value: str) -> bool:
    return bool(_identifier_parts(value) & DISALLOWED_NAME_PARTS)


def _target_names(node: ast.AST) -> list[ast.Name]:
    if isinstance(node, ast.Name):
        return [node]
    if isinstance(node, ast.Tuple | ast.List):
        names: list[ast.Name] = []
        for item in node.elts:
            names.extend(_target_names(item))
        return names
    return []


def _contains_disallowed_text(value: str) -> bool:
    words = {word.lower() for word in re.findall(r'[A-Za-z]+', value)}
    return bool(words & DISALLOWED_NAME_PARTS)


def _function_line_count(path: Path, function_name: str, *, class_name: str | None = None) -> int:
    tree = ast.parse(path.read_text(), filename=str(path))
    candidates: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    search_root: ast.AST = tree
    if class_name is not None:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                search_root = node
                break
        else:
            raise AssertionError(f'{class_name} not found in {path.relative_to(ROOT)}')
    for node in ast.walk(search_root):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function_name:
            candidates.append(node)
    if not candidates:
        raise AssertionError(f'{function_name} not found in {path.relative_to(ROOT)}')
    if len(candidates) != 1:
        raise AssertionError(f'{function_name} is ambiguous in {path.relative_to(ROOT)}')
    node = candidates[0]
    assert node.end_lineno is not None
    return node.end_lineno - node.lineno + 1


def test_typing_cast_is_not_used() -> None:
    offenders: list[str] = []
    for path in _python_files(PYTHON_CODE_DIRS):
        tree = ast.parse(path.read_text(), filename=str(path))
        cast_names = _imported_names(tree, module='typing', name='cast')
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == 'typing'
                and any(alias.name == 'cast' for alias in node.names)
            ):
                offenders.append(_relative(path, node))
            if isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                if call_name == 'typing.cast' or call_name in cast_names:
                    offenders.append(_relative(path, node))

    assert offenders == []


def test_runtime_code_reads_environment_only_in_config_bootstrap() -> None:
    offenders: list[str] = []
    for path in _python_files(RUNTIME_CODE_DIRS):
        if path in ENV_ACCESS_ALLOWED:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        os_aliases: set[str] = set()
        getenv_aliases: set[str] = set()
        environ_aliases: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == 'os':
                        os_aliases.add(alias.asname or alias.name)
            if isinstance(node, ast.ImportFrom) and node.module == 'os':
                for alias in node.names:
                    if alias.name == 'getenv':
                        getenv_aliases.add(alias.asname or alias.name)
                    if alias.name == 'environ':
                        environ_aliases.add(alias.asname or alias.name)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                if call_name in {f'{alias}.getenv' for alias in os_aliases} or call_name in getenv_aliases:
                    offenders.append(_relative(path, node))
            if isinstance(node, ast.Attribute):
                attr_name = _call_name(node)
                if attr_name in {f'{alias}.environ' for alias in os_aliases}:
                    offenders.append(_relative(path, node))
            if isinstance(node, ast.Name) and node.id in environ_aliases:
                offenders.append(_relative(path, node))

    assert offenders == []


def test_datetime_uses_timezone_aware_utc() -> None:
    offenders: list[str] = []
    for path in _python_files(RUNTIME_CODE_DIRS):
        tree = ast.parse(path.read_text(), filename=str(path))
        datetime_modules: set[str] = set()
        datetime_classes = _imported_names(tree, module='datetime', name='datetime')
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == 'datetime':
                        datetime_modules.add(alias.asname or alias.name)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node.func)
            if call_name in {f'{name}.utcnow' for name in datetime_classes}:
                offenders.append(_relative(path, node))
            if call_name in {f'{name}.datetime.utcnow' for name in datetime_modules}:
                offenders.append(_relative(path, node))
            now_calls = {f'{name}.now' for name in datetime_classes} | {f'{name}.datetime.now' for name in datetime_modules}
            if call_name in now_calls and not node.args and not any(keyword.arg == 'tz' for keyword in node.keywords):
                offenders.append(_relative(path, node))

    assert offenders == []


def test_runtime_function_names_are_short() -> None:
    offenders: list[str] = []
    for path in _python_files(RUNTIME_CODE_DIRS):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name.startswith('__'):
                continue
            name_parts = [part for part in node.name.split('_') if part]
            if len(name_parts) > 4:
                offenders.append(f'{_relative(path, node)}:{node.name}')

    assert offenders == []


def test_google_oauth_callback_route_stays_thin() -> None:
    line_count = _function_line_count(ROOT / 'app/api/v2/auth/auth.py', 'google_callback')

    assert line_count <= 35


def test_python_names_avoid_disallowed_generic_words() -> None:
    offenders: list[str] = []
    for path in _python_files(PYTHON_CODE_DIRS):
        if _has_disallowed_part(path.stem):
            offenders.append(str(path.relative_to(ROOT)))
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                if _has_disallowed_part(node.name):
                    offenders.append(f'{_relative(path, node)}:{node.name}')
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    args = [
                        *node.args.posonlyargs,
                        *node.args.args,
                        *node.args.kwonlyargs,
                    ]
                    if node.args.vararg is not None:
                        args.append(node.args.vararg)
                    if node.args.kwarg is not None:
                        args.append(node.args.kwarg)
                    for arg in args:
                        if _has_disallowed_part(arg.arg):
                            offenders.append(f'{_relative(path, arg)}:{arg.arg}')
            elif isinstance(node, ast.alias):
                local_name = node.asname or node.name.rsplit('.', 1)[-1]
                if _has_disallowed_part(local_name):
                    offenders.append(f'{_relative(path, node)}:{local_name}')
            elif isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for name in _target_names(target):
                        if _has_disallowed_part(name.id):
                            offenders.append(f'{_relative(path, name)}:{name.id}')
            elif isinstance(node, ast.NamedExpr | ast.For | ast.AsyncFor):
                for name in _target_names(node.target):
                    if _has_disallowed_part(name.id):
                        offenders.append(f'{_relative(path, name)}:{name.id}')
            elif isinstance(node, ast.With | ast.AsyncWith):
                for item in node.items:
                    if item.optional_vars is None:
                        continue
                    for name in _target_names(item.optional_vars):
                        if _has_disallowed_part(name.id):
                            offenders.append(f'{_relative(path, name)}:{name.id}')

    assert offenders == []


def test_imports_are_absolute() -> None:
    offenders: list[str] = []
    for path in _python_files(PYTHON_CODE_DIRS):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                offenders.append(_relative(path, node))

    assert offenders == []


def test_import_aliases_do_not_use_private_prefix() -> None:
    offenders: list[str] = []
    for path in _python_files(PYTHON_CODE_DIRS):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                for alias in node.names:
                    if alias.asname is not None and alias.asname.startswith('_'):
                        offenders.append(_relative(path, node))

    assert offenders == []


def test_python_comments_and_docstrings_avoid_disallowed_generic_words() -> None:
    offenders: list[str] = []
    for path in _python_files(PYTHON_CODE_DIRS):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            docstring = None
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                docstring = ast.get_docstring(node)
            if docstring and _contains_disallowed_text(docstring):
                offenders.append(_relative(path, node))
        with path.open('rb') as file:
            for token in tokenize.tokenize(file.readline):
                if token.type == tokenize.COMMENT and _contains_disallowed_text(token.string):
                    offenders.append(f'{path.relative_to(ROOT)}:{token.start[0]}')

    assert offenders == []


def test_services_do_not_depend_on_http_exception() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / 'app/services').rglob('*.py')):
        tree = ast.parse(path.read_text(), filename=str(path))
        http_exception_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in {'fastapi', 'starlette.exceptions'}:
                for alias in node.names:
                    if alias.name == 'HTTPException':
                        http_exception_names.add(alias.asname or alias.name)
                        offenders.append(_relative(path, node))
            if isinstance(node, ast.Raise) and node.exc is not None:
                raised_name = _call_name(node.exc.func) if isinstance(node.exc, ast.Call) else _call_name(node.exc)
                if raised_name in http_exception_names or raised_name == 'HTTPException':
                    offenders.append(_relative(path, node))

    assert offenders == []


def test_endpoint_domains_do_not_import_jsonrpc_route_data() -> None:
    offenders: list[str] = []
    roots = [ROOT / 'app/services/endpoint', ROOT / 'app/services/provider']
    forbidden_prefixes = ('app.orm.jsonrpc_route', 'app.services.jsonrpc_route')
    for path in _python_files(roots):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None and node.module.startswith(forbidden_prefixes):
                offenders.append(_relative(path, node))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_prefixes):
                        offenders.append(_relative(path, node))

    assert offenders == []


def test_jsonrpc_forwarding_policies_remain_independent() -> None:
    forwarding = ROOT / 'app/services/jsonrpc_forwarding'
    forbidden_by_file = {
        'selector.py': ('app.services.jsonrpc_forwarding.circuit', 'app.services.runtime_state.circuit'),
        'health.py': ('app.services.jsonrpc_forwarding.circuit', 'app.services.jsonrpc_forwarding.retry'),
        'circuit.py': ('app.services.jsonrpc_forwarding.health', 'app.services.jsonrpc_forwarding.retry'),
        'retry.py': ('app.services.jsonrpc_forwarding.circuit', 'app.services.jsonrpc_forwarding.health'),
    }
    offenders: list[str] = []
    for filename, forbidden_prefixes in forbidden_by_file.items():
        path = forwarding / filename
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None and node.module.startswith(forbidden_prefixes):
                offenders.append(_relative(path, node))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_prefixes):
                        offenders.append(_relative(path, node))

    assert offenders == []


def test_util_layer_does_not_depend_on_services_or_orm() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / 'app/util').rglob('*.py')):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in tree.body:
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith(('app.services', 'app.orm', 'app.model'))
            ):
                offenders.append(_relative(path, node))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(('app.services', 'app.orm', 'app.model')):
                        offenders.append(_relative(path, node))

    assert offenders == []


def test_core_layer_does_not_depend_on_services_or_orm() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / 'app/core').rglob('*.py')):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in tree.body:
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith(('app.services', 'app.orm'))
            ):
                offenders.append(_relative(path, node))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(('app.services', 'app.orm')):
                        offenders.append(_relative(path, node))

    assert offenders == []


def _base_name(node: ast.AST) -> str | None:
    name = _call_name(node)
    if name is None:
        return None
    return name.rsplit('.', 1)[-1]


def test_orm_indexes_are_named() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / 'app/orm').rglob('*.py')):
        tree = ast.parse(path.read_text(), filename=str(path))
        for class_node in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
            for meta_node in [node for node in class_node.body if isinstance(node, ast.ClassDef) and node.name == 'Meta']:
                for assign in [node for node in meta_node.body if isinstance(node, ast.Assign)]:
                    if not any(isinstance(target, ast.Name) and target.id == 'indexes' for target in assign.targets):
                        continue
                    if not isinstance(assign.value, ast.Tuple | ast.List):
                        offenders.append(_relative(path, assign))
                        continue
                    for index_node in assign.value.elts:
                        if not isinstance(index_node, ast.Call) or _base_name(index_node.func) != 'Index':
                            offenders.append(_relative(path, index_node))
                            continue
                        name_keywords = [keyword.value for keyword in index_node.keywords if keyword.arg == 'name']
                        if not name_keywords or not isinstance(name_keywords[0], ast.Constant):
                            offenders.append(_relative(path, index_node))
                            continue
                        index_name = name_keywords[0].value
                        if not isinstance(index_name, str) or not index_name.startswith('idx_'):
                            offenders.append(_relative(path, index_node))

    assert offenders == []
