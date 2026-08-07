#!/usr/bin/env python3
"""Create a fresh database schema from the registered ORM models."""

import asyncio

from app.infra.db import TORTOISE_ORM
from tortoise import Tortoise


async def _run() -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        await Tortoise.generate_schemas(safe=False)
    finally:
        await Tortoise.close_connections()


def main() -> None:
    asyncio.run(_run())


if __name__ == '__main__':
    main()
