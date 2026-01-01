# Colab Code Executor

A FastAPI server for remote Jupyter kernel management with code execution capabilities.

This package allows creation of remote Jupyter kernel runtimes with code execution, providing:
1. A local code execution proxy server
2. REST API endpoints for kernel management
3. WebSocket-based code execution interface for MCP servers or AI agents

## Features

- **Kernel Management**: Start, execute code on, and shutdown remote Jupyter kernels
- **WebSocket Communication**: Efficient real-time code execution via WebSocket
- **Crash Recovery**: Automatic retry logic and crash handling
- **Structured Logging**: JSON-formatted logs with timezone-aware timestamps
- **Type Safety**: Full type hints and Pydantic validation
- **Environment Configuration**: Configure via environment variables or `.env` file
- **Modern Python**: Built with Python 3.10+ features (PEP 604 union syntax, StrEnum)

## Installation

### From PyPI (once published)

```bash
pip install colab-code-executor
```

### From Source

```bash
git clone git@github.com:codeexec/colab.git
cd colab
pip install -e .
```

### Development Install

```bash
pip install -e ".[dev]"
```

## Quick Start

### Command Line

```bash
# Using environment variable
export JUPYTER_SERVER_URL="http://127.0.0.1:8888"
colab-code-executor

# Using CLI arguments
colab-code-executor --server-url http://127.0.0.1:8888 --port 8000

# With authentication token
colab-code-executor --server-url http://127.0.0.1:8888 --token mytoken123

# With debug logging
colab-code-executor --log-level DEBUG
```

### Python API

```python
import asyncio
from colab_code_executor import Settings, StructuredLogger, JupyterClient, KernelManager

async def main():
    # Configure settings
    settings = Settings(
        server_url="http://127.0.0.1:8888",
        token="your-token-here"
    )
    logger = StructuredLogger()

    # Use async context manager for proper cleanup
    async with JupyterClient(settings, logger) as client:
        manager = KernelManager(client, logger)

        # Start a kernel
        kernel = await manager.start_kernel()
        print(f"Kernel started: {kernel['id']}")

        # Execute code
        result = await manager.execute_code(
            kernel['id'],
            "print('Hello from Jupyter!')"
        )
        print(f"Execution results: {result}")

        # Shutdown kernel
        await manager.shutdown_kernel(kernel['id'])

asyncio.run(main())
```

## API Endpoints

### `POST /start_kernel`
Start a new Jupyter kernel.

**Response:**
```json
{
  "id": "kernel-uuid-here"
}
```

### `POST /execute_code`
Execute code on a kernel.

**Request:**
```json
{
  "id": "kernel-uuid-here",
  "code": "print('Hello, World!')"
}
```

**Response:**
```json
{
  "results": [
    {
      "header": {...},
      "content": {...},
      ...
    }
  ]
}
```

### `POST /shutdown_kernel`
Shutdown a kernel.

**Request:**
```json
{
  "id": "kernel-uuid-here"
}
```

**Response:**
```json
{
  "message": "Kernel kernel-uuid-here shutdown"
}
```

### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "ok"
}
```

## Configuration

Configure via environment variables with `JUPYTER_` prefix or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `JUPYTER_SERVER_URL` | `http://127.0.0.1:8080` | Jupyter server URL |
| `JUPYTER_TOKEN` | `""` | Jupyter authentication token |
| `JUPYTER_TIMEOUT_CONNECT` | `10.0` | Connection timeout (seconds) |
| `JUPYTER_TIMEOUT_TOTAL` | `30.0` | Total request timeout (seconds) |
| `JUPYTER_CRASH_SLEEP_DURATION` | `30.0` | Crash recovery sleep (seconds) |
| `JUPYTER_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARN, ERROR) |

## Development

### Setup

```bash
# Clone repository
git clone git@github.com:codeexec/colab.git
cd colab

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"
```

### Run Tests

```bash
# Run test script
./scripts/test_local_install.sh

# Or use pytest (if available)
pytest
pytest --cov=colab_code_executor --cov-report=html
```

### Run Server Locally

```bash
# Using the CLI (recommended)
export JUPYTER_SERVER_URL="http://127.0.0.1:8888"
colab-code-executor

# Or with options
colab-code-executor --server-url http://127.0.0.1:8888 --port 8000

# Direct Python execution
python -m colab_code_executor.server
```

## Publishing to PyPI

See [PUBLISHING.md](PUBLISHING.md) for detailed instructions on publishing this package to PyPI.

Quick publish:
```bash
./scripts/publish.sh
```

For token-based upload to TestPyPI:
```bash
export TESTPYPI_TOKEN='pypi-YOUR-TOKEN-HERE'
./scripts/upload_with_token.sh
```

## Requirements

- Python 3.10+
- Local or remote Jupyter server
- Dependencies: fastapi, uvicorn, httpx, websockets, pydantic, pydantic-settings

## Project Structure

```
colab-code-executor/
├── src/
│   └── colab_code_executor/     # Main package
│       ├── __init__.py          # Package exports
│       ├── server.py            # FastAPI server implementation
│       ├── cli.py               # Command-line interface
│       └── py.typed             # Type checking marker
├── scripts/                     # Utility scripts
│   ├── README.md               # Scripts documentation
│   ├── test_local_install.sh   # Local testing script
│   ├── publish.sh              # Build and publish script
│   └── quickstart.sh           # Quick start script
├── pyproject.toml              # Package metadata and dependencies
├── setup.py                    # Backward compatibility
├── MANIFEST.in                 # Distribution file inclusion rules
├── LICENSE                     # MIT License
├── README.md                   # This file
├── PUBLISHING.md               # PyPI publishing guide
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.