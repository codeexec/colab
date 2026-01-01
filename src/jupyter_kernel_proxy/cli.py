"""Command-line interface for Jupyter Kernel Proxy."""

import sys
import argparse
import uvicorn
from .server import Settings, StructuredLogger, LogLevel


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Jupyter Kernel Proxy - FastAPI server for remote Jupyter kernel management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with default settings (requires JUPYTER_SERVER_URL env var)
  jupyter-kernel-proxy

  # Start with custom Jupyter server URL
  jupyter-kernel-proxy --server-url http://localhost:8888

  # Start with authentication token
  jupyter-kernel-proxy --server-url http://localhost:8888 --token mytoken123

  # Start with debug logging
  jupyter-kernel-proxy --log-level DEBUG

  # Custom host and port
  jupyter-kernel-proxy --host 127.0.0.1 --port 9000

Environment Variables:
  JUPYTER_SERVER_URL    - Jupyter server URL (default: http://127.0.0.1:8080)
  JUPYTER_TOKEN         - Jupyter authentication token
  JUPYTER_LOG_LEVEL     - Log level (DEBUG, INFO, WARN, ERROR)
        """
    )

    parser.add_argument(
        "--server-url",
        type=str,
        help="Jupyter server URL (env: JUPYTER_SERVER_URL)"
    )

    parser.add_argument(
        "--token",
        type=str,
        help="Jupyter authentication token (env: JUPYTER_TOKEN)"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARN", "ERROR"],
        help="Logging level (env: JUPYTER_LOG_LEVEL)"
    )

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)"
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0"
    )

    args = parser.parse_args()

    # Build settings dict from CLI args
    settings_override = {}
    if args.server_url:
        settings_override["server_url"] = args.server_url
    if args.token:
        settings_override["token"] = args.token
    if args.log_level:
        settings_override["log_level"] = args.log_level

    # Load settings (CLI args override env vars)
    try:
        settings = Settings(**settings_override)
    except Exception as e:
        print(f"Error loading settings: {e}", file=sys.stderr)
        sys.exit(1)

    # Display startup info
    logger = StructuredLogger(min_level=settings.log_level)
    logger.info("cli", f"Starting Jupyter Kernel Proxy on {args.host}:{args.port}")
    logger.info("cli", f"Jupyter server: {settings.server_url}")
    logger.info("cli", f"Log level: {settings.log_level}")

    # Start server
    uvicorn.run(
        "jupyter_kernel_proxy.server:app",
        host=args.host,
        port=args.port,
        log_level=settings.log_level.lower()
    )


if __name__ == "__main__":
    main()
