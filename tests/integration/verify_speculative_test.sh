#!/usr/bin/env bash
#
# Manual verification script for Speculative Actions test project
#
# This script provides a quick way to verify the test project works
# without running the full pytest suite.

set -e

PROJECT_DIR="/workspace/buildstream/tests/integration/project"
CHECKOUT_DIR="/tmp/speculative-test-checkout"

echo "=== Speculative Actions Manual Test ==="
echo ""

# Check we're in the right place
if [ ! -d "$PROJECT_DIR" ]; then
    echo "ERROR: Project directory not found: $PROJECT_DIR"
    exit 1
fi

cd /workspace/buildstream

echo "Step 1: Clean any existing artifacts..."
rm -rf ~/.cache/buildstream/artifacts/test || true
rm -rf "$CHECKOUT_DIR" || true

echo ""
echo "Step 2: Show element info..."
bst --directory "$PROJECT_DIR" show speculative/top.bst

echo ""
echo "Step 3: Build the full chain (base -> middle -> top)..."
bst --directory "$PROJECT_DIR" build speculative/top.bst

echo ""
echo "Step 4: Checkout the artifact..."
bst --directory "$PROJECT_DIR" artifact checkout speculative/top.bst --directory "$CHECKOUT_DIR"

echo ""
echo "Step 5: Verify artifact contents..."
echo "Files in checkout:"
ls -la "$CHECKOUT_DIR"

echo ""
echo "Content of top.txt:"
cat "$CHECKOUT_DIR/top.txt"

echo ""
echo "Content of from-middle.txt:"
cat "$CHECKOUT_DIR/from-middle.txt"

echo ""
echo "Content of from-base.txt:"
cat "$CHECKOUT_DIR/from-base.txt"

echo ""
echo "=== Test passed! ==="
echo ""
echo "Next steps:"
echo "  1. Modify tests/integration/project/files/speculative/top.txt"
echo "  2. Re-run: bst --directory $PROJECT_DIR build speculative/top.bst"
echo "  3. Verify only top.bst rebuilds (middle.bst and base.bst should be cached)"
