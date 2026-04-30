"""Dependency resolution for packs."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcse.packs.errors import PackError
from vcse.packs.registry import PackRegistry


@dataclass(frozen=True)
class ResolvedPack:
    id: str
    version: str
    install_path: str
    dependencies: list[dict[str, str]]


@dataclass(frozen=True)
class DependencyResolution:
    ordered: list[ResolvedPack] = field(default_factory=list)


class DependencyResolver:
    def __init__(self, registry: PackRegistry | None = None) -> None:
        self.registry = registry or PackRegistry()

    def resolve(self, requested: list[str]) -> DependencyResolution:
        seen: dict[str, ResolvedPack] = {}
        visiting: set[str] = set()
        ordered: list[ResolvedPack] = []
        for spec in requested:
            pack_id, version = parse_pack_spec(spec)
            self._visit(pack_id, version, seen, visiting, ordered)
        return DependencyResolution(ordered=ordered)

    def _visit(
        self,
        pack_id: str,
        version: str | None,
        seen: dict[str, ResolvedPack],
        visiting: set[str],
        ordered: list[ResolvedPack],
    ) -> None:
        key = f"{pack_id}@{version or '*'}"
        if key in seen:
            return
        if key in visiting:
            raise PackError("CIRCULAR_DEPENDENCY", f"circular dependency detected at {key}")
        visiting.add(key)

        record = self.registry.find(pack_id, version)
        if record is None:
            raise PackError("MISSING_DEPENDENCY", f"missing dependency: {key}")
        resolved = ResolvedPack(
            id=str(record["id"]),
            version=str(record["version"]),
            install_path=str(record["install_path"]),
            dependencies=list(record.get("dependencies", [])),
        )
        for dep in resolved.dependencies:
            dep_id = str(dep.get("id", "")).strip()
            dep_version_spec = str(dep.get("version", "")).strip()
            if not dep_id:
                raise PackError("INVALID_DEPENDENCY", f"dependency missing id in {resolved.id}@{resolved.version}")
            dep_record = self.registry.find(dep_id, None)
            if dep_record is None:
                raise PackError("MISSING_DEPENDENCY", f"missing dependency: {dep_id}")
            if not _version_satisfies(str(dep_record["version"]), dep_version_spec):
                raise PackError(
                    "INCOMPATIBLE_DEPENDENCY",
                    f"{resolved.id}@{resolved.version} requires {dep_id} {dep_version_spec}",
                )
            self._visit(dep_id, str(dep_record["version"]), seen, visiting, ordered)

        visiting.remove(key)
        seen[key] = resolved
        ordered.append(resolved)


def parse_pack_spec(spec: str) -> tuple[str, str | None]:
    clean = spec.strip()
    if "@" in clean:
        pack_id, version = clean.split("@", 1)
        return pack_id.strip(), version.strip()
    return clean, None


def _version_satisfies(version: str, requirement: str) -> bool:
    if not requirement:
        return True
    value = _semver(version)
    requirement = requirement.strip()
    if requirement.startswith(">="):
        if "," in requirement:
            left, right = [part.strip() for part in requirement.split(",", 1)]
            return _version_satisfies(version, left) and _version_satisfies(version, right)
        return value >= _semver(requirement[2:])
    if requirement.startswith("<"):
        return value < _semver(requirement[1:])
    if requirement.startswith("=="):
        return value == _semver(requirement[2:])
    if requirement.startswith("="):
        return value == _semver(requirement[1:])
    if requirement.count(".") == 2 and requirement[0].isdigit():
        return value == _semver(requirement)
    raise PackError("UNSUPPORTED_DEPENDENCY_SYNTAX", f"unsupported dependency requirement: {requirement}")


def _semver(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3:
        raise PackError("INVALID_VERSION", f"invalid semver: {version}")
    return int(parts[0]), int(parts[1]), int(parts[2])
