-- Preserve the pre-System-Cache tables while letting the canonical migration run against
-- empty placeholders. Run with psql --single-transaction only after every RPC Gateway
-- process has stopped. The connection guard makes an accidental online cutover fail-fast.

DO $guard$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND pid <> pg_backend_pid()
          AND application_name LIKE 'rpc-gateway-%'
    ) THEN
        RAISE EXCEPTION 'RPC Gateway database connections are still active.';
    END IF;
    IF to_regclass('public.system_jsonrpc_cache_payload') IS NULL
       OR to_regclass('public.system_jsonrpc_cache_payload_lease') IS NULL THEN
        RAISE EXCEPTION 'Legacy System JSON-RPC Cache tables are unavailable.';
    END IF;
    IF to_regclass('public.system_jsonrpc_cache_payload_legacy') IS NOT NULL
       OR to_regclass('public.system_jsonrpc_cache_payload_lease_legacy') IS NOT NULL
       OR to_regclass('public.system_cache_payload') IS NOT NULL
       OR to_regclass('public.system_cache_payload_lease') IS NOT NULL THEN
        RAISE EXCEPTION 'System Cache cutover tables already exist.';
    END IF;
    IF to_regclass('public.tortoise_migrations') IS NOT NULL AND EXISTS (
        SELECT 1
        FROM tortoise_migrations
        WHERE app = 'models' AND name = '0008_system_cache_transport'
    ) THEN
        RAISE EXCEPTION 'System Cache transport migration is already applied.';
    END IF;
END
$guard$;

LOCK TABLE system_jsonrpc_cache_payload, system_jsonrpc_cache_payload_lease
    IN ACCESS EXCLUSIVE MODE NOWAIT;

ALTER TABLE system_jsonrpc_cache_payload RENAME TO system_jsonrpc_cache_payload_legacy;
ALTER SEQUENCE system_jsonrpc_cache_payload_id_seq RENAME TO sys_jsonrpc_cache_payload_legacy_id_seq;
ALTER TABLE system_jsonrpc_cache_payload_legacy
    RENAME CONSTRAINT system_jsonrpc_cache_payload_pkey TO system_jsonrpc_cache_payload_legacy_pkey;
ALTER TABLE system_jsonrpc_cache_payload_legacy
    RENAME CONSTRAINT uid_system_json_chain_61a00a TO uq_sys_jsonrpc_cache_payload_legacy;
ALTER TABLE system_jsonrpc_cache_payload_legacy
    RENAME CONSTRAINT chk_system_jsonrpc_cache_payload_size TO chk_sys_jsonrpc_cache_payload_legacy_size;
ALTER TABLE system_jsonrpc_cache_payload_legacy
    RENAME CONSTRAINT chk_system_jsonrpc_cache_stored_size TO chk_sys_jsonrpc_cache_payload_legacy_stored;
ALTER INDEX idx_system_jsonrpc_cache_payload_retention RENAME TO idx_sys_jsonrpc_cache_payload_legacy_retention;

ALTER TABLE system_jsonrpc_cache_payload_lease RENAME TO system_jsonrpc_cache_payload_lease_legacy;
ALTER SEQUENCE system_jsonrpc_cache_payload_lease_id_seq RENAME TO sys_jsonrpc_cache_lease_legacy_id_seq;
ALTER TABLE system_jsonrpc_cache_payload_lease_legacy
    RENAME CONSTRAINT system_jsonrpc_cache_payload_lease_pkey TO system_jsonrpc_cache_payload_lease_legacy_pkey;
ALTER TABLE system_jsonrpc_cache_payload_lease_legacy
    RENAME CONSTRAINT uid_system_json_chain_44ff7a TO uq_sys_jsonrpc_cache_lease_legacy;
ALTER INDEX idx_system_jsonrpc_cache_payload_lease_expiry RENAME TO idx_sys_jsonrpc_cache_lease_legacy_expiry;

CREATE UNLOGGED TABLE system_jsonrpc_cache_payload (
    id BIGSERIAL PRIMARY KEY,
    chain VARCHAR(32) NOT NULL,
    network VARCHAR(32) NOT NULL,
    method VARCHAR(256) NOT NULL,
    cache_key VARCHAR(40) NOT NULL,
    sequence BIGINT,
    payload BYTEA NOT NULL,
    payload_size INTEGER NOT NULL,
    fresh_until TIMESTAMPTZ,
    stale_until TIMESTAMPTZ,
    publisher_fence BIGINT NOT NULL,
    stored_at TIMESTAMPTZ NOT NULL,
    stored_size INTEGER NOT NULL,
    CONSTRAINT uid_system_json_chain_61a00a UNIQUE (chain, network, method, cache_key),
    CONSTRAINT chk_system_jsonrpc_cache_payload_size CHECK (payload_size >= 0),
    CONSTRAINT chk_system_jsonrpc_cache_stored_size CHECK (stored_size = octet_length(payload))
);
CREATE INDEX idx_system_jsonrpc_cache_payload_retention
    ON system_jsonrpc_cache_payload (chain, stored_at);

CREATE UNLOGGED TABLE system_jsonrpc_cache_payload_lease (
    id BIGSERIAL PRIMARY KEY,
    chain VARCHAR(32) NOT NULL,
    network VARCHAR(32) NOT NULL,
    method VARCHAR(256) NOT NULL,
    cache_key VARCHAR(40) NOT NULL,
    token VARCHAR(64) NOT NULL,
    fence BIGINT NOT NULL,
    lease_until TIMESTAMPTZ NOT NULL,
    CONSTRAINT uid_system_json_chain_44ff7a UNIQUE (chain, network, method, cache_key)
);
CREATE INDEX idx_system_jsonrpc_cache_payload_lease_expiry
    ON system_jsonrpc_cache_payload_lease (chain, lease_until);

DO $verify$
BEGIN
    IF (SELECT COUNT(*) FROM system_jsonrpc_cache_payload) <> 0
       OR (SELECT COUNT(*) FROM system_jsonrpc_cache_payload_lease) <> 0 THEN
        RAISE EXCEPTION 'System Cache migration placeholders must be empty.';
    END IF;
END
$verify$;
