#!/bin/bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

echo "Running tests for lemonade-sdk..."
echo "================================"

# Use a small model for fast testing
MODEL="Llama-3.2-1B-Instruct-GGUF"
# v10.x default lemond port
PORT=13305

# Start the lemond server in the background. Upstream v10.x split the CLI:
# `lemond` runs the server; `lemonade` is the client CLI (pull/list/etc).
echo ""
echo "Starting lemond on default port ${PORT}..."
lemond > /tmp/lemonade.log 2>&1 &
SERVER_PID=$!

cleanup() {
  echo ""
  echo "Stopping server..."
  kill $SERVER_PID 2>/dev/null
  sleep 1
  pkill -9 lemond 2>/dev/null
}
trap cleanup EXIT

# Wait for server to be ready
echo "Waiting for server to be ready..."
for i in {1..60}; do
  if curl -s http://localhost:$PORT/api/v1/health > /dev/null 2>&1; then
    echo "Server is ready!"
    break
  fi
  if [ $i -eq 60 ]; then
    echo "Server failed to start!"
    cat /tmp/lemonade.log
    exit 1
  fi
  sleep 1
done

# Pull the model
echo ""
echo "Pulling model $MODEL..."
lemonade pull $MODEL || {
  echo "Pull failed; the server may still be able to lazy-load on first request."
}

sleep 2

# Test the API with an actual completion request
echo ""
echo "Testing completion API with model $MODEL..."
RESPONSE=$(curl -s -X POST http://localhost:$PORT/api/v1/completions   -H "Content-Type: application/json"   -d '{
    "model": "'$MODEL'",
    "prompt": "Why is the sky blue?",
    "max_tokens": 100,
    "temperature": 0.7
  }')

echo "Raw API Response:"
echo "$RESPONSE" | python3 -m json.tool || echo "$RESPONSE"

if echo "$RESPONSE" | grep -q "choices"; then
  echo ""
  echo "================================"
  echo "✓ lemonade-sdk API test passed!"
  exit 0
else
  echo ""
  echo "✗ API test failed - no valid completion received"
  exit 1
fi
