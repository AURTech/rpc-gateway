import ast
from pathlib import Path

from app.infra.db import (
    DEFAULT_DB_CONNECTION,
    SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
    SYSTEM_CACHE_RETENTION_DB_CONNECTION,
)
from tests.infra import build_test_orm_config

_SERVER_ROOT = Path(__file__).resolve().parents[1]
_DIRECT_TRANSACTION_IMPORT_ALLOWED = Path('app/infra/db.py')


def test_orm_config_registers_all_production_connection_groups() -> None:
    config = build_test_orm_config(f'test_{"0" * 32}')

    assert set(config['connections']) == {
        DEFAULT_DB_CONNECTION,
        SYSTEM_CACHE_RETENTION_DB_CONNECTION,
        SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
    }


def test_production_code_uses_the_named_transaction_wrapper() -> None:
    violations: list[str] = []
    for source_root in (_SERVER_ROOT / 'app', _SERVER_ROOT / 'jobs'):
        for path in source_root.rglob('*.py'):
            relative_path = path.relative_to(_SERVER_ROOT)
            tree = ast.parse(path.read_text(), filename=str(relative_path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or node.module != 'tortoise.transactions':
                    continue
                imported_names = {alias.name for alias in node.names}
                if 'in_transaction' in imported_names and relative_path != _DIRECT_TRANSACTION_IMPORT_ALLOWED:
                    violations.append(f'{relative_path}:{node.lineno}')

    assert violations == []
