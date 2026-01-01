# Colab Code execution

This program allows creation of Colab Enterprise Runtimes with code execution.

It does the following:
1. Install a local code execution proxy server
2. Initializes a tunnel service that exposes a public URL
3. Exposes a new API for code execution for MCP server or agents. `/start_kernel` and `/execute_code`


