"""Dictionary-based claim encoding using string interning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vcse.compression.canonicalizer import CanonicalClaim, canonicalize_claim
from vcse.compression.errors import EncodingError
from vcse.compression.interner import Interner


@dataclass(frozen=True)
class EncodedClaim:
    """Integer-encoded claim using an interner."""
    subject_id: int
    relation_id: int
    object_id: int
    qualifier_ids: tuple[tuple[int, int], ...]


def encode_claim(claim: dict[str, Any], interner: Interner) -> EncodedClaim:
    """
    Encode a raw claim dict into an EncodedClaim using the given interner.

    Interns subject, relation, object, and all qualifier keys/values.
    Produces a fixed-size-ish record with small integers.

    Raises EncodingError if required fields are missing.
    """
    canonical = canonicalize_claim(claim)

    subject_id = interner.intern(canonical.subject)
    relation_id = interner.intern(canonical.relation)
    object_id = interner.intern(canonical.object)

    qualifier_pairs: list[tuple[int, int]] = []
    for key, value in canonical.qualifiers:
        key_id = interner.intern(key)
        value_id = interner.intern(value)
        qualifier_pairs.append((key_id, value_id))

    return EncodedClaim(
        subject_id=subject_id,
        relation_id=relation_id,
        object_id=object_id,
        qualifier_ids=tuple(qualifier_pairs),
    )


def decode_claim(encoded: EncodedClaim, interner: Interner) -> CanonicalClaim:
    """
    Decode an EncodedClaim back to a CanonicalClaim using the interner.
    """
    subject = interner.resolve(encoded.subject_id)
    relation = interner.resolve(encoded.relation_id)
    obj = interner.resolve(encoded.object_id)

    qualifier_pairs: list[tuple[str, str]] = []
    for key_id, value_id in encoded.qualifier_ids:
        key = interner.resolve(key_id)
        value = interner.resolve(value_id)
        qualifier_pairs.append((key, value))

    return CanonicalClaim(
        subject=subject,
        relation=relation,
        object=obj,
        qualifiers=tuple(qualifier_pairs),
    )


def encode_claim_from_canonical(canonical: CanonicalClaim, interner: Interner) -> EncodedClaim:
    """Encode a CanonicalClaim directly (no re-canonicalization)."""
    subject_id = interner.intern(canonical.subject)
    relation_id = interner.intern(canonical.relation)
    object_id = interner.intern(canonical.object)

    qualifier_pairs: list[tuple[int, int]] = []
    for key, value in canonical.qualifiers:
        key_id = interner.intern(key)
        value_id = interner.intern(value)
        qualifier_pairs.append((key_id, value_id))

    return EncodedClaim(
        subject_id=subject_id,
        relation_id=relation_id,
        object_id=object_id,
        qualifier_ids=tuple(qualifier_pairs),
    )


def encoded_to_dict(encoded: EncodedClaim) -> dict[str, Any]:
    """Serialize an EncodedClaim to a dict for JSON storage."""
    return {
        "subject_id": encoded.subject_id,
        "relation_id": encoded.relation_id,
        "object_id": encoded.object_id,
        "qualifier_ids": [[k, v] for k, v in encoded.qualifier_ids],
    }


def dict_to_encoded(data: dict[str, Any]) -> EncodedClaim:
    """Deserialize a dict to an EncodedClaim."""
    return EncodedClaim(
        subject_id=int(data["subject_id"]),
        relation_id=int(data["relation_id"]),
        object_id=int(data["object_id"]),
        qualifier_ids=tuple(
            (int(k), int(v)) for k, v in data.get("qualifier_ids", [])
        ),
    )