# API Adapter

VCSE 1.9.0 exposes an OpenAI-compatible HTTP adapter for deterministic VRM
execution.

## Important

Compatibility is request/response shape compatibility, not LLM behavior.

VCSE still returns verifier-grounded states such as:

- `VERIFIED`
- `INCONCLUSIVE`
- `NEEDS_CLARIFICATION`
- `CONTRADICTORY`
- `UNSATISFIABLE`
- artifact statuses for generation

No probabilistic sampling is used.

## Endpoints

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/responses`

## Supported Request Shape

```json
{
  "model": "vcse-vrm-1.9",
  "messages": [
    {"role": "user", "content": "All men are mortal. Socrates is a man. Can Socrates die?"}
  ],
  "temperature": 0,
  "top_p": 1,
  "max_tokens": 256
}
```

`temperature`, `top_p`, and similar fields are accepted but ignored.

## Debug Mode

Use query param `?debug=true` to include `vcse_debug` in responses.

## Run Server

```bash
vcse serve
vcse serve --host 0.0.0.0 --port 8000
```

## curl Examples

```bash
curl http://localhost:8000/health

curl http://localhost:8000/v1/models

curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"vcse-vrm-1.9","messages":[{"role":"user","content":"All men are mortal. Socrates is a man. Can Socrates die?"}]}'
```

## Python Example

```python
import requests

payload = {
    "model": "vcse-vrm-1.9",
    "messages": [{"role": "user", "content": "Is Socrates a man?"}],
}

r = requests.post("http://localhost:8000/v1/chat/completions", json=payload, timeout=30)
print(r.json())
```
