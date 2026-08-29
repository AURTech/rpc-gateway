# System Cache legacy-preserving cutover

This runbook preserves the pre-upgrade cache tables for rollback while the canonical migrations create empty System
Cache tables. It does not make old payloads reusable: the cache digest contract changed and the old rows do not retain
enough request identity to rebuild every digest.

## Required environment update

Rename the two production keys while preserving their values:

```dotenv
SYSTEM_CACHE_ENABLED=true
SYSTEM_CACHE_REDIS_TTL_MS=1000
```

Remove `SYSTEM_JSONRPC_CACHE_ENABLED` and `SYSTEM_JSONRPC_CACHE_REDIS_TTL_MS`. Leaving either old key in the environment
causes the new Config model to reject startup.

The following additions are optional:

- `AURPAY_OIDC_ISSUER`, `AURPAY_OIDC_CLIENT_ID`, `AURPAY_OIDC_CLIENT_SECRET`, and `AURPAY_OIDC_REDIRECT_URI` are required
  only when AurPay OIDC login is enabled.
- `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` and `OTEL_AUTH` belong to the Compose `fastlog-watcher`; they are not required by the
  existing systemd API, Worker, or Scheduler services.
- All other new Config fields have validated defaults and do not need to be copied into production merely because they
  appear in `.env.example`.

Validate the updated environment with the prepared runtime before stopping services:

```bash
ENV_FILE=.env .venv.next/bin/python -c \
  "from app.core.config import CONF; from app import init_app; init_app(); print(CONF.APP_ENV)"
```

## Cutover

1. Stop API, Worker, and Scheduler. Do not run the prepare SQL while any RPC Gateway database connection remains.
2. Preserve the old tables and create empty migration placeholders in one transaction:

   ```bash
   psql "$ORM_URL" -X -v ON_ERROR_STOP=1 --single-transaction \
     -f scripts/system_cache_legacy_prepare.sql
   ```

3. Run the canonical migrations through `0015_route_aware_usage`.
4. Activate the prepared runtime and updated environment, then start Scheduler, Worker, and API.
5. Check table state with `scripts/system_cache_legacy_status.sql`, API health, migration history, cache growth, and error
   rates.
6. Keep the `*_legacy` tables until the rollback window has passed. Dropping them requires separate confirmation.

## Rollback

1. Stop every new RPC Gateway process.
2. Downgrade all migrations through `0008_system_cache_transport`. Its reverse migration empties and restores the
   placeholder table names.
3. Restore the preserved tables:

   ```bash
   psql "$ORM_URL" -X -v ON_ERROR_STOP=1 --single-transaction \
     -f scripts/system_cache_legacy_restore.sql
   ```

4. Restore the previous runtime and environment, then start the services.

The restore script refuses to run when Gateway connections are active, when the canonical System Cache tables still
exist, or when rollback placeholders contain rows.
