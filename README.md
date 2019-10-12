# LLVM CFG to JSON

Exports an LLVM control flow graph (CFG) to JSON. This pass is different from
LLVM's standard CFG printer in that it captures both *intra* and *inter*
procedural edges (i.e., function calls).

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

## `cfg_stats.py`

Using the results produced by the LLVM pass, calculate some interesting graph
statistics (e.g., number of basic blocks, number of edges, and the graph
eccentricity from the CFG's entry point). The script can also (optionally)
produce a DOT graph of the CFG.

### Running

```bash
clang -fplugin=/path/to/build/libLLVMCFGToJSON.so /path/to/src.c
python cfg_stats.py `pwd`
```
