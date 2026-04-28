"""Pack manifest models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PackDependency:
    id: str
    version: str


@dataclass(frozen=True)
class PackIntegrity:
    hash_algorithm: str = "sha256"
    manifest_hash: str = ""
    artifact_hashes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PackManifest:
    id: str
    name: str
    version: str
    description: str
    domain: str
    authors: list[str]
    license: str
    created_at: str
    vcse_min_version: str
    vcse_max_version: str | None
    dependencies: list[PackDependency]
    artifacts: dict[str, list[str]]
    benchmarks: list[str]
    gauntlet_cases: list[str]
    provenance: list[str]
    integrity: PackIntegrity
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PackManifest":
        dependencies: list[PackDependency] = []
        for item in payload.get("dependencies", []):
            if isinstance(item, dict):
                dependencies.append(
                    PackDependency(id=str(item.get("id", "")).strip(), version=str(item.get("version", "")).strip())
                )
        integrity_raw = payload.get("integrity", {})
        integrity = PackIntegrity(
            hash_algorithm=str(integrity_raw.get("hash_algorithm", "sha256")),
            manifest_hash=str(integrity_raw.get("manifest_hash", "")),
            artifact_hashes={
                str(key): str(value)
                for key, value in integrity_raw.get("artifact_hashes", {}).items()
            },
        )
        known_fields = {
            "id",
            "name",
            "version",
            "description",
            "domain",
            "authors",
            "license",
            "created_at",
            "vcse_min_version",
            "vcse_max_version",
            "dependencies",
            "artifacts",
            "benchmarks",
            "gauntlet_cases",
            "provenance",
            "integrity",
        }
        warnings = [
            f"unknown manifest field ignored: {key}"
            for key in sorted(payload.keys())
            if key not in known_fields
        ]
        return cls(
            id=str(payload.get("id", "")).strip(),
            name=str(payload.get("name", "")).strip(),
            version=str(payload.get("version", "")).strip(),
            description=str(payload.get("description", "")).strip(),
            domain=str(payload.get("domain", "")).strip(),
            authors=[str(item) for item in payload.get("authors", [])],
            license=str(payload.get("license", "")).strip(),
            created_at=str(payload.get("created_at", "")).strip(),
            vcse_min_version=str(payload.get("vcse_min_version", "")).strip(),
            vcse_max_version=(
                str(payload.get("vcse_max_version")).strip()
                if payload.get("vcse_max_version") is not None
                else None
            ),
            dependencies=dependencies,
            artifacts={str(k): [str(v) for v in values] for k, values in payload.get("artifacts", {}).items()},
            benchmarks=[str(item) for item in payload.get("benchmarks", [])],
            gauntlet_cases=[str(item) for item in payload.get("gauntlet_cases", [])],
            provenance=[str(item) for item in payload.get("provenance", [])],
            integrity=integrity,
            warnings=warnings,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "domain": self.domain,
            "authors": list(self.authors),
            "license": self.license,
            "created_at": self.created_at,
            "vcse_min_version": self.vcse_min_version,
            "vcse_max_version": self.vcse_max_version,
            "dependencies": [{"id": item.id, "version": item.version} for item in self.dependencies],
            "artifacts": {k: list(v) for k, v in self.artifacts.items()},
            "benchmarks": list(self.benchmarks),
            "gauntlet_cases": list(self.gauntlet_cases),
            "provenance": list(self.provenance),
            "integrity": {
                "hash_algorithm": self.integrity.hash_algorithm,
                "manifest_hash": self.integrity.manifest_hash,
                "artifact_hashes": dict(self.integrity.artifact_hashes),
            },
        }
