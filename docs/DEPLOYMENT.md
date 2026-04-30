# Deployment

VCSE 2.0.0 is packaged for local installation, container execution, and API serving.

## Local

```bash
python -m pip install -e .
vcse --help
vcse serve
```

## Docker

```bash
docker build -t vcse .
docker run -p 8000:8000 vcse
```

## Operational Notes

- Same inputs produce the same outputs.
- The API server is deterministic.
- Configuration can come from environment variables or a config file.
