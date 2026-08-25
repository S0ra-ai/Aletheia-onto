# Configuration

> Every environment variable: runtime and security, platform database, SSO, thresholds.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

All tunables live in [`backend/ontology_platform/config.py`](../backend/ontology_platform/config.py)
and every one is overridable by environment variable.

## Runtime and security

| Variable | Purpose | Default |
|---|---|---|
| `ONTOLOGY_ADMIN_USERNAME` | Bootstrap administrator username | `admin` |
| `ONTOLOGY_ADMIN_PASSWORD` | Bootstrap administrator password | Unset: a random one is generated and printed once |
| `ONTOLOGY_SESSION_TTL_HOURS` | Session lifetime | `12` |
| `ONTOLOGY_AUTH_DISABLED` | Set to `1` to disable all authentication. **Local development only** | Unset (authentication on) |
| `ONTOLOGY_ALLOWED_ORIGINS` | Comma-separated CORS origins | `http://127.0.0.1:3000,http://localhost:3000` |

Only the documented opt-in values disable authentication. A typo
(`ONTOLOGY_AUTH_DISABLED=ture`) leaves it **on** — guessing at intent here would mean
guessing in favour of exposure.

## SSO

SSO is enabled only when all three are set. A half-configured deployment behaves as
"SSO off", never as "SSO on and accepting anything".

| Variable | Purpose | Default |
|---|---|---|
| `ONTOLOGY_SSO_ISSUER` | Expected `iss`; a mismatch is rejected | Unset (SSO off) |
| `ONTOLOGY_SSO_AUDIENCE` | Expected `aud`, so a token minted for another service is not reused here | Unset (SSO off) |
| `ONTOLOGY_SSO_SECRET` | Verification key. In the environment rather than the database — a credential in the database is a credential in every backup of it | Unset (SSO off) |
| `ONTOLOGY_SSO_ALGORITHM` | `HS256` / `HS384` / `HS512`. **Taken from configuration, never from the token header** | `HS256` |
| `ONTOLOGY_SSO_GROUP_CLAIM` | Claim carrying group membership | `groups` |
| `ONTOLOGY_SSO_USERNAME_CLAIM` | Claim carrying the user identifier | `sub` |

**The provider asserts identity; the platform decides authority.** An OIDC token can carry
any claim the provider chooses, including `role: admin` — trusting it would move this
platform's authorization boundary into someone else's configuration. So a claim never
becomes a capability: an administrator maps provider group to platform role, and an identity
whose groups map to nothing is **refused outright** rather than given a default role. A
default sounds safe and is not: it silently grants every employee in the directory read
access to every business object the platform can reach.

Local accounts are not replaced. "The IdP is down so nobody can fix the IdP integration" is
a real outage shape, so the bootstrap admin keeps its password.

## Platform database

| Variable | Purpose | Default |
|---|---|---|
| `ONTOLOGY_PLATFORM_DB_TYPE` | `sqlite` / `mysql` / `postgresql` | `sqlite` |
| `ONTOLOGY_PLATFORM_DB_URI` | Platform database connection string | Local SQLite file |
| `ONTOLOGY_PLATFORM_DB_FILE` | The SQLite platform database **file** (wins over `ONTOLOGY_DATA_DIR`) | Unset |
| `ONTOLOGY_DATA_DIR` | The **directory** holding `platform.sqlite3` | `data/` in a checkout, `~/.aletheia` otherwise |
| `ONTOLOGY_PLATFORM_SQLITE_BUSY_TIMEOUT_MS` | SQLite `busy_timeout` | `5000` |

> **`serve` uses the same database as every other command.**
> `aletheia serve --platform-db X` passes `X` to the served process and prints the path it
> resolved. It could not before: `uvicorn` imports the app in a fresh process that can only
> read the environment, so `serve --platform-db X` served a *different* database — and the
> symptom was an empty ontology list, which reads as "my data did not save". The
> investigation then starts at the writes, and the one thing it does not look like is a path
> mismatch.

## Thresholds and naming

| Group | Contents | Env prefix |
|---|---|---|
| `QUERY_LIMITS` | Page size caps, consistency sampling, enum-detection distinct bounds | `ONTOLOGY_DEFAULT_PAGE_SIZE`, `ONTOLOGY_MAX_PAGE_SIZE`, `ONTOLOGY_ENUM_*` |
| `MAPPING_CONFIDENCE` | Mapping candidate confidence (blueprint / structural / vocabulary / weak) | `ONTOLOGY_CONFIDENCE_*` |
| `ANSWER_CONFIDENCE` | Answer confidence | `ONTOLOGY_ANSWER_CONFIDENCE_*` |
| `RESOLUTION_CONFIDENCE` | Instance-resolution confidence and boosts | `ONTOLOGY_RESOLUTION_*` |
| `SEMANTIC_ASSET_NAMING` | IRI namespaces for JSON-LD / Turtle / OWL | `ONTOLOGY_VOCABULARY_BASE_IRI`, `ONTOLOGY_ASSET_BASE_IRI` |
| `MODEL_PROVIDER_DEFAULTS` | Model endpoint, model name, timeout, service tier | `OPENROUTER_*` |

With no `OPENROUTER_API_KEY` configured, question answering and draft generation fall back
to a local heuristic — the platform keeps working rather than failing.

## Related

- [Self-hosted deployment](deployment.md) — and `aletheia preflight`, which blocks unsafe combinations
- [Model endpoints](model-endpoints.md) — Azure OpenAI, vLLM, gateways
