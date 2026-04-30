# Configuration

VCSE settings can be loaded from environment variables or a JSON/YAML config file.

## Environment Variables

- `VCSE_SEARCH_BACKEND`
- `VCSE_TS3_ENABLED`
- `VCSE_INDEXING_ENABLED`
- `VCSE_TOP_K_RULES`
- `VCSE_TOP_K_PACKS`
- `VCSE_API_HOST`
- `VCSE_API_PORT`
- `VCSE_API_DEBUG`
- `VCSE_API_TIMEOUT_SECONDS`
- `VCSE_API_MAX_REQUEST_BYTES`
- `VCSE_LOG_LEVEL`
- `VCSE_PROFILING_ENABLED`

## Config File

Supported file types:

- `.json`
- `.yaml`
- `.yml`

Example:

```json
{
  "search_backend": "mcts",
  "ts3_enabled": true,
  "indexing_enabled": true,
  "api_host": "0.0.0.0",
  "api_port": 8000
}
```

CLI arguments override loaded settings.
