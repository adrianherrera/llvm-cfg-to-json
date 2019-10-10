# LLVM CFG to JSON

Exports an LLVM control flow graph (CFG) (including function calls) to JSON.
This pass is different from LLVM's standard CFG printer in that it captures both
*intra* and *inter* procedural edges (i.e., function calls).

## `cfg_eccentricity.py`

Using the results produced by the LLVM pass, calculate the eccentricity from the
CFG's entry point.
