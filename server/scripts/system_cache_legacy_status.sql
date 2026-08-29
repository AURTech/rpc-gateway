SELECT
    to_regclass('public.system_jsonrpc_cache_payload') AS jsonrpc_payload,
    to_regclass('public.system_jsonrpc_cache_payload_legacy') AS legacy_payload,
    to_regclass('public.system_cache_payload') AS system_payload,
    to_regclass('public.system_jsonrpc_cache_payload_lease') AS jsonrpc_lease,
    to_regclass('public.system_jsonrpc_cache_payload_lease_legacy') AS legacy_lease,
    to_regclass('public.system_cache_payload_lease') AS system_lease;

SELECT
    relation.relname AS table_name,
    pg_size_pretty(pg_total_relation_size(relation.oid)) AS total_size,
    statistics.n_live_tup AS estimated_rows
FROM pg_class AS relation
LEFT JOIN pg_stat_user_tables AS statistics ON statistics.relid = relation.oid
WHERE relation.relname IN (
    'system_jsonrpc_cache_payload',
    'system_jsonrpc_cache_payload_legacy',
    'system_cache_payload',
    'system_jsonrpc_cache_payload_lease',
    'system_jsonrpc_cache_payload_lease_legacy',
    'system_cache_payload_lease'
)
ORDER BY relation.relname;
