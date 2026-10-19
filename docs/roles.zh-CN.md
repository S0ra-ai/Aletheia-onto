# 角色与能力

> 六个角色、六项能力，以及默认拒绝的策略表。

返回 [中文 README](../README.zh-CN.md) · [English README](../README.md)

六个角色、六项能力。路由到能力的中央对照表在 `access_policy.py` 里，
**没有列出的路由默认只有管理员可用**。

| 角色 | `platform:read` | `platform:write` | `governance:review` | `governance:publish` | `automation:execute` | `platform:admin` |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ontology_engineer` | ✅ | ✅ | | ✅ | | |
| `business_expert` | ✅ | ✅ | ✅ | | | |
| `operator` | ✅ | | | | ✅ | |
| `analyst` | ✅ | | | | | |
| `ai_agent` | ✅ | | | | | |

新用户默认是 `analyst`。令牌只以摘要形式存储；会话会过期、可以被吊销，
改密码会让所有已存在的会话失效。
