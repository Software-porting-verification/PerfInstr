//===-- trec_interface_inl.h ------------------------------------*- C++
//-*-===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// This file is a part of TraceRecorder (TRec), a race detector.
//
//===----------------------------------------------------------------------===//

#include "sanitizer_common/sanitizer_ptrauth.h"
#include "sanitizer_common/sanitizer_stacktrace.h"
#include "trec_interface.h"
#include "trec_rtl.h"

#define CALLERPC ((uptr)__builtin_return_address(0))
#define PREVCALLERPC \
  (StackTrace::GetPreviousInstructionPc((uptr)__builtin_return_address(0)))
using namespace __trec;

void __trec_perf_func_enter(__sanitizer::u64 fid) { RecordFuncEntry(fid); }

void __trec_perf_func_exit(__sanitizer::u64 fid) { RecordFuncExit(fid); }
