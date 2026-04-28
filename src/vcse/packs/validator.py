"""Pack validator."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from vcse import __version__
from vcse.dsl import DSLLoader, DSLValidator
from vcse.gauntlet import load_gauntlet_cases
from vcse.packs.errors import PackError
from vcse.packs.loader import load_manifest
from vcse.packs.manifest import PackManifest


SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass
class PackValidationResult:
    passed: bool
    errors: list[str]
    warnings: list[str]
    manifest: PackManifest | None = None
    artifact_count: int = 0
    benchmark_count: int = 0
    gauntlet_count: int = 0


class PackValidator:
    def validate(self, pack_path: str | Path) -> PackValidationResult:
        manifest, root = load_manifest(pack_path)
        is_legacy = _is_legacy_pack(root, manifest)
        errors: list[str] = []
        warnings: list[str] = list(manifest.warnings)

        errors.extend(_validate_required_fields(manifest))
        errors.extend(_validate_semver(manifest))
        errors.extend(_validate_version_compatibility(manifest))

        artifact_paths = _manifest_artifact_paths(manifest)
        for rel_path in artifact_paths:
            if not (root / rel_path).exists():
                errors.append(f"missing artifact: {rel_path}")

        if errors:
            return PackValidationResult(
                passed=False,
                errors=errors,
                warnings=warnings,
                manifest=manifest,
                artifact_count=len(artifact_paths),
                benchmark_count=len(manifest.benchmarks),
                gauntlet_count=len(manifest.gauntlet_cases),
            )

        errors.extend(_validate_integrity(root, manifest))
        errors.extend(_validate_dsl(root, manifest))
        errors.extend(_validate_claims(root, manifest))
        errors.extend(_validate_constraints(root, manifest))
        errors.extend(_validate_provenance(root, manifest, is_legacy=is_legacy))
        errors.extend(_validate_benchmarks(root, manifest))
        errors.extend(_validate_gauntlet(root, manifest))
        errors.extend(_validate_forbidden_content(root, manifest))
        errors.extend(_validate_conflict_metadata(root, manifest))

        return PackValidationResult(
            passed=(len(errors) == 0),
            errors=errors,
            warnings=warnings,
            manifest=manifest,
            artifact_count=len(artifact_paths),
            benchmark_count=len(manifest.benchmarks),
            gauntlet_count=len(manifest.gauntlet_cases),
        )


def _validate_required_fields(manifest: PackManifest) -> list[str]:
    errors: list[str] = []
    if _is_legacy_manifest(manifest):
        for key, value in (
            ("id", manifest.id),
            ("version", manifest.version),
            ("domain", manifest.domain),
            ("created_at", manifest.created_at),
        ):
            if not str(value).strip():
                errors.append(f"manifest missing required field: {key}")
        return errors
    for key, value in (
        ("id", manifest.id),
        ("name", manifest.name),
        ("version", manifest.version),
        ("description", manifest.description),
        ("domain", manifest.domain),
        ("license", manifest.license),
        ("created_at", manifest.created_at),
    ):
        if not str(value).strip():
            errors.append(f"manifest missing required field: {key}")
    if not manifest.authors:
        errors.append("manifest missing required field: authors")
    if not manifest.artifacts:
        errors.append("manifest missing required field: artifacts")
    return errors


def _validate_semver(manifest: PackManifest) -> list[str]:
    errors: list[str] = []
    if not SEMVER_RE.match(manifest.version):
        errors.append("invalid manifest version semver")
    if manifest.vcse_min_version and not SEMVER_RE.match(manifest.vcse_min_version):
        errors.append("invalid vcse_min_version semver")
    if manifest.vcse_max_version is not None and not SEMVER_RE.match(manifest.vcse_max_version):
        errors.append("invalid vcse_max_version semver")
    for dependency in manifest.dependencies:
        if not dependency.id:
            errors.append("dependency missing id")
        if not dependency.version:
            errors.append(f"dependency missing version for {dependency.id or '<unknown>'}")
    return errors


def _validate_version_compatibility(manifest: PackManifest) -> list[str]:
    errors: list[str] = []
    if not manifest.vcse_min_version:
        return errors
    runtime = _semver_tuple(__version__)
    if runtime < _semver_tuple(manifest.vcse_min_version):
        errors.append("pack requires newer vcse version")
    if manifest.vcse_max_version is not None and runtime > _semver_tuple(manifest.vcse_max_version):
        errors.append("pack vcse_max_version incompatible with runtime")
    return errors


def _manifest_artifact_paths(manifest: PackManifest) -> list[str]:
    paths: list[str] = []
    for values in manifest.artifacts.values():
        paths.extend(values)
    paths.extend(manifest.benchmarks)
    paths.extend(manifest.gauntlet_cases)
    paths.extend(manifest.provenance)
    return sorted(set(paths))


def _validate_integrity(root: Path, manifest: PackManifest) -> list[str]:
    errors: list[str] = []
    if manifest.integrity.hash_algorithm != "sha256":
        errors.append("unsupported hash algorithm")
        return errors
    for rel_path, expected in manifest.integrity.artifact_hashes.items():
        path = root / rel_path
        if not path.exists():
            errors.append(f"artifact hash references missing file: {rel_path}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            errors.append(f"artifact hash mismatch: {rel_path}")
    return errors


def _validate_dsl(root: Path, manifest: PackManifest) -> list[str]:
    errors: list[str] = []
    for rel_path in manifest.artifacts.get("dsl", []):
        path = root / rel_path
        try:
            document = DSLLoader.load(path)
        except Exception as exc:
            errors.append(f"invalid dsl artifact {rel_path}: {exc}")
            continue
        validation = DSLValidator.validate(document)
        if not validation.passed:
            errors.append(f"invalid dsl artifact {rel_path}: {'; '.join(validation.errors)}")
    return errors


def _validate_claims(root: Path, manifest: PackManifest) -> list[str]:
    errors: list[str] = []
    for rel_path in manifest.artifacts.get("claims", []):
        for idx, line in enumerate((root / rel_path).read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"malformed claim {rel_path}:{idx}: {exc.msg}")
                continue
            for key in ("subject", "relation", "object"):
                if str(item.get(key, "")).strip() == "":
                    errors.append(f"claim missing {key} at {rel_path}:{idx}")
    return errors


def _validate_constraints(root: Path, manifest: PackManifest) -> list[str]:
    errors: list[str] = []
    for rel_path in manifest.artifacts.get("constraints", []):
        for idx, line in enumerate((root / rel_path).read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"malformed constraint {rel_path}:{idx}: {exc.msg}")
                continue
            if "target" not in item and "kind" not in item:
                errors.append(f"constraint missing target/kind at {rel_path}:{idx}")
    return errors


def _validate_provenance(root: Path, manifest: PackManifest, *, is_legacy: bool = False) -> list[str]:
    errors: list[str] = []
    paths = list(manifest.artifacts.get("provenance", [])) + list(manifest.provenance)
    if is_legacy and not paths:
        legacy_provenance = root / "provenance.jsonl"
        if legacy_provenance.exists():
            paths = ["provenance.jsonl"]
    if not paths:
        errors.append("manifest missing provenance artifacts")
        return errors
    for rel_path in sorted(set(paths)):
        lines = (root / rel_path).read_text().splitlines()
        if not any(line.strip() for line in lines):
            errors.append(f"empty provenance artifact: {rel_path}")
    return errors


def _validate_benchmarks(root: Path, manifest: PackManifest) -> list[str]:
    errors: list[str] = []
    for rel_path in manifest.benchmarks:
        path = root / rel_path
        for idx, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"malformed benchmark case {rel_path}:{idx}: {exc.msg}")
                continue
            if "expected_status" not in payload:
                errors.append(f"benchmark case missing expected_status {rel_path}:{idx}")
    return errors


def _validate_gauntlet(root: Path, manifest: PackManifest) -> list[str]:
    errors: list[str] = []
    for rel_path in manifest.gauntlet_cases:
        try:
            load_gauntlet_cases(root / rel_path)
        except Exception as exc:
            errors.append(f"invalid gauntlet case file {rel_path}: {exc}")
    return errors


def _validate_forbidden_content(root: Path, manifest: PackManifest) -> list[str]:
    errors: list[str] = []
    pattern = re.compile(r"\b(exec\(|eval\(|__import__|subprocess|os\.system)\b")
    for rel_path in _manifest_artifact_paths(manifest):
        path = root / rel_path
        if not path.exists() or path.suffix.lower() not in {".json", ".jsonl", ".yaml", ".yml", ".txt"}:
            continue
        text = path.read_text()
        if pattern.search(text):
            errors.append(f"forbidden executable content in {rel_path}")
    return errors


def _validate_conflict_metadata(root: Path, manifest: PackManifest) -> list[str]:
    errors: list[str] = []
    seen: dict[tuple[str, str], tuple[str, int]] = {}
    conflicts_path = manifest.artifacts.get("conflicts", [])
    has_conflict_file = bool(conflicts_path)
    for rel_path in manifest.artifacts.get("claims", []):
        for idx, line in enumerate((root / rel_path).read_text().splitlines(), start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            key = (str(payload.get("subject", "")), str(payload.get("relation", "")))
            obj = str(payload.get("object", ""))
            previous = seen.get(key)
            if previous is not None and previous[0] != obj and not has_conflict_file:
                errors.append(
                    f"conflicting claim without conflict artifact for {key[0]} {key[1]}"
                )
            else:
                seen[key] = (obj, idx)
    return errors


def _semver_tuple(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3:
        raise PackError("INVALID_VERSION", f"invalid semver: {version}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _is_legacy_manifest(manifest: PackManifest) -> bool:
    return not manifest.name and not manifest.artifacts and not manifest.dependencies


def _is_legacy_pack(root: Path, manifest: PackManifest) -> bool:
    if not _is_legacy_manifest(manifest):
        return False
    return (root / "claims.jsonl").exists() or (root / "provenance.jsonl").exists()
