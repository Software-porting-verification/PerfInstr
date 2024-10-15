//===-- TraceRecorder.cpp - race detector -------------------------------===//
//
// Author: Mao Yifu
//
// Performance analysis based on perf_event_open().
//
//===----------------------------------------------------------------------===//

#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/ADT/Statistic.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Analysis/CaptureTracking.h"
#include "llvm/Analysis/TargetLibraryInfo.h"
#include "llvm/Analysis/ValueTracking.h"
#include "llvm/IR/DataLayout.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/IRBuilder.h"
#include <llvm/IR/BasicBlock.h>
#include "llvm/IR/Intrinsics.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/Metadata.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Type.h"
#include "llvm/Pass.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/ProfileData/InstrProf.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Transforms/Instrumentation.h"
#include "llvm/Transforms/Utils/BasicBlockUtils.h"
#include "llvm/Transforms/Utils/EscapeEnumerator.h"
#include "llvm/Transforms/Utils/Local.h"
#include "llvm/Transforms/Utils/Cloning.h"
#include "llvm/Transforms/Utils/ModuleUtils.h"

#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>

#include <filesystem>
#include <map>
#include <string>
#include <vector>

#include "SqliteDebugWriter.h"
#include "PerfInstrPass.h"

using namespace llvm;

#define DEBUG_TYPE "trec"

const char kTrecModuleCtorName[] = "trec.module_ctor";
const char kTrecInitName[] = "__trec_init";

namespace {
/// TraceRecorder: instrument the code in module to record traces.
///
/// Instantiating TraceRecorder inserts the trec runtime library API
/// function declarations into the module if they don't exist already.
/// Instantiating ensures the __trec_init function is in the list of global
/// constructors for the module.
struct PerfInstr {
  PerfInstr() {
    // Sanity check options and warn user.
  }

  ~PerfInstr() {}
  bool instrmentFunction(Function& F);
  std::vector<BasicBlock *> copyBasicBlocks(Function &F);
  void instrumentBasicBlocks(std::vector<BasicBlock *> blocks, uint64_t fid);

 private:
  SqliteDebugWriter debugger;
  Type* IntptrTy;
  FunctionCallee TrecEnter;
  FunctionCallee TrecExit;
  FunctionCallee TrecRecordBBL;

  void initialize(Module& M);

  inline std::string concatFileName(std::filesystem::path dir,
                                    std::filesystem::path file) {
    return (dir / file).string();
  }
};

void insertModuleCtor(Module& M) {
  getOrCreateSanitizerCtorAndInitFunctions(
      M, kTrecModuleCtorName, kTrecInitName, /*InitArgTypes=*/{},
      /*InitArgs=*/{},
      // This callback is invoked when the functions are created the first
      // time. Hook them into the global ctors list in that case:
      [&](Function* Ctor, FunctionCallee) { appendToGlobalCtors(M, Ctor, 0); });
}

}  // anonymous namespace


PreservedAnalyses PerfInstrPass::run(Function& F,
                                     FunctionAnalysisManager& FAM) {
  PerfInstr pi;
  pi.instrmentFunction(F);
  return PreservedAnalyses::none();
}

PreservedAnalyses ModulePerfInstrPass::run(Module& M,
                                           ModuleAnalysisManager& MAM) {
  insertModuleCtor(M);
  PerfInstr pi;
  for (auto& F : M) {
    pi.instrmentFunction(F);
  }
  return PreservedAnalyses::none();
}

void PerfInstr::initialize(Module& M) {
  const DataLayout& DL = M.getDataLayout();
  IntptrTy = DL.getIntPtrType(M.getContext());
  IRBuilder<> IRB(M.getContext());
  AttributeList Attr;
  // why?
  Attr = Attr.addFnAttribute(M.getContext(), Attribute::NoUnwind);
  // Initialize the callbacks.
  TrecEnter = M.getOrInsertFunction("__trec_perf_enter", Attr,
                                        IRB.getVoidTy(), IRB.getInt64Ty());
  TrecExit = M.getOrInsertFunction("__trec_perf_exit", Attr,
                                       IRB.getVoidTy(), IRB.getInt64Ty());
  TrecRecordBBL = M.getOrInsertFunction("__trec_perf_record_bbl", Attr,
                                       IRB.getInt64Ty());
}

