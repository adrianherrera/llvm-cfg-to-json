# LLVM CFG to JSON

Exports an LLVM control flow graph (CFG) (including function calls) to JSON.
This pass is different from LLVM's standard CFG printer in that it captures both
*intra* and *inter* procedural edges (i.e., function calls).

## Building

```bash
git clone https://github.com/adrianherrera/llvm-cfg-to-json.git
cd llvm-cfg-to-json
mkdir build
cd build
CC=clang CXX=clang++ cmake ..
```

## Running

```bash
clang -fplugin=/path/to/build/libLLVMCFGToJSON.so /path/to/src.c
```

If using autotools/cmake/etc., do

```bash
CFLAGS="-fplugin=/path/to/build/libLLVMCFGToJSON.so"
CXXFLAGS="-fplugin=/path/to/build/libLLVMCFGToJSON.so"
make
```

## `cfg_eccentricity.py`

Using the results produced by the LLVM pass, calculate the eccentricity from the
CFG's entry point.
