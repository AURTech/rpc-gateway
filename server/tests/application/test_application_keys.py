from datetime import UTC, datetime, timedelta

import pytest
from app.api.v2.application.application import router
from app.model.application import AppKeyState
from app.orm.application import AppApiKey
from app.services.application.application import ApplicationManager
from app.services.application.crypto import encrypt_api_key
from fastapi.routing import APIRoute


@pytest.mark.parametrize(
    ('expires_at', 'revoked_at', 'state'),
    [
        (None, None, AppKeyState.ACTIVE),
        (timedelta(hours=1), None, AppKeyState.GRACE),
        (timedelta(hours=-1), None, AppKeyState.EXPIRED),
        (None, timedelta(minutes=-1), AppKeyState.REVOKED),
    ],
)
def test_app_key_item_exposes_value_for_every_state(
    expires_at: timedelta | None,
    revoked_at: timedelta | None,
    state: AppKeyState,
) -> None:
    now = datetime.now(UTC)
    app_id = 'app-1'
    key_id = 'key-1'
    api_key = 'ak_test-key'
    key = AppApiKey(
        id=key_id,
        api_key_digest='digest',
        encrypted_api_key=encrypt_api_key(api_key, app_id=app_id, key_id=key_id),
        expires_at=now + expires_at if expires_at is not None else None,
        revoked_at=now + revoked_at if revoked_at is not None else None,
        created_at=now,
        modified_at=now,
    )
    key.app_id = app_id

    item = ApplicationManager._to_key_item(key, now=now)

    assert item.api_key == api_key
    assert item.state is state


def test_app_key_reveal_route_is_removed() -> None:
    paths = {route.path for route in router.routes if isinstance(route, APIRoute)}

    assert not any(path.endswith('/reveal') for path in paths)
