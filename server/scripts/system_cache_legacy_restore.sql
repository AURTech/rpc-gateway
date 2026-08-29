-- Restore the preserved tables when the canonical migration has not run, or after all
-- migrations have been reversed through 0008_system_cache_transport. The empty-table
-- guards prevent this rollback from discarding cache data written by a running service.

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
    IF to_regclass('public.system_jsonrpc_cache_payload_legacy') IS NULL
       OR to_regclass('public.system_jsonrpc_cache_payload_lease_legacy') IS NULL
       OR to_regclass('public.system_jsonrpc_cache_payload') IS NULL
       OR to_regclass('public.system_jsonrpc_cache_payload_lease') IS NULL THEN
        RAISE EXCEPTION 'System Cache rollback tables are unavailable.';
    END IF;
    IF to_regclass('public.system_cache_payload') IS NOT NULL
       OR to_regclass('public.system_cache_payload_lease') IS NOT NULL THEN
        RAISE EXCEPTION 'Reverse the System Cache transport migration before restoring legacy tables.';
    END IF;
    IF (SELECT COUNT(*) FROM system_jsonrpc_cache_payload) <> 0
       OR (SELECT COUNT(*) FROM system_jsonrpc_cache_payload_lease) <> 0 THEN
        RAISE EXCEPTION 'System Cache rollback placeholders are not empty.';
    END IF;
END
$guard$;

LOCK TABLE system_jsonrpc_cache_payload, system_jsonrpc_cache_payload_lease,
    system_jsonrpc_cache_payload_legacy, system_jsonrpc_cache_payload_lease_legacy
    IN ACCESS EXCLUSIVE MODE NOWAIT;

DROP TABLE system_jsonrpc_cache_payload, system_jsonrpc_cache_payload_lease;

ALTER TABLE system_jsonrpc_cache_payload_legacy RENAME TO system_jsonrpc_cache_payload;
ALTER SEQUENCE sys_jsonrpc_cache_payload_legacy_id_seq RENAME TO system_jsonrpc_cache_payload_id_seq;
ALTER TABLE system_jsonrpc_cache_payload
    RENAME CONSTRAINT system_jsonrpc_cache_payload_legacy_pkey TO system_jsonrpc_cache_payload_pkey;
ALTER TABLE system_jsonrpc_cache_payload
    RENAME CONSTRAINT uq_sys_jsonrpc_cache_payload_legacy TO uid_system_json_chain_61a00a;
ALTER TABLE system_jsonrpc_cache_payload
    RENAME CONSTRAINT chk_sys_jsonrpc_cache_payload_legacy_size TO chk_system_jsonrpc_cache_payload_size;
ALTER TABLE system_jsonrpc_cache_payload
    RENAME CONSTRAINT chk_sys_jsonrpc_cache_payload_legacy_stored TO chk_system_jsonrpc_cache_stored_size;
ALTER INDEX idx_sys_jsonrpc_cache_payload_legacy_retention RENAME TO idx_system_jsonrpc_cache_payload_retention;

ALTER TABLE system_jsonrpc_cache_payload_lease_legacy RENAME TO system_jsonrpc_cache_payload_lease;
ALTER SEQUENCE sys_jsonrpc_cache_lease_legacy_id_seq RENAME TO system_jsonrpc_cache_payload_lease_id_seq;
ALTER TABLE system_jsonrpc_cache_payload_lease
    RENAME CONSTRAINT system_jsonrpc_cache_payload_lease_legacy_pkey TO system_jsonrpc_cache_payload_lease_pkey;
ALTER TABLE system_jsonrpc_cache_payload_lease
    RENAME CONSTRAINT uq_sys_jsonrpc_cache_lease_legacy TO uid_system_json_chain_44ff7a;
ALTER INDEX idx_sys_jsonrpc_cache_lease_legacy_expiry RENAME TO idx_system_jsonrpc_cache_payload_lease_expiry;
