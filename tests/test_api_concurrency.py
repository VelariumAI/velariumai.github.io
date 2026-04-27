from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from vcse.api.server import create_app


def test_api_handles_concurrent_requests_deterministically() -> None:
    client = TestClient(create_app())

    def do_request() -> str:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "vcse-vrm-1.9",
                "messages": [
                    {"role": "user", "content": "All men are mortal. Socrates is a man. Can Socrates die?"}
                ],
            },
        )
        assert response.status_code == 200
        return response.json()["choices"][0]["message"]["content"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        outputs = list(executor.map(lambda _: do_request(), range(8)))

    assert len(set(outputs)) == 1
    assert "Socrates" in outputs[0]

