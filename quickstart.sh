#!/bin/bash
# Quick Start Example - Jupyter Kernel API

# Start a kernel
URL="http://127.0.0.1:8000"
echo "Remote URL $URL"

echo "Starting kernel..."
KERNEL_ID=$(curl -s -X POST $URL/start_kernel | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
echo "Kernel ID: $KERNEL_ID"
echo ""

# Execute some code
echo "Executing code..."

# Create JSON payload with proper escaping
python3 -c "
import json
payload = {
    'id': '$KERNEL_ID',
    'code': '''import numpy as np
import pandas as pd

print('NumPy version:', np.__version__)
print('Pandas version:', pd.__version__)
print()

data = np.random.rand(5)
print('Random data:', data)
print('Mean:', data.mean())
print('Std:', data.std())
'''
}
print(json.dumps(payload))
" | curl -s -X POST $URL/execute_code \
  -H "Content-Type: application/json" \
  -d @- | python3 ~/extract_output.py

echo ""
echo "Done! Kernel $KERNEL_ID is still running."
echo "To shutdown: curl -X POST $URL/shutdown_kernel -H 'Content-Type: application/json' -d '{\"id\": \"$KERNEL_ID\"}'"
