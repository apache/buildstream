# Speculative Actions Test Project

This directory contains test elements for verifying the Speculative Actions PoC implementation.

## Test Elements

The test project consists of a 3-element dependency chain that uses trexe to record subactions:

```
trexe.bst (provides /usr/bin/trexe from buildbox)
    ↓
base.bst (depends on base.bst from project + trexe)
    ↓
middle.bst (depends on speculative/base.bst + trexe)
    ↓
top.bst (depends on speculative/middle.bst + trexe)
```

### Element Details

- **trexe.bst**: Imports trexe binary from buildbox build directory
- **base.bst**: Uses `trexe -- cat` to process base.txt, recording file operations as subactions
- **middle.bst**: Uses trexe to combine files from sources and base dependency
- **top.bst**: Uses trexe to aggregate files from entire dependency chain (top + middle + base)

**Key Feature**: Each element uses `trexe --input <files> -- <command>` to wrap simple file operations (cat, echo, wc). Each trexe invocation records the operation as a subaction in the ActionResult with explicit input declarations. This is essential for the Speculative Actions PoC to have actual subactions to extract and process.

**Why simple commands?**: Using `cat` and shell commands instead of compilation keeps the test fast and simple while still exercising the full subaction recording mechanism. The `--input` flags explicitly declare dependencies, which is what the PoC needs to trace.

## Test Scenarios

### 1. Basic Build (`test_speculative_actions_basic`)
- Builds the full chain from scratch
- Verifies all artifacts are created correctly
- Checks that speculative actions are generated and stored

### 2. Rebuild with Source Change (`test_speculative_actions_rebuild_with_source_change`)
- Builds initial chain
- Modifies `top.txt` source file
- Rebuilds and verifies only necessary elements are rebuilt
- **Key test**: In future, speculative actions from middle.bst should help adapt cached artifacts

### 3. Dependency Chain (`test_speculative_actions_dependency_chain`)
- Builds each element independently
- Verifies dependency relationships work correctly
- Confirms artifacts from dependencies are accessible

## Manual Testing

To manually test the project:

```bash
# From buildstream root
cd /workspace/buildstream

# Build the full chain
bst --directory tests/integration/project build speculative/top.bst

# Check the artifact
bst --directory tests/integration/project artifact checkout speculative/top.bst --directory /tmp/checkout
ls -la /tmp/checkout

# Modify source and rebuild
echo "Modified content" > tests/integration/project/files/speculative/top.txt
bst --directory tests/integration/project build speculative/top.bst
```

## Integration with Speculative Actions PoC

The PoC implementation includes:

1. **Generator** (`src/buildstream/_speculative_actions/generator.py`):
   - Runs after BuildQueue
   - Extracts subactions from ActionResult
   - Traverses directory trees to identify file sources
   - Creates overlay metadata

2. **Instantiator** (`src/buildstream/_speculative_actions/instantiator.py`):
   - Runs during cache priming (before BuildQueue)
   - Reads speculative actions from artifacts
   - Creates adapted actions with overlays applied
   - Submits to Remote Execution

3. **Queue Integration**:
   - `SpeculativeActionGenerationQueue`: Generates actions after builds
   - `SpeculativeCachePrimingQueue`: Instantiates and submits actions before builds

## Future Enhancements

Currently, the tests verify basic functionality. Future additions should verify:

- [ ] Speculative actions are stored in artifact proto's `speculative_actions` field
- [ ] Actions can be retrieved from CAS using the stored digest
- [ ] Overlays correctly identify SOURCE vs ARTIFACT types
- [ ] Cache key optimization skips overlay generation for strong cache hits
- [ ] Weak cache hits benefit from speculative action reuse
- [ ] Remote execution successfully executes adapted actions
