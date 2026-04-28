from pathlib import Path

from vcse.interaction.session import Session
from vcse.packs.activator import PackActivator
from vcse.packs.installer import PackInstaller


def _pack_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "packs" / name


def test_pack_activation_compiles_dsl_and_claims(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VCSE_PACK_HOME", str(tmp_path / "vcse_home"))
    installer = PackInstaller()
    installer.install(_pack_path("logic_basic"))

    activation = PackActivator().activate(["vrm.logic.basic@1.0.0"])

    assert activation.parser_rules >= 1
    assert activation.synonyms >= 0
    assert len(activation.knowledge_claims) == 2


def test_ask_with_pack_bundle_solves_logic(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VCSE_PACK_HOME", str(tmp_path / "vcse_home"))
    installer = PackInstaller()
    installer.install(_pack_path("logic_basic"))
    activation = PackActivator().activate(["vrm.logic.basic@1.0.0"])

    session = Session.create(dsl_bundle=activation.dsl_bundle)
    for claim in activation.knowledge_claims:
        session.memory.add_claim(claim["subject"], claim["relation"], claim["object"])

    session.ingest("Can Socrates die?")
    result = session.solve()

    assert result is not None
    assert result.evaluation.status.value == "VERIFIED"
