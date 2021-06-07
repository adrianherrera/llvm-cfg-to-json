//===-- CFGToJSON.cpp - Export CFG to JSON --------------------------------===//
//
//                     The LLVM Compiler Infrastructure
//
// This file is distributed under the University of Illinois Open Source
// License. See LICENSE.TXT for details.
//
//===----------------------------------------------------------------------===//
///
/// \file
/// Exports an LLVM control flow graph (CFG), including function calls, to JSON.
///
//===----------------------------------------------------------------------===//

#include "llvm/IR/CFG.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/InlineAsm.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/LegacyPassManager.h"
#include "llvm/IR/Module.h"
#include "llvm/Pass.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/Path.h"
#include "llvm/Transforms/IPO/PassManagerBuilder.h"

#include "json/json.h"

using namespace llvm;

#define DEBUG_TYPE "cfg-to-json"

namespace {

using SourceRange = std::pair<DebugLoc, DebugLoc>;

cl::opt<std::string> OutDir("cfg-outdir", cl::desc("Output directory"),
                            cl::value_desc("directory"), cl::init("."));

class CFGToJSON : public ModulePass {
public:
  static char ID;
  CFGToJSON() : ModulePass(ID) {}

  virtual void getAnalysisUsage(AnalysisUsage &) const override;
  virtual void print(raw_ostream &, const Module *) const override;
  virtual bool runOnModule(Module &) override;
};

} // anonymous namespace

char CFGToJSON::ID = 0;

// Adapted from llvm::CFGPrinter::getSimpleNodeLabel
static std::string getBBLabel(const BasicBlock *BB) {
  if (!BB->getName().empty()) {
    return BB->getName().str();
  }

  std::string Str;
  raw_string_ostream OS(Str);

  BB->printAsOperand(OS, false);
  return OS.str();
}

static SourceRange getSourceRange(const BasicBlock *BB) {
  DebugLoc Start;
  for (const auto &I : *BB) {
    const auto &DbgLoc = I.getDebugLoc();
    if (DbgLoc) {
      Start = DbgLoc;
      break;
    }
  }

  return {Start, BB->getTerminator()->getDebugLoc()};
}

static filter_iterator<
    BasicBlock::const_iterator,
    std::function<bool(const Instruction &)>>::difference_type
sizeWithoutDebug(const BasicBlock *BB) {
  return std::distance(BB->instructionsWithoutDebug().begin(),
                       BB->instructionsWithoutDebug().end());
}

void CFGToJSON::getAnalysisUsage(AnalysisUsage &AU) const {
  AU.setPreservesAll();
}

void CFGToJSON::print(raw_ostream &OS, const Module *M) const {
  // Nothing to do here
}

bool CFGToJSON::runOnModule(Module &M) {
  SmallPtrSet<const BasicBlock *, 32> SeenBBs;
  SmallVector<const BasicBlock *, 32> Worklist;

  SmallVector<std::pair<const StringRef, Json::Value>, 32> JFuncs;
  Json::Value JNodes, JEdges, JCalls, JIndirectCalls, JReturns;

  for (const auto &F : M) {
    if (F.isDeclaration()) {
      continue;
    }
    SeenBBs.clear();
    Worklist.clear();
    Worklist.push_back(&F.getEntryBlock());

    JNodes.clear();
    JEdges.clear();
    JCalls.clear();
    JIndirectCalls.clear();
    JReturns.clear();

    while (!Worklist.empty()) {
      auto *BB = Worklist.pop_back_val();

      // Prevent loops
      const auto Res = SeenBBs.insert(BB);
      if (!Res.second) {
        continue;
      }

      // Save the node
      const auto &BBLabel = getBBLabel(BB);
      const auto &[SrcStart, SrcEnd] = getSourceRange(BB);

      Json::Value JBB;
      JBB["start_line"] = SrcStart ? SrcStart.getLine() : Json::Value();
      JBB["end_line"] = SrcEnd ? SrcEnd.getLine() : Json::Value();
      JBB["size"] = sizeWithoutDebug(BB);
      JNodes[BBLabel] = JBB;

      // Save the intra-procedural edges
      for (auto SI = succ_begin(BB), SE = succ_end(BB); SI != SE; ++SI) {
        Json::Value JEdge;
        JEdge["src"] = BBLabel;
        JEdge["dst"] = getBBLabel(*SI);
        JEdges.append(JEdge);

        Worklist.push_back(*SI);
      }

      // Save the inter-procedural edges
      for (auto &I : *BB) {
        // Skip debug instructions
        if (I.isDebugOrPseudoInst()) {
          continue;
        }

        if (const auto *CB = dyn_cast<CallBase>(&I)) {
          if (CB->isIndirectCall()) {
            JIndirectCalls.append(BBLabel);
          } else {
            const auto *Target = CB->getCalledOperand()->stripPointerCasts();

            Json::Value JCall;
            JCall["src"] = BBLabel;
            JCall["dst"] = [&Target]() {
              if (const auto *IAsm = dyn_cast<InlineAsm>(Target)) {
                return IAsm->getAsmString();
              } else {
                return Target->getName().str();
              }
            }();

            JCalls.append(JCall);
          }
        }
      }

      // Save the return
      if (isa<ReturnInst>(BB->getTerminator())) {
        JReturns.append(BBLabel);
      }
    }

    // Save function
    Json::Value JFunc;
    JFunc["entry"] = getBBLabel(&F.getEntryBlock());
    JFunc["nodes"] = JNodes;
    JFunc["edges"] = JEdges;
    JFunc["calls"] = JCalls;
    JFunc["returns"] = JReturns;
    JFunc["indirect_calls"] = JIndirectCalls;
    JFuncs.push_back({F.getName(), JFunc});
  }

  // Print the results
  Json::Value JMod;
  for (const auto &[FuncName, JFunc] : JFuncs) {
    JMod[FuncName.str()] = JFunc;
  }

  const auto ModName = sys::path::filename(M.getName());
  SmallString<32> Filename(OutDir.c_str());
  sys::path::append(Filename, "cfg." + ModName + ".json");
  errs() << "Writing module '" << M.getName() << "' to '" << Filename << "'...";

  std::error_code EC;
  raw_fd_ostream File(Filename, EC, sys::fs::F_Text);

  if (!EC) {
    File << JMod.toStyledString();
  } else {
    errs() << "  error opening file for writing!";
  }
  errs() << "\n";

  return false;
}

static RegisterPass<CFGToJSON> X("cfg-to-json", "Export a CFG to JSON", false,
                                 false);

static void registerCFGToJSON(const PassManagerBuilder &,
                              legacy::PassManagerBase &PM) {
  PM.add(new CFGToJSON());
}

static RegisterStandardPasses
    RegisterCFGToJSON(PassManagerBuilder::EP_OptimizerLast, registerCFGToJSON);

static RegisterStandardPasses
    RegisterCFGToJSON0(PassManagerBuilder::EP_EnabledOnOptLevel0,
                       registerCFGToJSON);
