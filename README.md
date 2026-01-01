# Colab Code Executor

A FastAPI server for remote Jupyter kernel management with code execution capabilities.

This package allows creation of remote Jupyter kernel runtimes with code execution, providing:
1. A local code execution proxy server
2. REST API endpoints for kernel management
3. WebSocket-based code execution interface for MCP servers or AI agents

## Features

- **Kernel Management**: Start, execute code on, and shutdown remote Jupyter kernels
- **Long-Running Operations**: Non-blocking code execution with status polling
- **WebSocket Communication**: Efficient real-time code execution via WebSocket
- **Crash Recovery**: Automatic retry logic and crash handling
- **Structured Logging**: JSON-formatted logs with timezone-aware timestamps
- **Type Safety**: Full type hints and Pydantic validation
- **Environment Configuration**: Configure via environment variables or `.env` file
- **Modern Python**: Built with Python 3.10+ features (PEP 604 union syntax, StrEnum)
- **Comprehensive Testing**: Unit tests and integration tests included

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

#### Using the REST API (Recommended)

```python
import requests
import time

# Start a kernel
response = requests.post("http://localhost:8000/start_kernel")
kernel_id = response.json()["id"]
print(f"Kernel started: {kernel_id}")

# Execute code (returns immediately)
response = requests.post(
    "http://localhost:8000/execute_code",
    json={
        "id": kernel_id,
        "code": "print('Hello from Jupyter!')"
    }
)
execution_id = response.json()["execution_id"]
print(f"Execution started: {execution_id}")

# Poll for results
while True:
    response = requests.get(f"http://localhost:8000/execution_status/{execution_id}")
    data = response.json()

    print(f"Status: {data['status']}")

    if data['status'] == 'COMPLETED':
        print("Results:", data['results'])
        break
    elif data['status'] == 'FAILED':
        print("Error:", data.get('error'))
        break

    time.sleep(0.5)  # Poll every 500ms

# Shutdown kernel
requests.post("http://localhost:8000/shutdown_kernel", json={"id": kernel_id})
```

#### Using the Internal API

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

        # Execute code (returns execution_id)
        result = await manager.execute_code(
            kernel['id'],
            "print('Hello from Jupyter!')"
        )
        execution_id = result['execution_id']

        # Poll for status
        while True:
            status = manager.get_execution_status(execution_id)
            if status['status'] in ['COMPLETED', 'FAILED']:
                print(f"Results: {status}")
                break
            await asyncio.sleep(0.5)

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
Execute code on a kernel (returns immediately with execution ID).

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
  "execution_id": "execution-uuid-here"
}
```

**Note:** Code execution runs asynchronously. Use the `/execution_status` endpoint to check progress and retrieve results.

### `GET /execution_status/{execution_id}`
Get the status and results of a code execution operation.

Example:

Start Kernel
```
curl -X POST http://127.0.0.1:8000/start_kernel
```

Execute code
```
curl -X POST -H "Content-Type: application/json" -d '{"id": "kernel-uuid-here", "code": "import time\nfor i in range(60):\n    time.sleep(1)\n    print(i+1)"}' http://127.0.0.1:8000/execute_code
```

Get status
```
curl -s http://127.0.0.1:8000/execution_status/execution-uuid-here | jq .
```

**Response (Running):**
```json
{
  "execution_id": "execution-uuid-here",
  "kernel_id": "kernel-uuid-here",
  "status": "RUNNING",
  "created_at": 1767256211.8526392,
  "started_at": 1767256211.8529763,
  "completed_at": null,
  "output": {
    "stdout": "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\n13\n14\n15\n16\n17\n18\n",
    "stderr": "",
    "result": null,
    "error": null,
    "traceback": null,
    "execution_count": null,
    "status": "ok"
  }
}
```

**Response (Completed):**
```json
curl -s http://127.0.0.1:8000/execution_status/execution-uuid-here | jq .
{
  "execution_id": "execution-uuid-here",
  "kernel_id": "kernel-uuid-here",
  "status": "COMPLETED",
  "created_at": 1767256211.8526392,
  "started_at": 1767256211.8529763,
  "completed_at": 1767256271.987443,
  "output": {
    "stdout": "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\n13\n14\n15\n16\n17\n18\n19\n20\n21\n22\n23\n24\n25\n26\n27\n28\n29\n30\n31\n32\n33\n34\n35\n36\n37\n38\n39\n40\n41\n42\n43\n44\n45\n46\n47\n48\n49\n50\n51\n52\n53\n54\n55\n56\n57\n58\n59\n60\n",
    "stderr": "",
    "result": null,
    "error": null,
    "traceback": null,
    "execution_count": 1,
    "status": "ok"
  }
}
```

**Status Values:**
- `PENDING`: Execution queued but not started
- `RUNNING`: Execution in progress
- `COMPLETED`: Execution finished successfully
- `FAILED`: Execution failed with error

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

## Long-Running Operations (LRO)

Code execution uses a non-blocking, asynchronous pattern:

1. **Submit Code**: POST to `/execute_code` returns immediately with an `execution_id`
2. **Poll Status**: GET `/execution_status/{execution_id}` to check progress
3. **Retrieve Results**: Results available when status is `COMPLETED`

### Benefits

- **Non-blocking**: Client doesn't wait for long-running code
- **Scalable**: Handle multiple concurrent executions
- **Observable**: Monitor execution progress in real-time
- **Resilient**: Execution continues even if client disconnects

### Example Workflow

```python
import requests
import time

