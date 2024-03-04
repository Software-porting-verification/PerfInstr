//===-- trec_rtl.cpp
//------------------------------------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// This file is a part of TraceRecorder (TRec), a race detector.
//
// Main file (entry points) for the TRec run-time.
//===----------------------------------------------------------------------===//

#include "trec_rtl.h"

#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/fcntl.h>
#include <sys/stat.h>
#include <time.h>

#include "sanitizer_common/sanitizer_atomic.h"
#include "sanitizer_common/sanitizer_common.h"
#include "sanitizer_common/sanitizer_file.h"
#include "sanitizer_common/sanitizer_libc.h"
#include "sanitizer_common/sanitizer_placement_new.h"
#include "sanitizer_common/sanitizer_stackdepot.h"
#include "sanitizer_common/sanitizer_symbolizer.h"
#include "trec_defs.h"
#include "trec_platform.h"
#include "ubsan/ubsan_init.h"

namespace __trec {

// #if !SANITIZER_GO && !SANITIZER_APPLE
// __attribute__((tls_model("initial-exec")))
// THREADLOCAL char cur_thread_placeholder[sizeof(ThreadState)] ALIGNED(64);
// #endif
static char ctx_placeholder[sizeof(Context)] ALIGNED(64);
Context *ctx;

// static char thread_registry_placeholder[sizeof(ThreadRegistry)];

// static ThreadContextBase *CreateThreadContext(u32 tid) {
//   void *mem = internal_alloc(MBlockThreadContex, sizeof(ThreadContext));
//   return new (mem) ThreadContext(tid);
// }

#if !SANITIZER_GO
static const u32 kThreadQuarantineSize = 16;
#else
static const u32 kThreadQuarantineSize = 64;
#endif

Context::Context()
    : initialized(),
      pid(internal_getpid()),
      // thread_registry(new(thread_registry_placeholder) ThreadRegistry(
      //     CreateThreadContext, kMaxTid, kThreadQuarantineSize, kMaxTidReuse)),
      temp_dir_path(nullptr) {}

// The objects are allocated in TLS, so one may rely on zero-initialization.
ThreadState::ThreadState(Context *ctx, int tid, int unique_id)
    : tid(tid), unique_id(unique_id) {}

#if !SANITIZER_GO

static void OnStackUnwind(const SignalContext &sig, const void *,
                          BufferedStackTrace *stack) {
  stack->Unwind(StackTrace::GetNextInstructionPc(sig.pc), sig.bp, sig.context,
                common_flags()->fast_unwind_on_fatal);
}

void TrecFlushTraceOnDead() {
  uptr num_threads = 0;

}

static void TrecOnDeadlySignal(int signo, void *siginfo, void *context) {
  TrecFlushTraceOnDead();
  if (ctx->flags.print_debug_on_dead)
    HandleDeadlySignal(siginfo, context, GetTid(), &OnStackUnwind, nullptr);
  Die();
}
#endif

void TrecCheckFailed(const char *file, int line, const char *cond, u64 v1,
                     u64 v2) {
  // There is high probability that interceptors will check-fail as well,
  // on the other hand there is no sense in processing interceptors
  // since we are going to die soon.
  ScopedIgnoreInterceptors ignore;
#if !SANITIZER_GO
  cur_thread()->ignore_sync++;
  cur_thread()->ignore_reads_and_writes++;
#endif
  Printf(
      "FATAL: TraceRecorder CHECK failed: "
      "%s:%d \"%s\" (0x%zx, 0x%zx)\n",
      file, line, cond, (uptr)v1, (uptr)v2);
  Die();
}

void Initialize() {
  // Thread safe because done before all threads exist.
  static bool is_initialized = false;
  if (is_initialized)
    return;
  is_initialized = true;
  // We are not ready to handle interceptors yet.
  ScopedIgnoreInterceptors ignore;
  SanitizerToolName = "TraceRecorder";

  ctx = new (ctx_placeholder) Context;
  const char *env_name = SANITIZER_GO ? "GORACE" : "TREC_OPTIONS";
  const char *options = GetEnv(env_name);
  CacheBinaryName();
  CheckASLR();
  InitializeFlags(&ctx->flags, options, env_name);
  AvoidCVE_2016_2143();
  __sanitizer::InitializePlatformEarly();
  __trec::InitializePlatformEarly();

#if !SANITIZER_GO

  // InitializeAllocator();
  // ReplaceSystemMalloc();
#endif
  // Processor *proc = ProcCreate();
  // ProcWire(proc, thr);
  // InitializeInterceptors();
  InitializePlatform();
#if !SANITIZER_GO
  // InitializeAllocatorLate();

  // Do not install SEGV handler
  InstallDeadlySignalHandlers(TrecOnDeadlySignal);
  if (common_flags()->use_sigaltstack)
    SetAlternateSignalStack();
#endif
  // Setup correct file descriptor for error reports.
  // __sanitizer_set_report_path(common_flags()->log_path);

  VPrintf(1, "***** Perf-based Performance Analyzer (pid %d) *****\n",
          (int)internal_getpid());

  // Initialize thread 0.
  // int tid = ThreadCreate(thr, 0, 0, true);
  // CHECK_EQ(tid, 0);
  // ThreadStart(thr, tid, GetTid(), ThreadType::Regular);
  ctx->initialized = true;

#if !SANITIZER_GO
  {
    // symbolizer calls interceptors, ignore them
    ScopedIgnoreInterceptors ignore;
    Symbolizer::LateInitialize();
  }
#endif
}

ALWAYS_INLINE USED void RecordFuncEntry(__sanitizer::u64 fid) {
  // TODO
  Report("Enter %d\n", fid);
}

ALWAYS_INLINE USED void RecordFuncExit(__sanitizer::u64 fid) {
  // TODO
  Report("Exit %d\n", fid);
}

}  // namespace __trec

#if !SANITIZER_GO
// Must be included in this file to make sure everything is inlined.
#include "trec_interface_inl.h"
#endif

#if !SANITIZER_GO
void __sanitizer::BufferedStackTrace::UnwindImpl(uptr pc, uptr bp,
                                                 void *context,
                                                 bool request_fast,
                                                 u32 max_depth) {
  uptr top = 0;
  uptr bottom = 0;
  if (StackTrace::WillUseFastUnwind(request_fast)) {
    GetThreadStackTopAndBottom(false, &top, &bottom);
    Unwind(max_depth, pc, bp, nullptr, top, bottom, true);
  } else
    Unwind(max_depth, pc, 0, context, 0, 0, false);
}
#endif  // SANITIZER_GO
