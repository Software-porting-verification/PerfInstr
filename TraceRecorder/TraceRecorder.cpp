//===-- TraceRecorder.cpp - race detector -------------------------------===//
//
// Author: Mao Yifu
//
// Performance analysis based on perf_event_open().
//
//===----------------------------------------------------------------------===//

#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/SmallString.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/ADT/Statistic.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Analysis/CaptureTracking.h"
#include "llvm/Analysis/TargetLibraryInfo.h"
#include "llvm/Analysis/ValueTracking.h"
#include "llvm/IR/DataLayout.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/Intrinsics.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/Metadata.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Type.h"
#include "llvm/InitializePasses.h"
#include "llvm/Pass.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/ProfileData/InstrProf.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/Debug.h"
#include "llvm/Support/MathExtras.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Transforms/Instrumentation.h"
#include "llvm/Transforms/Utils/BasicBlockUtils.h"
#include "llvm/Transforms/Utils/EscapeEnumerator.h"
#include "llvm/Transforms/Utils/Local.h"
#include "llvm/Transforms/Utils/ModuleUtils.h"

#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>

#include <bit>
#include <filesystem>
#include <map>
#include <string>

#include "SqliteDebugWriter.h"
#include "TraceRecorder.h"

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
struct TraceRecorder {
  TraceRecorder() {
    // Sanity check options and warn user.
  }

  ~TraceRecorder() {}
  bool instrmentFunction(Function& F);

 private:
  SqliteDebugWriter debugger;
  Type* IntptrTy;
  FunctionCallee TrecFuncEntry;
  FunctionCallee TrecFuncExit;

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

PreservedAnalyses TraceRecorderPass::run(Function& F,
                                         FunctionAnalysisManager& FAM) {
  TraceRecorder TRec;
  TRec.instrmentFunction(F);
  return PreservedAnalyses::none();
}

PreservedAnalyses ModuleTraceRecorderPass::run(Module& M,
                                               ModuleAnalysisManager& MAM) {
  insertModuleCtor(M);
  TraceRecorder Trec;
  for (auto& F : M) {
    Trec.instrmentFunction(F);
  }
  return PreservedAnalyses::none();
}

void TraceRecorder::initialize(Module& M) {
  const DataLayout& DL = M.getDataLayout();
  IntptrTy = DL.getIntPtrType(M.getContext());
  IRBuilder<> IRB(M.getContext());
  AttributeList Attr;
  // why?
  Attr = Attr.addFnAttribute(M.getContext(), Attribute::NoUnwind);
  // Initialize the callbacks.
  TrecFuncEntry = M.getOrInsertFunction("__trec_perf_func_enter", Attr,
                                        IRB.getVoidTy(), IRB.getInt64Ty());
  TrecFuncExit = M.getOrInsertFunction("__trec_perf_func_exit", Attr,
                                       IRB.getVoidTy(), IRB.getInt64Ty());
}

bool TraceRecorder::instrmentFunction(Function& F) {
  // This is required to prevent instrumenting call to __trec_init from
  // within the module constructor.
  StringRef funcName = F.getName();
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

  IRBuilder<> IRB(&*F.getEntryBlock().getFirstInsertionPt());
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

  llvm::dbgs() << "instr " << funcName << " line " << line << " fid " << fid << "\n";
  llvm::dbgs() << "\t filename: " << F.getSubprogram()->getFilename() << "\n";

  IRB.CreateCall(TrecFuncEntry, {IRB.getInt64(fid)});

  EscapeEnumerator EE(F);
  while (IRBuilder<>* AtExit = EE.Next()) {
    AtExit->CreateCall(TrecFuncExit, {AtExit->getInt64(fid)});
  }

  debugger.commitSQL();

  return false;
}

// register LLVM Pass
extern "C" LLVM_ATTRIBUTE_WEAK ::llvm::PassPluginLibraryInfo
llvmGetPassPluginInfo() {
  return {.APIVersion = LLVM_PLUGIN_API_VERSION,
          .PluginName = "TraceRecorder (perf) pass",
          .PluginVersion = "v3.0",
          .RegisterPassBuilderCallbacks = [](PassBuilder& PB) {
            PB.registerPipelineStartEPCallback(
                [](ModulePassManager& MPM, OptimizationLevel Level) {
                  MPM.addPass(ModuleTraceRecorderPass());
                });
          }};
}
