import json
from pathlib import Path

from fastapi.testclient import TestClient

from vcse.api.server import create_app
from vcse import __version__


client = TestClient(create_app())


def test_health() -> None:
    response = client.get('/health')
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['version'] == __version__


def test_models() -> None:
    response = client.get('/v1/models')
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload[0]['id'] == 'vcse-vrm-1.9'


def test_chat_completion_verified() -> None:
    response = client.post(
        '/v1/chat/completions',
        json={
            'model': 'vcse-vrm-1.9',
            'messages': [
                {'role': 'user', 'content': 'All men are mortal. Socrates is a man. Can Socrates die?'}
            ],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['object'] == 'chat.completion'
    content = payload['choices'][0]['message']['content']
    assert 'Socrates' in content
    assert 'mortal' in content.lower()


def test_chat_completion_inconclusive() -> None:
    response = client.post(
        '/v1/chat/completions',
        json={
            'model': 'vcse-vrm-1.9',
            'messages': [{'role': 'user', 'content': 'Is Socrates a man?'}],
        },
    )
    assert response.status_code == 200
    content = response.json()['choices'][0]['message']['content']
    assert 'Cannot determine' in content


def test_chat_completion_needs_clarification() -> None:
    response = client.post(
        '/v1/chat/completions',
        json={
            'model': 'vcse-vrm-1.9',
            'messages': [{'role': 'user', 'content': 'Is it valid?'}],
        },
    )
    assert response.status_code == 200
    content = response.json()['choices'][0]['message']['content']
    assert 'Additional information required' in content


def test_generation_request() -> None:
    spec_path = Path(__file__).resolve().parents[1] / 'examples' / 'generation' / 'contractor_policy_spec.json'
    spec_text = spec_path.read_text()

    response = client.post(
        '/v1/chat/completions',
        json={
            'model': 'vcse-vrm-1.9',
            'messages': [{'role': 'user', 'content': spec_text}],
        },
    )
    assert response.status_code == 200
    content = response.json()['choices'][0]['message']['content']
    assert 'Access Policy' in content


def test_contradictory_generation_case() -> None:
    payload = {
        'id': 'api_contradiction',
        'artifact_type': 'config',
        'goal': 'Create conflicting artifact',
        'required_fields': {
            'name': 'demo',
            'enabled': True,
            'threshold': 1,
            'subject': 'x',
            'relation': 'equals',
            'object': '4',
        },
        'constraints': [
            {'kind': 'field_present', 'target': 'name'},
            {'kind': 'field_present', 'target': 'enabled'},
            {'kind': 'field_present', 'target': 'threshold'},
        ],
        'success_criteria': ['demo'],
        'memory_claims': [{'subject': 'x', 'relation': 'equals', 'object': '3'}],
    }
    response = client.post(
        '/v1/chat/completions',
        json={
            'model': 'vcse-vrm-1.9',
            'messages': [{'role': 'user', 'content': json.dumps(payload)}],
        },
    )
    assert response.status_code == 200
    content = response.json()['choices'][0]['message']['content']
    assert 'Contradiction detected' in content


def test_debug_mode() -> None:
    response = client.post(
        '/v1/chat/completions?debug=true',
        json={
            'model': 'vcse-vrm-1.9',
            'messages': [{'role': 'user', 'content': 'All men are mortal. Socrates is a man. Can Socrates die?'}],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert 'vcse_debug' in payload
    assert payload['vcse_debug']['status'] == 'VERIFIED'


def test_responses_endpoint_maps_to_same_pipeline() -> None:
    response = client.post(
        '/v1/responses',
        json={
            'model': 'vcse-vrm-1.9',
            'input': 'All men are mortal. Socrates is a man. Can Socrates die?',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['object'] == 'response'
    assert 'Socrates' in payload['output_text']


def test_invalid_input_returns_structured_error() -> None:
    response = client.post('/v1/chat/completions', json={})
    assert response.status_code == 400
    payload = response.json()
    assert 'error' in payload
    assert payload['error']['type'] == 'INVALID_REQUEST'
