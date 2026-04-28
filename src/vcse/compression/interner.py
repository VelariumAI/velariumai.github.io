"""String interning for deduplicated storage."""

from __future__ import annotations

from typing import Any

from vcse.compression.errors import InterningError


class Interner:
    """
    Maps strings to small integer IDs for space savings.

    Same string always returns same ID. IDs are deterministic based on
    first-seen order.

    Interning reduces repetition in claim fields (subject/relation/object)
    especially when many claims share subjects/relations/objects.
    """

    def __init__(self) -> None:
        self._s2i: dict[str, int] = {}
        self._i2s: dict[int, str] = {}

    def intern(self, value: str) -> int:
        """
        Intern a string, returning a small integer ID.

        If the string has been interned before, returns the same ID.
        New strings get the next available ID (incremental).
        """
        if value in self._s2i:
            return self._s2i[value]
        next_id = len(self._s2i)
        self._s2i[value] = next_id
        self._i2s[next_id] = value
        return next_id

    def resolve(self, id: int) -> str:
        """Resolve an integer ID back to the original string."""
        if id not in self._i2s:
            raise InterningError(
                "UNRESOLVABLE_ID",
                f"no interned string for id {id}; interner has {len(self._s2i)} entries",
            )
        return self._i2s[id]

    def contains(self, value: str) -> bool:
        """Check if a string is already interned."""
        return value in self._s2i

    @property
    def size(self) -> int:
        """Number of unique strings interned."""
        return len(self._s2i)

    def to_dict(self) -> dict[str, Any]:
        """Serialize intern table for storage."""
        return {
            "string_to_id": dict(self._s2i),
            "id_to_string": {str(k): v for k, v in self._i2s.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Interner":
        """Deserialize intern table."""
        inst = cls()
        s2i = data.get("string_to_id", {})
        for s, i in s2i.items():
            inst._s2i[s] = int(i)
        i2s = data.get("id_to_string", {})
        for i_str, s in i2s.items():
            inst._i2s[int(i_str)] = s
        return inst