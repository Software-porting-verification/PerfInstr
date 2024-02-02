//===---------------- Perf Runtime (perfRT) -------------------------------===//
//
// Author: Mao Yifu, maoif@ios.ac.cn
//
// Runtime for performance metrics collection.
//
//===----------------------------------------------------------------------===//

#include <filesystem>
#include <iostream>
#include <fstream>
#include <cstdlib>
#include <map>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include <mutex>
#include <atomic>
#include <cerrno>
#include <ctime>
#include <chrono>
#include <algorithm>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>
#include <linux/perf_event.h>    /* Definition of PERF_* constants */
#include <linux/hw_breakpoint.h> /* Definition of HW_* constants */
#include <sys/syscall.h>         /* Definition of SYS_* constants */
#include <sys/types.h>
#include <sys/ioctl.h>

extern "C" {
void __trec_perf_func_enter(long);
void __trec_perf_func_exit(long);
void __trec_init();
}

static long currentTime();
static void flushImpl();
static void flushData();
static void initTimeIntervals();
static int  computeIndexFromDelta(unsigned int);

enum Mode : unsigned char {
  TIME  = 0,
  CYCLE = 1,
  INSN  = 2
};

constexpr char envDataPath[] = "TREC_PERF_DIR";
constexpr char envMode[]     = "TREC_PERF_MODE";
constexpr char envInterval[] = "TREC_PERF_INTERVAL";
constexpr int defaultNumOfBuckets = 1024;
// constexpr int idxInfinity = defaultNumOfBuckets - 1;
// constexpr int lengthOfTimeIntervals = defaultNumOfBuckets - 1;

static Mode mode;
// used to run finalization code upon thread exit
// static pthread_key_t finalizeKey;
// used to check if there's a fork
static pid_t pid;
static unsigned int timeIntervals[defaultNumOfBuckets];
// time interval as per bucket (nanosecond)
static int interval = 5000;

// fid -> buckets
static std::unordered_map<long, std::vector<long>> * funcCallCounter;
static std::mutex  * lock;
static std::thread * flusher;
// tell the flush thread to quit
static std::atomic_bool * shouldQuit;
static std::string * dataPath;

struct perfFD {
  int fd;

  perfFD() {
    int tid = gettid();
    int cpu = -1;
    struct perf_event_attr pe;
    memset(&pe, 0, sizeof(pe));
    pe.size = sizeof(pe);
    pe.disabled = 1;
    // required, otherwise CAP_PERFMON is needed
    pe.exclude_kernel = 1;
    pe.exclude_hv = 1;

    if (mode == TIME) {
      pe.type = PERF_TYPE_SOFTWARE;
      pe.config = PERF_COUNT_SW_CPU_CLOCK;
    } else if (mode == CYCLE) {
      pe.type = PERF_TYPE_HARDWARE;
      pe.config = PERF_COUNT_HW_REF_CPU_CYCLES;
    } else if (mode == INSN) {
      pe.type = PERF_TYPE_HARDWARE;
      pe.config = PERF_COUNT_HW_INSTRUCTIONS;
    }

    // create per-thread perf timer
    fd = syscall(SYS_perf_event_open, &pe, tid, cpu, -1, 0);
    if (fd == -1) {
      fprintf(stderr, "Failed to open perf event: %s\n", strerror(errno));
      abort();
    }

    ioctl(fd, PERF_EVENT_IOC_RESET, 0);
    ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);

    printf("created perf fd %d for tid %d \n", fd, tid);
  }

  ~perfFD() {
    ioctl(fd, PERF_EVENT_IOC_DISABLE, 0);
    close(fd);
    printf("closed perf fd %d\n", fd);
  }
};

// a new perf fd will be created for each thread
static thread_local struct perfFD tl_perffd;
// per thread, fid -> time
static thread_local std::unordered_map<long, long> TL_lastCallTimePerFunc;

//===----------------------------------------------------------------------===//
//
// Interfaces.
//
//===----------------------------------------------------------------------===//

void __trec_perf_func_enter(long fid) {
  printf("enter %ld\n", fid);
  long t = currentTime();
  TL_lastCallTimePerFunc[fid] = t;
}

void __trec_perf_func_exit(long fid) {
  long t   = currentTime();
  long val = TL_lastCallTimePerFunc.at(fid);
  long delta = t - val;
  int i = computeIndexFromDelta((unsigned int) delta);
  
  lock->lock();

  if (funcCallCounter->count(fid) == 0) {
    std::vector<long> newVec(defaultNumOfBuckets, 0);
    funcCallCounter->insert({fid, std::move(newVec)});
  }

  auto & bucket = funcCallCounter->at(fid).at(i);
  bucket++;
  printf("exit %ld delta %ld\n", fid, delta);

  lock->unlock();
}

