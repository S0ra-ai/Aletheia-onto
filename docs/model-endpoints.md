# Connecting a custom model service

The platform speaks the **OpenAI-compatible `chat/completions` protocol**, so any service that
implements it can be connected: the official APIs, a relay or a custom subscription, a
self-hosted vLLM / Ollama, Azure OpenAI, or a vendor's compatibility endpoint.

> With no API key configured, question answering and drafting **fall back to a local
> heuristic** and stay usable — a missing model does not make the platform unavailable.

## Why a base URL on its own is not enough

Providers disagree on three things, and each one fails the request outright:

| Difference | Symptom |
|---|---|
| How the key is carried | `401`: Azure wants an `api-key` header, not `Authorization: Bearer` |
| Tolerance for extra fields | `400`: `service_tier` / `session_id` are OpenRouter extensions, and a strict implementation (vLLM, LM Studio, some relays) rejects unknown fields |
| The shape of the base URL | `404`: some gateways already give you the full `/chat/completions`, and Azure adds `?api-version=` |

So there are three compatibility settings beside the base URL.

## Presets

The model settings page applies these in one click:

| Preset | Base URL | Auth | Extra fields |
|---|---|:--:|:--:|
| OpenRouter | `https://openrouter.ai/api/v1` | bearer | on |
| OpenAI | `https://api.openai.com/v1` | bearer | off |
| Relay / custom subscription | `https://<your domain>/v1` | bearer | off |
| Azure OpenAI | `https://<resource>.openai.azure.com/openai/deployments/<deployment>/chat/completions?api-version=2024-02-01` | api-key | off |
| Self-hosted vLLM / Ollama | `http://127.0.0.1:8000/v1` | none | off |
| Alibaba Cloud Model Studio / Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | bearer | off |
| DeepSeek official API | `https://api.deepseek.com` | bearer | off |

A preset fills in the compatibility settings only; the key and the model name are still yours.

## The settings

### Authentication style

| Value | What is sent | For |
|---|---|---|
| `bearer` | `Authorization: Bearer <key>` | most services |
| `api-key` | `api-key: <key>` | Azure OpenAI |
| `custom` | `<your header>: <key>` | gateways that need a special header name |
| `none` | no key at all | a service on your own network |

Choosing `custom` requires the header name, and saving is refused without it — a silently
dropped key is harder to diagnose than an error.

### Send OpenRouter extension fields

Controls whether `service_tier` and `session_id` go in the request body.
**Turn this off for anything that is not OpenRouter.**

### Extra headers

A JSON object, for example `{"X-Tenant-Id": "acme"}`. A key here **overrides** the generated
header of the same name, which makes this the last-resort escape hatch.

### How the base URL's path is handled

The platform decides the address it actually calls like this:

- normally it appends `/chat/completions` to the base URL
- if the base URL **already contains** `/chat/completions`, it is used as given, not appended twice
- the query string (Azure's `?api-version=`, say) is preserved

The settings page shows **the full address that will be called**, so it can be checked before
saving.

## Environment variables

Where the interface is not used, the same settings can come from the environment (a value saved
in the database takes precedence):

| Variable | Meaning |
|---|---|
| `OPENROUTER_API_KEY` | API key |
| `OPENROUTER_BASE_URL` | base URL |
| `OPENROUTER_MODEL` | model name |
| `ONTOLOGY_MODEL_AUTH_STYLE` | authentication style |
| `ONTOLOGY_MODEL_AUTH_HEADER` | custom authentication header name |
| `ONTOLOGY_MODEL_EXTRA_HEADERS` | extra headers (a JSON string) |
| `ONTOLOGY_MODEL_SEND_EXTRAS` | set to `0` to turn the extension fields off |

With no `OPENROUTER_API_KEY`, the DeepSeek official API can be used instead: set
`DEEPSEEK_API_KEY`, and optionally `DEEPSEEK_MODEL` (default `deepseek-flash`) and
`DEEPSEEK_BASE_URL` (default `https://api.deepseek.com`). The platform uses Bearer
authentication and turns the OpenRouter-only fields off automatically; a model configuration
saved in the database still takes precedence over the environment.

## What happens to what the model returns

The drafting assistants (blueprint drafts, semantic suggestions, reasoning chains) depend on the
model returning **JSON**, so the platform has to assume the model is not perfectly obedient.
Three rules:

**Field types are written into the prompt.** An early prompt listed the field names without
their shape, leaving the model to guess — and `objectHints` is very naturally read by a real
model as an array of object descriptors (the richer form, carrying source table, primary key and
relations), while the platform read it as `{table name: display name}` and `dict(array)` raised
outright. The prompt now gives the shape **the platform stores**.

The same gap was still open on the reasoning-chain endpoint: the prompt asked for "buildPlan
with both paths", the model therefore gave an object per path, and the field was rendered as an
array of strings — React refuses an object as a child, the error boundary replaces the whole
page, and **the endpoint returned 200 while the log recorded success**.
All three drafting endpoints now state the shape of every field and of its elements.

**A field that cannot be read costs only that field.** Normalisation is per field: one with the
wrong shape keeps the draft's own value while the rest take the model's. Previously any field
raising took the whole response down through an `except` above — a usable 16KB of model output
was replaced by the heuristic draft, and the caller saw only `usedRemoteModel: false`, which
**reads like "no model was configured at all"**.

**A field that could not be read is reported.** `unreadableModelFields: ["objectHints"]` in the
response means that field fell back to the draft's own value; the key's absence means every
field the model returned was used. The platform does not guess at what the model meant — a hint
becomes the governed ontology's business vocabulary, and **a name the model never wrote, once
invented, is indistinguishable from a real one**.

One more thing: the normaliser also accepts array-shaped object descriptors, because that is the
natural reading when the model was not told the shape and it carries more than the mapping does.
It only projects faithfully (`code`/`name`); it never fills in or infers. Likewise, when a text
field receives an object, it projects that object's own `detail` / `path` / `text` — keeping the
model's words rather than discarding the entry or turning it into a Python `repr`.

## Troubleshooting

| Symptom | Check first |
|---|---|
| `401` | whether the authentication style matches; whether the key has expired |
| `400` naming an unknown field | turn off "send OpenRouter extension fields" |
| `404` | the base URL's path; compare with the address the settings page shows |
| Connection timeout | the address and port of a self-hosted service; raise the timeout |
| Empty response | whether the model name is valid for that provider (Azure wants the deployment name) |

The settings page's "test connection" returns the actual error and names the most likely cause
for the status code.

## Security

- the API key is returned **as its first and last characters only**; the full value is never echoed
- leaving the key blank on the settings page means "keep the current key", not "clear it"
- values in the extra headers go into the request too — do not put unrelated credentials there