bool PerfInstr::instrmentFunction(Function& F) {
  StringRef funcName = F.getName();

  // Builtins, llvm intrinsics, lib functions are all empty.
  // Skip them so getFirstInsertionPt() below won't segfault.
  if (F.empty()) {
    // llvm::dbgs() << F.getName() << " is empty\n";
    return false;
  }

  // This is required to prevent instrumenting call to __trec_init from
  // within the module constructor.
  if (funcName == kTrecModuleCtorName || funcName.starts_with("__cxx"))
    return false;
  // If we cannot find the source file, then this function may not be written by
  // user.
  // Do not instrument it.
  if (F.getSubprogram() == nullptr || F.getSubprogram()->getFile() == nullptr)
    return false;
  // skip C++ standard library
  if (F.getSubprogram()->getFilename().contains("include/c++"))
    return false;

  debugger.beginSQL();
  initialize(*F.getParent());

  // deal with cpp name mangling
  // getName() may return the name after mangling.
  // use getSubprogram()->getName() if possible
  if (F.getSubprogram()) {
    funcName = F.getSubprogram()->getName();
  }

  std::string fileName = "";
  if (F.getSubprogram()->getFile()) {
    fileName =
        concatFileName(F.getSubprogram()->getFile()->getDirectory().str(),
                       F.getSubprogram()->getFile()->getFilename().str());
  }

  int line = F.getSubprogram()->getLine();
  int fileID = debugger.getFileID(fileName.c_str());
  int funcID = debugger.getFuncID(funcName.str()
    .append(": ").append(std::to_string(line)).c_str());
  uint64_t fid = debugger.craftFID(fileID, funcID);

  llvm::dbgs() << "instr " << funcName << "() line " << line << " fid " << fid << "\n";
  llvm::dbgs() << "\t filename: " << F.getSubprogram()->getFilename() << "\n";

  BasicBlock *entry = &F.getEntryBlock();
  IRBuilder<> irbEntry(&*entry->getFirstInsertionPt());

  EscapeEnumerator EE(F);
  std::vector<IRBuilder<> *> escapes;
  while (IRBuilder<>* AtExit = EE.Next()) {
    escapes.push_back(AtExit);
  }

  debugger.commitSQL();

  auto newBlocks = copyBasicBlocks(F);

  // insert the dispatcher conditional block
  BasicBlock *newEntry = BasicBlock::Create((F.getParent()->getContext()), "newEntry", &F, entry);
  IRBuilder<> BuildIR(F.getContext());
  BuildIR.SetInsertPoint(newEntry, newEntry->getFirstInsertionPt());
  auto *cond = BuildIR.CreateCall(TrecRecordBBL, {BuildIR.getInt64(fid)});
  BuildIR.CreateCondBr(cond, newBlocks.front(), entry);

  instrumentBasicBlocks(newBlocks, fid);

  // instrument function recording last
  irbEntry.CreateCall(TrecEnter, {irbEntry.getInt64(fid)});
  for (auto irbExit : escapes) {
    irbExit->CreateCall(TrecExit, {irbExit->getInt64(fid)});
  }

  return false;
}

void PerfInstr::instrumentBasicBlocks(std::vector<BasicBlock *> blocks, uint64_t fid) {
  llvm::dbgs() << "instr BBs\n";
  for (auto bb : blocks) {
    int enter_line = 0, enter_col = 0, exit_line = 0, exit_col = 0;
    auto FirstI = &*(bb->getFirstInsertionPt());
    auto TermI = bb->getTerminator();

    if (FirstI->getDebugLoc()) {
      enter_line = FirstI->getDebugLoc().getLine();
      enter_col = FirstI->getDebugLoc().getCol();
    }

    if (TermI->getDebugLoc()) {
      exit_line = TermI->getDebugLoc().getLine();
      exit_col = TermI->getDebugLoc().getCol();
    }

    IRBuilder<> EnterIRB(FirstI);

    // look for the debug info
    while (FirstI != TermI && (enter_line == 0)) {
      llvm::dbgs() << "instr BBs enter_line: " << enter_line << "\n";
      FirstI = FirstI->getNextNode();
      if (FirstI->getDebugLoc()) {
        enter_line = FirstI->getDebugLoc().getLine();
        enter_col = FirstI->getDebugLoc().getCol();
        break;
      }
    }

    IRBuilder<> ExitIRB(TermI);
    while (TermI != FirstI && (exit_line == 0)) {
      llvm::dbgs() << "instr BBs exit_line: " << exit_line << "\n";
      TermI = TermI->getPrevNode();
      if (TermI->getDebugLoc()) {
        exit_line = TermI->getDebugLoc().getLine();
        exit_col = TermI->getDebugLoc().getCol();
        break;
      }
    }

    if (FirstI == TermI || enter_line == 0 || exit_line == 0) {
      continue;
    }

    int bbid = debugger.getBBLID(fid, enter_line, exit_line);

    EnterIRB.CreateCall(TrecEnter, {EnterIRB.getInt64(bbid)});
    ExitIRB.CreateCall(TrecExit, {ExitIRB.getInt64(bbid)});
  }

  llvm::dbgs() << "instr BBs done\n";
}

