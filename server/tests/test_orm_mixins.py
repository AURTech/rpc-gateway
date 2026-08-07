import warnings

from app.orm.mixin import GuidMixin, NANOIDField, TimestampMixin
from tests.infra import patch_tortoise_migration_recorder
from tortoise import fields
from tortoise.migrations.recorder import MigrationRecorder


def test_nanoid_field_generates_default_for_primary_key() -> None:
    field = NANOIDField(primary_key=True)

    assert callable(field.default)
    value = field.default()
    assert len(value) == 21
    assert value.isalnum()


def test_nanoid_field_respects_explicit_default() -> None:
    field = NANOIDField(primary_key=True, default='fixed-id')

    assert field.default == 'fixed-id'


def test_timestamp_mixin_fields_use_expected_auto_timestamps() -> None:
    assert isinstance(TimestampMixin.created_at, fields.DatetimeField)
    assert TimestampMixin.created_at.auto_now_add is True
    assert TimestampMixin.modified_at.auto_now is True
    assert TimestampMixin.deleted_at.null is True


def test_guid_mixin_is_abstract_with_nanoid_primary_key() -> None:
    assert GuidMixin._meta.abstract is True
    assert GuidMixin._meta.pk_attr == 'id'
    assert isinstance(GuidMixin._meta.pk, NANOIDField)


def test_migration_recorder_uses_primary_key_without_deprecation_warning() -> None:
    patch_tortoise_migration_recorder()

    with warnings.catch_warnings():
        warnings.simplefilter('error', DeprecationWarning)
        recorder = MigrationRecorder(None)

    assert recorder.model._meta.pk_attr == 'id'
