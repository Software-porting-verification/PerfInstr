//===-- trec_rtl_thread.cpp
//-----------------------------------------------===//
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

#include <assert.h>
#include <errno.h>
#include <sys/fcntl.h>

#include "sanitizer_common/sanitizer_placement_new.h"
#include "trec_platform.h"
#include "trec_rtl.h"

namespace __trec {

TraceWriter::TraceWriter(u16 tid)
    : id(tid),
      trace_buffer(nullptr),
      metadata_buffer(nullptr),
      trace_len(0),
      metadata_len(0),
      is_end(false) {
}

TraceWriter::~TraceWriter() {
  // if (ctx->flags.output_trace)
  //   flush_all();
  // if (trace_buffer)
  //   internal_free(trace_buffer);
  // if (metadata_buffer)
  //   internal_free(metadata_buffer);
}

void TraceWriter::flush_module() {

}

void TraceWriter::flush_all() {
  if (is_end)
    return;
  {
    TrecMutexGuard guard(mtx);
    flush_trace();
    flush_metadata();
    flush_header();
  }
}

void TraceWriter::flush_trace() {
  if (trace_buffer == nullptr || trace_len == 0)
    return;
  char filepath[TREC_DIR_PATH_LEN];

  internal_snprintf(filepath, TREC_DIR_PATH_LEN - 1, "%s/trec_%lu/trace/%d.bin",
                    ctx->trace_dir, internal_getpid(), id);
  // int fd_trace = internal_open(filepath, O_CREAT | O_WRONLY | O_APPEND, 0700);

  // if (UNLIKELY(fd_trace < 0)) {
  //   Report("Failed to open trace file at %s\n", filepath);
  //   Die();
  // }
  // char *buff_pos = (char *)trace_buffer;
  // while (trace_len > 0) {
  //   uptr write_bytes = internal_write(fd_trace, buff_pos, trace_len);
  //   if (write_bytes == (uptr)-1 && errno != EINTR) {
  //     Report("Failed to flush trace info in %s, errno=%u\n", filepath, errno);
  //     Die();
  //   } else {
  //     trace_len -= write_bytes;
  //     buff_pos += write_bytes;
  //   }
  // }

  // internal_close(fd_trace);
}

void TraceWriter::flush_metadata() {
  if (metadata_buffer == nullptr || metadata_len == 0)
    return;
  char filepath[TREC_DIR_PATH_LEN];

  internal_snprintf(filepath, TREC_DIR_PATH_LEN - 1,
                    "%s/trec_%lu/metadata/%d.bin", ctx->trace_dir,
                    internal_getpid(), id);
  int fd_metadata =
      internal_open(filepath, O_CREAT | O_WRONLY | O_APPEND, 0700);

  if (UNLIKELY(fd_metadata < 0)) {
    Report("Failed to open metadata file at %s\n", filepath);
    Die();
  }
  char *buff_pos = (char *)metadata_buffer;
  while (metadata_len > 0) {
    uptr write_bytes = internal_write(fd_metadata, buff_pos, metadata_len);
    if (write_bytes == (uptr)-1 && errno != EINTR) {
      Report("Failed to flush metadata info in %s, errno=%u\n", filepath,
             errno);
      Die();
    } else {
      metadata_len -= write_bytes;
      buff_pos += write_bytes;
    }
  }

  internal_close(fd_metadata);
}

void TraceWriter::flush_header() {
  char filepath[TREC_DIR_PATH_LEN];

  internal_snprintf(filepath, TREC_DIR_PATH_LEN - 1,
                    "%s/trec_%lu/header/%d.bin", ctx->trace_dir,
                    internal_getpid(), id);

  // int fd_header = internal_open(filepath, O_CREAT | O_WRONLY | O_TRUNC, 0700);

  // if (UNLIKELY(fd_header < 0)) {
  //   Report("Failed to open header file\n");
  //   Die();
  // } else {
  //   uptr need_write_bytes = sizeof(header);
  //   char *buff_pos = (char *)&header;
  //   while (need_write_bytes > 0) {
  //     uptr write_bytes = internal_write(fd_header, buff_pos, need_write_bytes);
  //     if (write_bytes == (uptr)-1 && errno != EINTR) {
  //       Report("Failed to flush header in %s, errno=%u\n", filepath, errno);
  //       Die();
  //     } else {
  //       need_write_bytes -= write_bytes;
  //       buff_pos += write_bytes;
  //     }
  //   }
  // }

  // internal_close(fd_header);
}

bool TraceWriter::state_restore() {
  // TrecMutexGuard guard(mtx);
  // struct stat _st = {0};
  // char path[2 * TREC_DIR_PATH_LEN];
  // internal_snprintf(path, 2 * TREC_DIR_PATH_LEN - 1,
  //                   "%s/trec_%lu/header/%u.bin", ctx->trace_dir,
  //                   internal_getpid(), id);
  // uptr IS_EXIST = __sanitizer::internal_stat(path, &_st);
  // if (IS_EXIST == 0 && _st.st_size > 0) {
  //   int header_fd = internal_open(path, O_RDONLY);
  //   if (header_fd < 0) {
  //     Report("Restore header from %s failed\n", path);
  //     return false;
  //   } else {
  //     internal_read(header_fd, &header, sizeof(header));
  //     return true;
  //   }
  // }
  // return false;
}

void TraceWriter::reset() {
  // TrecMutexGuard guard(mtx);
  // if (trace_buffer)
  //   internal_free(trace_buffer);
  // trace_buffer = nullptr;
  // trace_len = 0;
  // if (metadata_buffer)
  //   internal_free(metadata_buffer);
  // metadata_buffer = nullptr;
  // metadata_len = 0;
}

void TraceWriter::init_cmd() {
  TrecMutexGuard guard(mtx);
  char **cmds = GetArgv();
  int cmd_len = 0;
}

void TraceWriter::setEnd() { is_end = true; }

// ThreadContext implementation.

ThreadContext::ThreadContext(int tid)
    : ThreadContextBase(tid), thr(), writer(tid) {}

#if !SANITIZER_GO
ThreadContext::~ThreadContext() {}
#endif

void ThreadContext::OnDead() {}

void ThreadContext::OnJoined(void *arg) {}

struct OnCreatedArgs {
  ThreadState *thr;
  uptr pc;
};

void ThreadContext::OnCreated(void *arg) {}

void ThreadContext::OnReset() {}

void ThreadContext::OnDetached(void *arg) {}

struct OnStartedArgs {
  ThreadState *thr;
};

void ThreadContext::OnStarted(void *arg) {
  OnStartedArgs *args = static_cast<OnStartedArgs *>(arg);
  thr = args->thr;
  new (thr) ThreadState(ctx, tid, unique_id);
  thr->is_inited = true;
  DPrintf("#%d: ThreadStart\n", tid);
}

void ThreadContext::OnFinished() {
#if !SANITIZER_GO
  PlatformCleanUpThreadState(thr);
#endif
  thr->~ThreadState();
  thr = 0;
}

int ThreadCount(ThreadState *thr) {
  // uptr result;
  // ctx->thread_registry->GetNumberOfThreads(0, 0, &result);
  // return (int)result;

  return 0;
}

int ThreadCreate(ThreadState *thr, uptr pc, uptr uid, bool detached) {
  // OnCreatedArgs args = {thr, pc};
  // u32 parent_tid = thr ? thr->tid : kInvalidTid;  // No parent for GCD workers.
  // int tid =
  //     ctx->thread_registry->CreateThread(uid, detached, parent_tid, &args);
  // DPrintf("#%d: ThreadCreate tid=%d uid=%zu\n", parent_tid, tid, uid);

  // // TODO maybe move this to __trec_init()
  // if (tid == 0) {
  //   if (ctx->flags.output_trace) {
  //     const char *trace_dir_env = GetEnv("TREC_TRACE_DIR");
  //     if (trace_dir_env == nullptr) {
  //       Report("TREC_TRACE_DIR has not been set!\n");
  //       Die();
  //     } else
  //       internal_strncpy(ctx->trace_dir, trace_dir_env,
  //                        internal_strlen(trace_dir_env));
  //     ctx->open_directory(ctx->trace_dir);
  //   }
  //   atomic_store(&ctx->global_id, 0, memory_order_relaxed);
  //   atomic_store(&ctx->forked_cnt, 0, memory_order_relaxed);
  // } else if (LIKELY(thr != nullptr && thr->tctx != nullptr) &&
  //            LIKELY(ctx->flags.output_trace)) {

  // }
  // return tid;
}



}  // namespace __trec
