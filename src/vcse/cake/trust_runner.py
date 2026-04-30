"""CAKE trust integration — delegates to TrustPromoter, read-only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vcse.knowledge.pack_model import KnowledgeClaim
from vcse.trust.promoter import TrustPromoter, TrustReport


class CakeTrustRunner:
    """Calls existing TrustPromoter without modification."""

    def evaluate(self, claims: list[KnowledgeClaim]) -> TrustReport:
        """Evaluate trust decisions for a list of claims."""
        promoter = TrustPromoter()
        return promoter.evaluate_claims([c.to_dict() for c in claims])

    def promote(self, pack_path: Path) -> TrustReport:
        """Run trust promotion on an on-disk pack."""
        promoter = TrustPromoter()
        return promoter.promote(pack_path)