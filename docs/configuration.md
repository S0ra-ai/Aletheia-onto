# Configuration

> Every environment variable: runtime and security, platform database, SSO, thresholds.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

All tunables live in [`backend/ontology_platform/config.py`](../backend/ontology_platform/config.py)
and every one is overridable by environment variable.

## Runtime and security

| Variable | Purpose | Default |
|---|---|---|
| `ONTOLOGY_ADMIN_USERNAME` | Bootstrap administrator username | `admin` |
| `ONTOLOGY_ADMIN_PASSWORD` | Bootstrap administrator password | Unset: a random one is generated and printed **once** — miss it and `aletheia passwd --username admin` is the way back |
| `ONTOLOGY_SESSION_TTL_HOURS` | Session lifetime | `12` |
| `ONTOLOGY_AUTH_DISABLED` | Set to `1` to disable all authentication. **Local development only** | Unset (authentication on) |
| `ONTOLOGY_ALLOWED_ORIGINS` | Comma-separated CORS origins | `http://127.0.0.1:3000,http://localhost:3000` |

Only the documented opt-in values disable authentication. A typo
(`ONTOLOGY_AUTH_DISABLED=ture`) leaves it **on** — guessing at intent here would mean
guessing in favour of exposure.

## Logging

| Variable | Purpose | Default |
|---|---|---|
| `ONTOLOGY_LOG_FORMAT` | `json` for one object per line, `text` for a person reading a terminal | `text` |
| `ONTOLOGY_LOG_LEVEL` | Root log level. An unusable value falls back to `INFO` rather than refusing to start | `INFO` |
| `ONTOLOGY_LOG_FILE` | Rotating log file (10 MiB × 5). The parent directory is created | Unset: stderr only |

Both formats carry the request id — `request_id=…` inline in text, `requestId` in JSON —
and every record carries it, including lines logged deep inside a dependency, because the
id is bound to the request context rather than passed at each call site. See
[operations](operations.md) for using it to trace a failure.

Logging is configured when the service starts serving, not when the module is imported:
importing a library should not install process-wide handlers or create directories.

## Rate limiting

Off unless a limit is set. Counters are per process, so the effective limit is the
configured value times the worker count.

| Variable | Purpose | Default |
|---|---|---|
| `ONTOLOGY_RATE_LIMIT_PER_MINUTE` | Requests per minute per client address. `0` disables | `0` (disabled) |
| `ONTOLOGY_RATE_LIMIT_AUTH_PER_MINUTE` | Requests per minute per client address against `/auth/login` and `/auth/sso/login` | `10` |

Limiting runs **before authentication**, keyed on the peer address (`X-Forwarded-For` is
deliberately not read — it is caller-supplied, so reading it lets a caller choose the
address recorded in the audit log). Several hundred people behind one NAT therefore share
one budget: size the limit by that population. Public paths (`/health`, `/metrics`, the
docs) are never counted, so monitoring cannot consume its own allowance.

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
| `ONTOLOGY_DATA_DIR` | The **directory** holding `platform.sqlite3` and the demo sample databases (`legacy_contracts.sqlite3`, `legacy_equipment.sqlite3`) | `data/` in a checkout, `~/.aletheia` otherwise |
| `ONTOLOGY_PLATFORM_SQLITE_BUSY_TIMEOUT_MS` | SQLite `busy_timeout` | `5000` |

> **`serve` uses the same database as every other command.**
> `aletheia serve --platform-db X` passes `X` to the served process and prints the path it
> resolved. It could not before: `uvicorn` imports the app in a fresh process that can only
> read the environment, so `serve --platform-db X` served a *different* database — and the
> symptom was an empty ontology list, which reads as "my data did not save". The
> investigation then starts at the writes, and the one thing it does not look like is a path
> mismatch.

**Every timestamp is UTC**, of the form `2026-01-05 09:30:00` (no offset suffix). All three
dialects default those columns to `current_timestamp`, which is the *session's* time zone:
UTC on SQLite, an instant with an offset on PostgreSQL, and the server's local time on MySQL
— so the same column meant different things on different deployments, invisibly, because an
audit log that is hours off still reads as a plausible time. A MySQL connection now pins
`SET time_zone = '+00:00'`, which makes the convention true on all three. Screens label the
columns they show in UTC; the backup list shows local time and says so.

## Thresholds and naming

| Group | Contents | Env prefix |
|---|---|---|
| `QUERY_LIMITS` | Page size caps, consistency sampling, enum-detection distinct bounds | `ONTOLOGY_DEFAULT_PAGE_SIZE`, `ONTOLOGY_MAX_PAGE_SIZE`, `ONTOLOGY_ENUM_*` |
| `MAPPING_CONFIDENCE` | Mapping candidate confidence (blueprint / structural / vocabulary / weak) | `ONTOLOGY_CONFIDENCE_*` |
| `ANSWER_CONFIDENCE` | Answer confidence | `ONTOLOGY_ANSWER_CONFIDENCE_*` |
| `RESOLUTION_CONFIDENCE` | Instance-resolution confidence and boosts | `ONTOLOGY_RESOLUTION_*` |
| `SEMANTIC_ASSET_NAMING` | IRI namespaces for JSON-LD / Turtle / OWL | `ONTOLOGY_VOCABULARY_BASE_IRI`, `ONTOLOGY_ASSET_BASE_IRI` |
| `MODEL_PROVIDER_DEFAULTS` | Model endpoint, model name, timeout, service tier | `OPENROUTER_*`; `DEEPSEEK_*` when OpenRouter is unset |

With no `OPENROUTER_API_KEY` configured, question answering and draft generation fall back
to a local heuristic — the platform keeps working rather than failing.
If `OPENROUTER_API_KEY` is unset and `DEEPSEEK_API_KEY` is present, the platform automatically
uses DeepSeek's OpenAI-compatible endpoint, defaults to `deepseek-flash`, and disables
OpenRouter-only body extensions. The web model settings page also provides a “DeepSeek official
API” preset.

### Keeping a secret out of the database

Those two variables are the ones the model layer knows by name. For any other endpoint — Azure,
an internal gateway, a local vLLM — the key is configured on the settings page, and there is a
way to do that without the key ever being written to the platform database: store a **reference**
instead, and it is read when the connection is made.

```bash
export CONTRACTS_DSN='postgresql://reader:...@10.0.0.5:5432/contracts'
export AZURE_OPENAI_KEY='...'
```

| Stored value | Read as |
|---|---|
| `env:CONTRACTS_DSN` | the environment variable, at connect time |
| `file:/run/secrets/azure-openai-key` | the file's contents, trimmed of the trailing newline |
| anything else | the value itself, unchanged |

Both a data source's connection URI and a model API key accept a reference. A reference that
points at nothing is an error rather than an empty credential — an empty password fails as
“the password is wrong”, which sends the reader to the wrong problem.

The settings page shows the reference rather than the resolved value, which is what tells an
operator which secret a row is using. This is not encryption: the secret is not in the database
at all, which is a stronger property than obscuring it and needs no crypto dependency.

## Related

- [Self-hosted deployment](deployment.md) — and `aletheia preflight`, which blocks unsafe combinations
- [Model endpoints](model-endpoints.md) — Azure OpenAI, vLLM, gateways
