"""Runtime registries for the platform's extension points.

Every extension point used to be hardcoded, which meant a third party wanting to
add a data source, a rule function, a route policy or a writeback channel had to
fork the platform -- and a fork can no longer upgrade the kernel. These
registries replace that with runtime registration.

Stability: all extension points are experimental. Signatures may change between
minor versions before 1.0; changes are recorded in CHANGELOG.md. See
docs/adr/0007-extension-registry-without-api-stability.md.

Design notes:

- Built-in implementations register themselves at import time, so default
  behaviour is unchanged and ``list_*()`` reports a complete picture.
- Registration is idempotent for the same object but rejects silent overwrites by
  a *different* object, because a plugin quietly shadowing a built-in is a
  debugging nightmare. Pass ``replace=True`` to override deliberately.
- Registries are process-global, matching how the platform already loads
  built-ins. Per-tenant variation is deliberately out of scope until the
  isolation model lands (ADR-0006).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Iterable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RegistryError(RuntimeError):
    """Raised when a registration or lookup cannot be satisfied."""


@dataclass
class Registry(Generic[T]):
    """A named collection of interchangeable implementations.

    ``kind`` appears in error messages, so it should read naturally in a
    sentence such as "不支持的数据源适配器: oracle".
    """

    kind: str
    aliases: dict[str, str] = field(default_factory=dict)
    _entries: dict[str, T] = field(default_factory=dict)

    def register(self, name: str, implementation: T, *, replace: bool = False) -> T:
        key = self._normalize(name)
        if not key:
            raise RegistryError(f"{self.kind}的名称不能为空")
        existing = self._entries.get(key)
        if existing is not None and existing is not implementation and not replace:
            raise RegistryError(f"{self.kind} '{key}' 已被占用。如确实要覆盖，请显式传入 replace=True。")
        self._entries[key] = implementation
        return implementation

    def unregister(self, name: str) -> None:
        self._entries.pop(self._normalize(name), None)

    def get(self, name: str) -> T:
        key = self._normalize(name)
        resolved = self.aliases.get(key, key)
        try:
            return self._entries[resolved]
        except KeyError:
            raise RegistryError(
                f"不支持的{self.kind}: {name}。当前已注册: {', '.join(self.names()) or '（无）'}"
            ) from None

    def try_get(self, name: str) -> Optional[T]:
        key = self._normalize(name)
        return self._entries.get(self.aliases.get(key, key))

    def contains(self, name: str) -> bool:
        return self.try_get(name) is not None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    def items(self) -> tuple[tuple[str, T], ...]:
        return tuple(sorted(self._entries.items()))

    def alias(self, alias: str, target: str) -> None:
        self.aliases[self._normalize(alias)] = self._normalize(target)

    def snapshot(self) -> dict[str, T]:
        """Copy current contents, for tests that need to restore state."""
        return dict(self._entries)

    def restore(self, entries: dict[str, T]) -> None:
        self._entries.clear()
        self._entries.update(entries)

    @staticmethod
    def _normalize(name: str) -> str:
        return str(name or "").strip().lower()


def load_entry_point_plugins(group: str, registrar: Callable[[str, Any], Any]) -> list[str]:
    """Register implementations advertised by installed packages.

    Discovery failures are logged rather than raised: one broken third-party
    package must not prevent the platform from starting.
    """
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover - Python < 3.8
        return []

    loaded: list[str] = []
    try:
        discovered = entry_points()
        # 3.10+ returns a selectable EntryPoints; 3.9 returns a dict keyed by
        # group. Probe for the newer API rather than catching TypeError, which
        # would also swallow genuine errors from a plugin's metadata.
        selector = getattr(discovered, "select", None)
        if callable(selector):
            found: Iterable[Any] = selector(group=group)
        else:
            found = discovered.get(group, [])  # type: ignore[attr-defined]
    except Exception as error:  # pragma: no cover - defensive
        logger.warning("扫描 entry point 组 %s 失败: %s", group, error)
        return []

    for entry in found:
        try:
            registrar(entry.name, entry.load())
            loaded.append(entry.name)
        except Exception as error:
            logger.error("加载插件 %s (%s) 失败: %s", entry.name, group, error)
    return loaded
