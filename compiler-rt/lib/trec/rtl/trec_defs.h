//===-- trec_defs.h ---------------------------------------------*- C++ -*-===//
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

#ifndef TREC_DEFS_H
#define TREC_DEFS_H

#include "sanitizer_common/sanitizer_internal_defs.h"
#include "sanitizer_common/sanitizer_libc.h"
#include "sanitizer_common/sanitizer_mutex.h"
#ifndef TREC_BUFFER_SIZE
#define TREC_BUFFER_SIZE (1 << 28) // default buffer size: 256MB
#endif

#ifndef TREC_DIR_PATH_LEN
#define TREC_DIR_PATH_LEN 256
#endif

#ifndef TREC_HAS_128_BIT
#define TREC_HAS_128_BIT 0
#endif

namespace __trec
{

  const unsigned kMaxTidReuse = (1 << 22) - 1;
  const unsigned kMaxTid = (1 << 13) - 1;
  const __sanitizer::u16 kInvalidTid = kMaxTid + 1;

  template <typename T>
  T min(T a, T b)
  {
    return a < b ? a : b;
  }

  template <typename T>
  T max(T a, T b)
  {
    return a > b ? a : b;
  }

  struct Processor;
  struct ThreadState;
  class ThreadContext;
  class Context;

} // namespace __trec

namespace __trec_perf
{
  const char TREC_PERF_VER[] = "20240124";
  
} // namespace __trec_perf
#endif // TREC_DEFS_H