# Submit execution
response = requests.post("http://localhost:8000/execute_code", json={
    "id": "kernel-id",
    "code": "import time; time.sleep(5); print('Done!')"
})
execution_id = response.json()["execution_id"]

# Poll until complete
while True:
    status = requests.get(f"http://localhost:8000/execution_status/{execution_id}").json()
    if status["status"] in ["COMPLETED", "FAILED"]:
        break
    time.sleep(1)

print("Results:", status.get("results"))
```

See [LRO_API.md](LRO_API.md) for detailed API documentation.

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

## Testing

The project includes comprehensive unit and integration tests.

### Unit Tests

Located in `src/colab_code_executor/test_server.py`, covering:
- StructuredLogger functionality
- Settings configuration
- CrashRecoveryState behavior
- JupyterClient operations
- KernelManager lifecycle
- API route handlers

```bash
# Run unit tests
cd src/colab_code_executor
pytest test_server.py -v

# With coverage report
pytest test_server.py --cov=server --cov-report=html
```

### Integration Tests

Located in `test_lro.py`, demonstrating the Long-Running Operations pattern with 5 comprehensive test cases:

1. **Simple Print**: Basic output testing
2. **Return Values**: Fibonacci computation with both output and return value
3. **Long-Running**: Progress updates over 5 seconds
4. **Error Handling**: Division by zero with traceback
5. **Multiple Outputs**: Complex computation with dictionary return

```bash
# Ensure Jupyter server is running
jupyter lab --port 8080 &

# Start the FastAPI server
python -m uvicorn colab_code_executor.server:app --port 8000 &

# Run integration tests
python test_lro.py
```

### Automated Testing

The publish script runs all tests automatically:

```bash
./scripts/publish.sh           # Runs tests before building
./scripts/publish.sh --no-test # Skip tests
```

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

Quick publish with automated testing:
```bash
# Ensure Jupyter server is running for integration tests
jupyter lab --port 8080 &

# Run tests, build, and publish (interactive)
./scripts/publish.sh

# Skip tests if already validated
./scripts/publish.sh --no-test
```

The publish script automatically:
1. Installs dev dependencies
2. Runs unit tests (`pytest test_server.py`)
3. Runs integration tests (`test_lro.py`)
4. Builds the package
5. Validates with `twine check`
6. Prompts for upload target (TestPyPI/PyPI/Skip)

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
│       ├── server.py            # FastAPI server with LRO support
│       ├── cli.py               # Command-line interface
│       ├── test_server.py       # Unit tests (pytest)
|       ├── test_lro.py          # Integration tests for LRO pattern
│       └── py.typed             # Type checking marker
├── scripts/                     # Utility scripts
│   ├── README.md               # Scripts documentation
│   ├── publish.sh              # Automated test, build, and publish
│   └── quickstart.sh           # Quick start script
├── pyproject.toml              # Package metadata and dependencies
├── MANIFEST.in                 # Distribution file inclusion rules
├── LICENSE                     # MIT License
├── README.md                   # This file
└── PUBLISHING.md               # PyPI publishing guide
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.