void __trec_deinit() {
  printf("perfRT deinit\n");

  *shouldQuit = true;
  flusher->join();

  delete funcCallCounter;
  delete lock;
  delete shouldQuit;
  delete flusher;
  delete dataPath;
}

void __trec_init() {
  printf("perfRT init\n");
  
  char * env = getenv(envDataPath);
  if (env == nullptr) {
    fprintf(stderr, "env %s not set!\n", envDataPath);
    abort();
  }
  auto p = std::filesystem::path(env);
  if (std::filesystem::exists(p)) {
    if (!std::filesystem::is_directory(p)) {
      fprintf(stderr, "%s is not a directory!\n", env);
      abort();
    }
  } else {
    std::filesystem::create_directories(p);
  }

  pid = getpid();
  // generate data file name: trec_perf_comm_pid.bin
  std::string comm(program_invocation_short_name);
  std::string pidStr(std::to_string(pid));
  dataPath = new std::string("trec_perf_" + comm + "_" + pidStr + ".bin");
  printf("data file: %s\n", dataPath->c_str());

  env = getenv(envMode);
  if (env == nullptr) {
    fprintf(stderr, "env %s not set!\n", envMode);
    abort();
  }
  if (strcmp(env, "time") == 0) {
    mode = TIME;
  } else if (strcmp(env, "cycle") == 0) {
    mode = CYCLE;
  } else if (strcmp(env, "insn") == 0) {
    mode = INSN;
  } else {
    fprintf(stderr, 
      "Unknown value for env %s: %s, available ones: time, cycle, insn\n", envMode, env);
    abort();
  }

  env = getenv(envInterval);
  if (env != nullptr) {
    int step = atoi(env);
    if (step <= 0) {
      fprintf(stderr, "Invalid interval %s, defaults to %d\n", env, interval);
    } else {
      interval = step;
    }
  }

  initTimeIntervals();
  
  funcCallCounter = new std::unordered_map<long, std::vector<long>>();
  lock = new std::mutex();
  shouldQuit  = new std::atomic_bool(false);
  // spawn a thread for syncing data
  flusher = new std::thread(flushData);

  atexit(__trec_deinit);

  printf("perfRT init done\n");
}

//===----------------------------------------------------------------------===//
//
// Internals.
//
//===----------------------------------------------------------------------===//

inline static long currentTimeClock() {
  struct timespec ts;
  clock_gettime(CLOCK_REALTIME, &ts);

  return ts.tv_sec + ts.tv_nsec;
}

inline static long currentTimePerf() {
  long count;
  read(tl_perffd.fd, &count, sizeof(count));

  return count;
}

inline static long currentTime() {
  return currentTimeClock();
}

static void flushImpl() {
  if (getpid() != pid) {
    // TODO write to a new file
    fprintf(stderr, "Program %s has forked, trec perf data is nor recorded in the child process\n", program_invocation_short_name);
    return;
  }

  lock->lock();

  std::ofstream ofs(dataPath->c_str(), std::ios::out | std::ios::binary | std::ios::trunc);
  // write mode
  ofs.write((const char *)&mode, sizeof(mode));
  // write vector length
  ofs.write((const char *)&defaultNumOfBuckets, sizeof(defaultNumOfBuckets));
  // write data
  for (auto & kv : *funcCallCounter) {
    // fid
    ofs.write((const char *)&kv.first, sizeof(kv.first));
    for (auto & c : kv.second) {
      // buckets
      ofs.write((const char *)&c, sizeof(c));
    }
  }

  if (!ofs.good()) {
    fprintf(stderr, "Error flushing data to %s\n", dataPath->c_str());
    abort();
  }
  ofs.close();

  lock->unlock();
}

static void flushData() {
  printf("flusher started\n");
  while (true) {
    // Sleep for 1s, but check for quit signal frequently.
    for (int i = 0; i < 20; i++) {
      if (*shouldQuit) {
        flushImpl();
        printf("flusher quit\n");
        return;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }

    flushImpl();   
  }
}

static void initTimeIntervals() {
  int start = 0;
  for (int i = 0; i < defaultNumOfBuckets; i++) {
    timeIntervals[i] = start;
    start += interval;
  }
}

inline static int computeIndexFromDelta(unsigned int delta) {
  int m;
  int left = 0;
  int right = defaultNumOfBuckets - 1;

  // binary search
  while (left <= right) {
    if (left == right) {
      // == 0 or size - 1
      return left;
    }

    m = (left + right) / 2;
    if (delta < timeIntervals[m - 1]) {
      // move left
      right = m - 1;
    } else if (timeIntervals[m + 1] <= delta) {
      // move right
      left = m + 1;
    } else {
      // v[m - 1] <= delta <= v[m + 1]
      if (delta >= timeIntervals[m]) {
        return m;
      } else {
        return m - 1;
      }
    }
  }

  // unreachable
  return -1;
}
