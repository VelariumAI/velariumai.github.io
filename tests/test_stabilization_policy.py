from pathlib import Path


def test_core_source_has_no_forbidden_implementation_references() -> None:
    src_dir = Path(__file__).resolve().parents[1] / "src" / "vcse"
    forbidden_terms = (
        "openai",
        "anthropic",
        "llama",
        "transformer",
        "transformers",
        "neural",
        "llm",
        "large language model",
        "autoregressive",
        "next-token",
        "embedding model",
    )
    forbidden_imports = (
        "import torch",
        "from torch",
        "import tensorflow",
        "from tensorflow",
        "import transformers",
        "from transformers",
        "import openai",
        "from openai",
        "import anthropic",
        "from anthropic",
    )

    for path in src_dir.rglob("*.py"):
        text = path.read_text().lower()
        assert not any(term in text for term in forbidden_terms), path
        assert not any(term in text for term in forbidden_imports), path
