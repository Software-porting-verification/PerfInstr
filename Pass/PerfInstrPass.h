#ifndef LLVM_TRANSFORMS_INSTRUMENTATION_PERFINSTR_H
#define LLVM_TRANSFORMS_INSTRUMENTATION_PERFINSTR_H

#include "llvm/IR/PassManager.h"
#include "llvm/Pass.h"
#include <map>

namespace llvm {
// Insert performance instrumentation


struct PerfInstrPass : public PassInfoMixin<PerfInstrPass> {
  PreservedAnalyses run(Function &F, FunctionAnalysisManager &FAM);
  static bool isRequired() { return true; }
};

struct ModulePerfInstrPass
  : public PassInfoMixin<ModulePerfInstrPass> {
  PreservedAnalyses run(Module &M, ModuleAnalysisManager &AM);
  static bool isRequired() { return true; }
};

} // namespace llvm
#endif /* LLVM_TRANSFORMS_INSTRUMENTATION_PERFINSTR_H */