std::vector<BasicBlock *> PerfInstr::copyBasicBlocks(Function &F) {
  llvm::dbgs() << "copying BBs\n";

  std::vector<BasicBlock *> oldBlocks;
  std::vector<BasicBlock *> newBlocks;
  ValueToValueMapTy vvmap;
  std::map<BasicBlock *, BasicBlock *> blockMap;

  // Why need this extra container?
  for (auto &BB : F) {
    oldBlocks.push_back(&BB);
  }

  for (auto &BB : oldBlocks) {
    llvm::dbgs() << "copying BBs 0.1\n";
    BasicBlock *b = CloneBasicBlock(BB, vvmap, "", &F);
    llvm::dbgs() << "copying BBs 0.2\n";
    newBlocks.push_back(b);
    llvm::dbgs() << "copying BBs 0.3\n";
    blockMap[BB] = b;
  }

  llvm::dbgs() << "copying BBs 1\n";
  
  for (auto &BB : oldBlocks) {
    for (auto &inst : *BB) {
      auto *newInst = cast<Instruction>(vvmap.lookup(&inst));
      // update operand addresses in the instruction
      for (unsigned i = 0; i < inst.getNumOperands(); ++i) {
        Value *OldOperand = inst.getOperand(i);
        if (vvmap.count(OldOperand)) {
          newInst->setOperand(i, vvmap.lookup(OldOperand));
        } else if (isa<BasicBlock>(OldOperand) &&
                   blockMap.count(dyn_cast<BasicBlock>(OldOperand))) {
          newInst->setOperand(i, blockMap.at(dyn_cast<BasicBlock>(OldOperand)));
        }
      }
      if (isa<CallInst>(newInst) &&
          dyn_cast<CallInst>(newInst)->getCalledFunction() &&
          dyn_cast<CallInst>(newInst)
              ->getCalledFunction()
              ->getName()
              .starts_with("llvm.dbg.value") &&
          isa<MetadataAsValue>(inst.getOperand(0)) &&
          isa<ValueAsMetadata>(
              dyn_cast<MetadataAsValue>(inst.getOperand(0))->getMetadata())) {
        Value *origValue =
            dyn_cast<ValueAsMetadata>(
                dyn_cast<MetadataAsValue>(inst.getOperand(0))->getMetadata())
                ->getValue();
        if (vvmap.count(origValue)) {
          Value *NewOperand = llvm::MetadataAsValue::get(
              F.getContext(),
              llvm::ValueAsMetadata::get(vvmap.lookup(origValue)));
          vvmap[inst.getOperand(0)] = NewOperand;
          newInst->setOperand(0, NewOperand);
        }
      }
    }
  }

  llvm::dbgs() << "copying BBs 2\n";

  // Fix the phi instructions.
  for (auto &newBlock : newBlocks) {
    for (auto &inst : *newBlock) {
      if (auto *phiInst = dyn_cast<PHINode>(&inst)) {
        for (unsigned i = 0; i < phiInst->getNumIncomingValues(); i++) {
          BasicBlock *InBB = phiInst->getIncomingBlock(i);
          if (blockMap.count(InBB)) {
            BasicBlock *TargetBB = blockMap.at(InBB);
            phiInst->setIncomingBlock(i, TargetBB);
          }
          Value *InValue = phiInst->getIncomingValue(i);
          if (vvmap.count(InValue)) {
            phiInst->setIncomingValue(i, vvmap.lookup(InValue));
          }
        }
      }
    }
  }

  llvm::dbgs() << "copying BBs done\n";

  return newBlocks;
}

// register LLVM Pass
extern "C" LLVM_ATTRIBUTE_WEAK ::llvm::PassPluginLibraryInfo
llvmGetPassPluginInfo() {
  return {.APIVersion = LLVM_PLUGIN_API_VERSION,
          .PluginName = "performance instrumentation pass",
          .PluginVersion = "v3.0",
          .RegisterPassBuilderCallbacks = [](PassBuilder& PB) {
            PB.registerOptimizerLastEPCallback(
                [](ModulePassManager& MPM, OptimizationLevel Level) {
                  MPM.addPass(ModulePerfInstrPass());
                });
          }};
}