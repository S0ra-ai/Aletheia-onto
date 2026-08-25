# Self-hosted deployment

> Images, orchestration and the preflight that blocks unsafe configurations.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

```bash
cp deploy/.env.example deploy/.env    # fill in real values; the example has no usable defaults
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d
```

Two-stage image, non-root, no bundled credentials and no seeded database. The reference
compose file uses PostgreSQL as the platform store and does not publish the database port.

## Deployment preflight

```bash
aletheia preflight --workers 4 --expect-origin https://ontology.example.com
```

Exits 1 on a blocker, so it works as a pipeline gate. `aletheia serve` runs it
**automatically** when binding to a non-loopback address and refuses to start — nobody
remembers to run a separate command, and the one deployment where it matters is the one
where `ONTOLOGY_AUTH_DISABLED=1` was left behind.

Every check catches a **silent** failure: the platform starts, serves traffic, and looks
healthy.

| Misconfiguration | What actually happens | Level |
|---|---|:--:|
| `ONTOLOGY_AUTH_DISABLED=1` left on | the whole API is reachable with no token, **including writeback** | blocker |
| CORS set to `*` | any site can drive the API carrying a user's credentials | blocker |
| admin password is a placeholder or under 12 chars | somebody chose it and will assume it was changed | blocker |
| SQLite with several workers | writes serialise; the symptom is **intermittent timeouts**, not a config error | blocker |
| platform DB file readable by group/other | that file holds every data source's connection string | blocker |
| CORS still localhost | the real frontend is blocked, and the next step someone takes is `*` | warning |
| admin password unset | a random one is printed once, and container logs rotate | warning |
| password inline in the connection URI | it appears in the process list, container inspect, and crash logs | warning |

A single-node SQLite evaluation deployment is legitimate, so one worker does not block —
refusing it would push people to skip the check entirely.

Full reasoning in [ADR-0017](adr/0017-deployment-preflight.md).
