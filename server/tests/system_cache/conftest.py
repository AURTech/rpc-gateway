from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from tests.infra import build_test_orm_config, create_schema, drop_schema
from tortoise import Tortoise


@pytest.fixture
async def orm_schema() -> AsyncGenerator[None]:
    schema = f'test_{uuid4().hex}'
    await create_schema(schema)
    try:
        await Tortoise.init(config=build_test_orm_config(schema))
        await Tortoise.generate_schemas(safe=False)
        yield
    finally:
        await Tortoise.close_connections()
        await drop_schema(schema)
