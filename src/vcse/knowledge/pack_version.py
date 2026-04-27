"""Knowledge pack semantic version helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcse.knowledge.pack_model import KnowledgePack


@dataclass(frozen=True)
class PackDiff:
    added_claims: list[str] = field(default_factory=list)
    removed_claims: list[str] = field(default_factory=list)


def next_patch_version(version: str) -> str:
    major, minor, patch = _parse_semver(version)
    return f"{major}.{minor}.{patch + 1}"


def diff_packs(old: KnowledgePack, new: KnowledgePack) -> PackDiff:
    old_keys = {claim.key for claim in old.claims}
    new_keys = {claim.key for claim in new.claims}
    return PackDiff(
        added_claims=sorted(new_keys - old_keys),
        removed_claims=sorted(old_keys - new_keys),
    )


def _parse_semver(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"invalid semantic version: {version}")
    return int(parts[0]), int(parts[1]), int(parts[2])
