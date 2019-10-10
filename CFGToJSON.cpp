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
#include "llvm/IR/CallSite.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/LegacyPassManager.h"
#include "llvm/Pass.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Transforms/IPO/PassManagerBuilder.h"

#include "json/json.h"

using namespace llvm;

#define DEBUG_TYPE "cfg-to-json"

namespace {

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

void CFGToJSON::getAnalysisUsage(AnalysisUsage &AU) const {
  AU.setPreservesAll();
}

bool CFGToJSON::runOnFunction(Function &F) {
  SmallPtrSet<BasicBlock *, 32> SeenBBs;
  SmallVector<BasicBlock *, 32> Worklist = {&F.getEntryBlock()};

  Json::Value JNodes;
  Json::Value JEdges;
  Json::Value JCalls;

  while (!Worklist.empty()) {
    auto *BB = Worklist.pop_back_val();

    // Prevent loops
    auto Res = SeenBBs.insert(BB);
    if (!Res.second) {
      continue;
    }

    // Save the node
    auto BBLabel = getBBLabel(BB);
    JNodes.append(BBLabel);

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
      if (isa<CallInst>(I) || isa<InvokeInst>(I)) {
        CallSite CS(&I);
        auto *CalledF = CS.getCalledFunction();
        if (CalledF) {
          Json::Value JCall;
          JCall["src"] = BBLabel;
          JCall["dst"] = CalledF->getName().str();
          JCalls.append(JCall);
        }
      }
    }
  }

  // Print the results

  Json::Value JObj;
  JObj["function"] = F.getName().str();
  JObj["entry"] = getBBLabel(&F.getEntryBlock());
  JObj["nodes"] = JNodes;
  JObj["edges"] = JEdges;
  JObj["calls"] = JCalls;

  std::string Filename = ("cfg." + F.getName() + ".json").str();
  errs() << "Writing '" << Filename << "'...";

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
