# Roles and capabilities

> Six capabilities across six roles, and the deny-by-default policy table.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

Six capabilities across six roles. The central route-to-capability table lives in
`access_policy.py`, and **unlisted routes default to admin-only**.

| Role | `platform:read` | `platform:write` | `governance:review` | `governance:publish` | `automation:execute` | `platform:admin` |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ontology_engineer` | ✅ | ✅ | | ✅ | | |
| `business_expert` | ✅ | ✅ | ✅ | | | |
| `operator` | ✅ | | | | ✅ | |
| `analyst` | ✅ | | | | | |
| `ai_agent` | ✅ | | | | | |

New users default to `analyst`. Tokens are stored as digests only; sessions expire and
can be revoked, and changing a password invalidates all existing sessions.
