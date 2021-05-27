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

cl::opt<std::string> OutDir("cfg-outdir", cl::desc("Output directory"),
                            cl::value_desc("directory"), cl::init("."));

class CFGToJSON : public FunctionPass {
public:
  static char ID;
  CFGToJSON() : FunctionPass(ID) {}

  void getAnalysisUsage(AnalysisUsage &) const override;
  bool runOnFunction(Function &) override;
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

static std::pair<DebugLoc, DebugLoc> getSourceRange(const BasicBlock *BB) {
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

bool CFGToJSON::runOnFunction(Function &F) {
  const Module *M = F.getParent();

  SmallPtrSet<BasicBlock *, 32> SeenBBs;
  SmallVector<BasicBlock *, 32> Worklist = {&F.getEntryBlock()};

  Json::Value JNodes;
  Json::Value JEdges;
  Json::Value JCalls;
  Json::Value JIndirectCalls;
  Json::Value JReturns;

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

    Json::Value BBNode;
    BBNode["start_line"] = SrcStart ? SrcStart.getLine() : Json::Value();
    BBNode["end_line"] = SrcEnd ? SrcEnd.getLine() : Json::Value();
    BBNode["size"] = sizeWithoutDebug(BB);
    JNodes[BBLabel] = BBNode;

    // Save the edges
    for (auto SI = succ_begin(BB), SE = succ_end(BB); SI != SE; ++SI) {
      Json::Value JEdge;
      JEdge["src"] = BBLabel;
      JEdge["dst"] = getBBLabel(*SI);
      JEdges.append(JEdge);

      Worklist.push_back(*SI);
    }

    // Save the calls
    for (auto &I : *BB) {
      if (const auto *CB = dyn_cast<CallBase>(&I)) {
        auto *CalledF = dyn_cast_or_null<Function>(
            CB->getCalledOperand()->stripPointerCasts());
        if (CalledF) {
          Json::Value JCall;
          JCall["src"] = BBLabel;
          JCall["dst"] = CalledF->getName().str();
          JCalls.append(JCall);
        } else {
          JIndirectCalls.append(BBLabel);
        }
      }
    }

    // Save the return
    if (isa<ReturnInst>(BB->getTerminator())) {
      JReturns.append(BBLabel);
    }
  }

  // Print the results

  Json::Value JObj;
  JObj["module"] = M->getName().str();
  JObj["function"] = F.getName().str();
  JObj["entry"] = getBBLabel(&F.getEntryBlock());
  JObj["nodes"] = JNodes;
  JObj["edges"] = JEdges;
  JObj["calls"] = JCalls;
  JObj["returns"] = JReturns;
  JObj["indirect_calls"] = JIndirectCalls;

  StringRef ModName = sys::path::filename(M->getName());
  SmallString<32> Filename(OutDir.c_str());
  sys::path::append(Filename, "cfg." + ModName + "." + F.getName() + ".json");
  errs() << "Writing function '" << F.getName() << "' (module '" << M->getName()
         << "') to '" << Filename << "'...";

  std::error_code EC;
  raw_fd_ostream File(Filename, EC, sys::fs::F_Text);

  if (!EC) {
    File << JObj.toStyledString();
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
