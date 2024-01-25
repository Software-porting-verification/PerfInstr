//===-- trec_interface.h ----------------------------------------*- C++
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
// The functions declared in this header will be inserted by the instrumentation
// module.
// This header can be included by the instrumented program or by TRec
// tests.
//===----------------------------------------------------------------------===//
#ifndef TREC_INTERFACE_H
#define TREC_INTERFACE_H

#include <sanitizer_common/sanitizer_internal_defs.h>
using __sanitizer::tid_t;
using __sanitizer::u32;
using __sanitizer::uptr;

// This header should NOT include any other headers.
// All functions in this header are extern "C" and start with __trec_.

#ifdef __cplusplus
extern "C" {
#endif

#if !SANITIZER_GO

// This function should be called at the very beginning of the process,
// before any instrumented code is executed and before any call to malloc.
SANITIZER_INTERFACE_ATTRIBUTE void __trec_init();

SANITIZER_INTERFACE_ATTRIBUTE void __trec_func_entry(__sanitizer::u16 order,
                                                     __sanitizer::u16 arg_cnt,
                                                     __sanitizer::u64 debugID);
SANITIZER_INTERFACE_ATTRIBUTE void __trec_func_exit(__sanitizer::u64 debugID);

#endif  // SANITIZER_GO

#ifdef __cplusplus
}  // extern "C"
#endif

namespace __trec {

// disable 128-bit
#define __TREC_HAS_INT128 0

// Part of ABI, do not change.
// https://github.com/llvm/llvm-project/blob/master/libcxx/include/atomic
typedef enum {
  mo_relaxed,
  mo_consume,
  mo_acquire,
  mo_release,
  mo_acq_rel,
  mo_seq_cst
} morder;

struct ThreadState;
}  // namespace __trec

#endif  // TREC_INTERFACE_H
