#!/bin/bash
# Quick Start Example - Colab Code Executor with Long-Running Operations (LRO)
#
# This script demonstrates:
# 1. Starting a kernel
# 2. Executing code with non-blocking LRO pattern
# 3. Polling for execution status
# 4. Displaying results
# 5. Shutting down the kernel

set -e  # Exit on error

URL="http://127.0.0.1:8000"
echo "=========================================="
echo "Colab Code Executor - Quick Start"
echo "=========================================="
echo "Server URL: $URL"
echo ""

# Check if server is running
if ! curl -s "$URL/health" > /dev/null 2>&1; then
    echo "❌ Error: Server is not running at $URL"
    echo ""
    echo "Please start the server first:"
    echo "  colab-code-executor"
    echo ""
    echo "Or with custom settings:"
    echo "  export JUPYTER_SERVER_URL='http://127.0.0.1:8080'"
    echo "  colab-code-executor --port 8000"
    exit 1
fi

echo "✓ Server is healthy"
echo ""

# Step 1: Start a kernel
echo "1️⃣  Starting kernel..."
KERNEL_RESPONSE=$(curl -s -X POST "$URL/start_kernel")
KERNEL_ID=$(echo "$KERNEL_RESPONSE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
echo "   ✓ Kernel started: $KERNEL_ID"
echo ""

# Step 2: Execute code (returns immediately with execution_id)
echo "2️⃣  Submitting code for execution (non-blocking)..."

# Create JSON payload
CODE=$(cat <<'EOF'
import time
import numpy as np

print("=== Long-Running Computation Demo ===")
print()

# Simulate some computation
print("Generating random data...")
data = np.random.rand(10)
print(f"Data: {data}")
print()

# Progress updates
print("Processing in steps:")
for i in range(5):
    time.sleep(1)
    print(f"  Step {i+1}/5 completed")

print()
print("Computing statistics...")
time.sleep(1)

# Results
result = {
    'mean': float(data.mean()),
    'std': float(data.std()),
    'min': float(data.min()),
    'max': float(data.max())
}

print(f"Results: {result}")
result
EOF
)

PAYLOAD=$(python3 -c "import json; print(json.dumps({'id': '$KERNEL_ID', 'code': $(echo "$CODE" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read()))")}))")

EXEC_RESPONSE=$(curl -s -X POST "$URL/execute_code" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

EXECUTION_ID=$(echo "$EXEC_RESPONSE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["execution_id"])')
echo "   ✓ Execution submitted: $EXECUTION_ID"
echo "   ℹ️  Code is running in background (non-blocking)"
echo ""

# Step 3: Poll for status
echo "3️⃣  Polling for execution status..."
POLL_COUNT=0
while true; do
    POLL_COUNT=$((POLL_COUNT + 1))
    STATUS_RESPONSE=$(curl -s "$URL/execution_status/$EXECUTION_ID")
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["status"])')

    echo "   Poll #$POLL_COUNT: Status = $STATUS"

    if [ "$STATUS" = "COMPLETED" ]; then
        echo "   ✓ Execution completed successfully!"
        break
    elif [ "$STATUS" = "FAILED" ]; then
        echo "   ✗ Execution failed!"
        ERROR=$(echo "$STATUS_RESPONSE" | python3 -c 'import sys,json; data=json.load(sys.stdin); print(data.get("error", "Unknown error"))')
        echo "   Error: $ERROR"
        break
    fi

    sleep 1
done
echo ""

# Step 4: Display results
echo "4️⃣  Displaying results..."
echo ""
echo "$STATUS_RESPONSE" | python3 -c "
import sys
import json

data = json.load(sys.stdin)

# Display execution info
print('📊 EXECUTION SUMMARY')
print('=' * 60)
print(f'Execution ID: {data[\"execution_id\"]}')
print(f'Kernel ID: {data[\"kernel_id\"]}')
print(f'Status: {data[\"status\"]}')

if data.get('started_at') and data.get('completed_at'):
    duration = data['completed_at'] - data['started_at']
    print(f'Duration: {duration:.3f} seconds')

print()

# Display output
if data.get('results'):
    print('📤 OUTPUT')
    print('-' * 60)
    for msg in data['results']:
        msg_type = msg.get('header', {}).get('msg_type', '')
        content = msg.get('content', {})

        # Print stdout
        if msg_type == 'stream' and content.get('name') == 'stdout':
            print(content.get('text', ''), end='')

        # Print return value
        if msg_type == 'execute_result':
            text_data = content.get('data', {}).get('text/plain', '')
            if text_data:
                print()
                print('📊 RETURN VALUE:')
                print(text_data)

    print('-' * 60)
else:
    print('(No output)')
print()
"

# Step 5: Shutdown kernel
echo "5️⃣  Cleaning up..."
curl -s -X POST "$URL/shutdown_kernel" \
  -H "Content-Type: application/json" \
  -d "{\"id\": \"$KERNEL_ID\"}" > /dev/null
echo "   ✓ Kernel shutdown: $KERNEL_ID"
echo ""

echo "=========================================="
echo "✅ Quick Start Complete!"
echo "=========================================="
