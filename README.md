<p align="center">
  <img src="web/public/aurpay-logo.svg" width="96" alt="RPC Gateway">
</p>

<h1 align="center">RPC Gateway</h1>

<p align="center">
  A multi-tenant gateway for reliable access to blockchain RPC networks.
</p>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License"></a>
  <a href="https://github.com/AURTech/rpc-gateway/actions/workflows/ci.yml"><img src="https://github.com/AURTech/rpc-gateway/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white" alt="Python 3.13">
  <img src="https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white" alt="Next.js 16">
</p>

---

Connect applications through one stable endpoint per network and manage upstream RPC access from one place.

## Highlights

### Reliable delivery

- **Routing and resilience** — distribute requests across registered upstreams and keep traffic flowing when
  individual endpoints degrade or fail.
- **Response caching** — reuse eligible JSON-RPC responses to reduce upstream load and response time.

### Traffic governance

- **Traffic controls** — observe or enforce request limits globally and by IP, account or application.
- **Access management** — use console sessions, Google sign-in, scoped personal access tokens and application API
  keys.

### Operations

- **Usage insights** — track request volume by application, gateway, chain, network and method.
- **Provider integrations** — discover and synchronize upstream endpoints from Alchemy, QuickNode, Chainstack, dRPC
  and Tenderly.

## Quick start

### Prerequisites

Install Python 3.13 with [uv](https://docs.astral.sh/uv/) and Node 20.19+ with pnpm. Start PostgreSQL and Redis.

### Backend

```bash
cd server
make init
UV_ENV_FILE=../.env.test make migrate     # required — tables are never created automatically
uv run --env-file ../.env.test app        # http://127.0.0.1:18173
```

> [!IMPORTANT]
> Set `APP_API_KEY_MASTER_KEY` to at least 32 bytes in `.env.test` before starting the backend. Add an endpoint
> keyring before creating endpoints or providers.

See [`server/.env.example`](./server/.env.example) for the configuration contract and
[`server/README.md`](./server/README.md) for the backend architecture.

### Console

```bash
cd web
corepack enable
pnpm install
pnpm dev                                  # http://localhost:19341
```

## Supported networks

| Chain | Family | Networks | Transports |
|---|---|---|---|
| Ethereum | EVM | Mainnet (1), Sepolia (11155111) | JSON-RPC |
| Polygon | EVM | Mainnet (137), Amoy (80002) | JSON-RPC |
| BNB Smart Chain | EVM | Mainnet (56), Testnet (97) | JSON-RPC |
| Arbitrum | EVM | Mainnet (42161), Sepolia (421614) | JSON-RPC |
| Optimism | EVM | Mainnet (10), Sepolia (11155420) | JSON-RPC |
| Base | EVM | Mainnet (8453), Sepolia (84532) | JSON-RPC |
| Solana | SVM | Mainnet, Devnet | JSON-RPC |
| Bitcoin | UTXO | Mainnet, Testnet | JSON-RPC |
| Litecoin | UTXO | Mainnet, Testnet | JSON-RPC |
| TRON | TRON | Mainnet (728126428), Nile (3448148188) | JSON-RPC, HTTP API |

## Documentation

| Document | Covers |
|---|---|
| [`server/README.md`](./server/README.md) | Backend architecture and topic index |
| [`server/docs/architecture/`](./server/docs/architecture/) | Protocols, data planes, runtime state and platform |
| [`web/README.md`](./web/README.md) | Console architecture and development conventions |

## License

[Apache License 2.0](./LICENSE).
