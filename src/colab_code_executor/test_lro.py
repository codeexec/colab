#!/usr/bin/env python3
"""Test script for Long-Running Operation (LRO) pattern in code execution.

This script demonstrates:
1. Starting a kernel
2. Executing code (returns immediately with execution_id)
3. Polling for execution status
4. Retrieving results when completed
"""

import time
import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"

def start_kernel():
    """Start a new kernel."""
    print("Starting kernel...")
    response = requests.post(f"{BASE_URL}/start_kernel")
    response.raise_for_status()
    kernel_id = response.json()["id"]
    print(f"✓ Kernel started: {kernel_id}\n")
    return kernel_id

def execute_code(kernel_id, code):
    """Execute code and return execution_id."""
    print(f"Executing code (returns immediately)...")
    print(f"Code: {code[:50]}...")
    response = requests.post(
        f"{BASE_URL}/execute_code",
        json={"id": kernel_id, "code": code}
    )
    response.raise_for_status()
    execution_id = response.json()["execution_id"]
    print(f"✓ Execution started: {execution_id}\n")
    return execution_id

def get_execution_status(execution_id):
    """Get execution status."""
    response = requests.get(f"{BASE_URL}/execution_status/{execution_id}")
    response.raise_for_status()
    return response.json()

def poll_until_complete(execution_id, poll_interval=0.5):
    """Poll execution status until complete or failed."""
    print("Polling for execution status...")
    while True:
        status_data = get_execution_status(execution_id)
        status = status_data["status"]

        print(f"  Status: {status}")

        if status == "COMPLETED":
            print("\n✓ Execution completed!")
            return status_data
        elif status == "FAILED":
            print(f"\n✗ Execution failed: {status_data.get('error')}")
            return status_data

        time.sleep(poll_interval)

def print_results(status_data):
    """Print execution results."""
    print("\n" + "="*60)
    print("EXECUTION RESULTS")
    print("="*60)
    print(f"Execution ID: {status_data['execution_id']}")
    print(f"Kernel ID: {status_data['kernel_id']}")
    print(f"Status: {status_data['status']}")

    # Calculate duration if completed
    if status_data['started_at'] and status_data['completed_at']:
        duration = status_data['completed_at'] - status_data['started_at']
        print(f"Duration: {duration:.3f} seconds")

    if status_data['status'] == 'COMPLETED':
        # Use processed output instead of raw results
        output = status_data.get('output', {})

        # STDOUT
        if output.get('stdout'):
            print("\n📤 STDOUT:")
            print(f"  {output['stdout']}", end='')
            if not output['stdout'].endswith('\n'):
                print()

        # STDERR
        if output.get('stderr'):
            print("\n⚠️  STDERR:")
            print(f"  {output['stderr']}", end='')
            if not output['stderr'].endswith('\n'):
                print()

        # Return value/result
        if output.get('result') is not None:
            print("\n📊 RETURN VALUE:")
            print(f"  {output['result']}")

        # Error
        if output.get('error'):
            print("\n❌ ERROR:")
            print(f"  {output['error']}")
            if output.get('traceback'):
                print("\n  Traceback:")
                for line in output['traceback']:
                    print(f"    {line}")

        # Show summary if no output
        if not any([output.get('stdout'), output.get('stderr'),
                   output.get('result') is not None, output.get('error')]):
            print("\n(No output produced)")

    elif status_data['status'] == 'FAILED':
        print(f"\n❌ EXECUTION FAILED")
        print(f"Error: {status_data.get('error')}")

    print("="*60)

def main():
    """Run the test."""
    try:
        # Start kernel
        kernel_id = start_kernel()

        # Test 1: Simple print statement
        print("TEST 1: Simple print statement")
        print("-" * 40)
        code1 = "print('Hello from long-running operation!')"
        execution_id1 = execute_code(kernel_id, code1)
        result1 = poll_until_complete(execution_id1)
        print_results(result1)

        # Test 2: Code with return value
        print("\n\nTEST 2: Code with return value")
        print("-" * 40)
        code2 = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

result = [fibonacci(i) for i in range(10)]
print(f"First 10 Fibonacci numbers: {result}")
result  # This will be the return value
"""
        execution_id2 = execute_code(kernel_id, code2)
        result2 = poll_until_complete(execution_id2)
        print_results(result2)

        # Test 3: Longer execution with progress
        print("\n\nTEST 3: Long-running code with progress updates")
        print("-" * 40)
        code3 = """
import time
total = 5
print(f"Processing {total} items...")
for i in range(total):
    print(f'  → Processing item {i+1}/{total}')
    time.sleep(1)
print('✓ All items processed!')
"""
        execution_id3 = execute_code(kernel_id, code3)
        result3 = poll_until_complete(execution_id3, poll_interval=1)
        print_results(result3)

        # Test 4: Code with error
        print("\n\nTEST 4: Code that produces an error")
        print("-" * 40)
        code4 = """
print("This will execute fine")
x = 1 / 0  # This will cause a ZeroDivisionError
print("This won't execute")
"""
        execution_id4 = execute_code(kernel_id, code4)
        result4 = poll_until_complete(execution_id4)
        print_results(result4)

        # Test 5: Multiple outputs
        print("\n\nTEST 5: Multiple outputs and computations")
        print("-" * 40)
        code5 = """
import math

# Some calculations
print("Computing some math operations...")
values = [1, 4, 9, 16, 25]
print(f"Input values: {values}")

sqrt_values = [math.sqrt(x) for x in values]
print(f"Square roots: {sqrt_values}")

# Return a dictionary
{
    'input': values,
    'sqrt': sqrt_values,
    'sum': sum(sqrt_values)
}
"""
        execution_id5 = execute_code(kernel_id, code5)
        result5 = poll_until_complete(execution_id5)
        print_results(result5)

        print("\n✓ All tests completed successfully!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
