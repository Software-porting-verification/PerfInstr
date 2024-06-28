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
#include <sstream>
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
#include <signal.h>
#include <linux/perf_event.h>    /* Definition of PERF_* constants */
#include <linux/hw_breakpoint.h> /* Definition of HW_* constants */
#include <sys/syscall.h>         /* Definition of SYS_* constants */
#include <sys/types.h>
#include <sys/ioctl.h>

constexpr bool debug = false;
#define DEBUG(body) if (debug) { do { body } while (0); }


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
std::unordered_map<long, long> * getLastCallTimeMap();

enum Mode : unsigned char {
  TIME  = 0,
  CYCLE = 1,
  INSN  = 2,
  NONE
};

constexpr char g_envDataPath[] = "TREC_PERF_DIR";
constexpr char g_envMode[]     = "TREC_PERF_MODE";
constexpr char g_envInterval[] = "TREC_PERF_INTERVAL";
constexpr int  g_defaultNumOfBuckets = 1024;
// constexpr int idxInfinity = defaultNumOfBuckets - 1;
// constexpr int lengthOfTimeIntervals = defaultNumOfBuckets - 1;

// TODO why __trec_init() is called in every thread?
static std::atomic_bool g_inited(false);
static Mode g_mode;
// used to run finalization code upon thread exit
// static pthread_key_t finalizeKey;
// used to check if there's a fork
static pid_t g_pid;
static unsigned int g_timeIntervals[g_defaultNumOfBuckets];
// time interval as per bucket (nanosecond)
static int g_interval = 5000;

// fid -> buckets
static std::unordered_map<long, std::vector<long>> * g_funcCallCounter;
static std::mutex  * g_lock;
static std::thread * g_flusher;
// tell the flush thread to quit
static std::atomic_bool * g_shouldQuit;
static std::string * g_dataPath;
// exe + all args
static std::string * g_cmdline;
// path of this executable
static std::string * g_binPath;
// initial working directrory,
// "initial" because program may later call chdir()
static std::string * g_pwd;

#if defined (USE_PERF_SYSCALL)
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

    if (g_mode == TIME) {
      pe.type = PERF_TYPE_SOFTWARE;
      pe.config = PERF_COUNT_SW_CPU_CLOCK;
    } else if (g_mode == CYCLE) {
      pe.type = PERF_TYPE_HARDWARE;
      pe.config = PERF_COUNT_HW_REF_CPU_CYCLES;
    } else if (g_mode == INSN) {
      pe.type = PERF_TYPE_HARDWARE;
      pe.config = PERF_COUNT_HW_INSTRUCTIONS;
    }

    // create per-thread perf timer
    fd = syscall(SYS_perf_event_open, &pe, tid, cpu, -1, 0);
    if (fd == -1) {
      fprintf(stderr, "[perfRT] Failed to open perf event: %s\n", strerror(errno));
      abort();
    }

    ioctl(fd, PERF_EVENT_IOC_RESET, 0);
    ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);

    DEBUG(printf("[perfRT] created perf fd %d for tid %d \n", fd, tid););
  }

  ~perfFD() {
    ioctl(fd, PERF_EVENT_IOC_DISABLE, 0);
    close(fd);
    DEBUG(printf("closed perf fd %d\n", fd););
  }
};

// a new perf fd will be created for each thread
static thread_local struct perfFD tl_perffd;
#endif

// Note: the thread-local TL_lastCallTimePerFunc may be destructed if the thread is terminating,
// leading to segfault.
// This is usually because there are other functions registered via `atexit()`.
// When a thread is exiting, glibc will call the destructors of those thread-local variables first before 
// calling functions registered via `atexit()`, hence invalidating the data.
// So do not use thread-local data.

// per thread, fid -> time
// static thread_local std::unordered_map<long, long> TL_lastCallTimePerFunc;

static std::unordered_map<pid_t, std::unordered_map<long, long> *> * g_lastCallTimePerFuncPerThread;
static std::mutex  * g_lastCallTimeMapLock;

//===----------------------------------------------------------------------===//
//
// Interfaces.
//
//===----------------------------------------------------------------------===//

void __trec_perf_func_enter(long fid) {
  if (g_mode == NONE) return;

  DEBUG(printf("[perfRT] enter %ld\n", fid););

  long t = currentTime();
  auto map = getLastCallTimeMap();
  (*map)[fid] = t;
}

void __trec_perf_func_exit(long fid) {
  if (g_mode == NONE) return;

  // FIXME sometimes the key does not exist when 
  // __trec_perf_func_enter() is actually run.
  // E.g., sed when run as `sed '~1d'`
  // Maybe it's because another function is registered by `aexit()`?

  long t   = currentTime();
  auto map = getLastCallTimeMap();
  long val = map->at(fid);
  long delta = t - val;
  int i = computeIndexFromDelta((unsigned int) delta);
  
  g_lock->lock();

  if (g_funcCallCounter->count(fid) == 0) {
    std::vector<long> newVec(g_defaultNumOfBuckets, 0);
    g_funcCallCounter->insert({fid, std::move(newVec)});
  }

  auto & bucket = g_funcCallCounter->at(fid).at(i);
  bucket++;
  DEBUG(printf("[perfRT] exit %ld delta %ld\n", fid, delta););

  g_lock->unlock();
}

void __trec_deinit() {
  if (g_mode == NONE) return;

  DEBUG(printf("perfRT deinit\n"););

  *g_shouldQuit = true;
  g_flusher->join();

  delete g_funcCallCounter;
  delete g_lock;
  delete g_shouldQuit;
  delete g_flusher;
  delete g_dataPath;
  delete g_binPath;
  delete g_cmdline;
  delete g_pwd;
  for (auto kv : *g_lastCallTimePerFuncPerThread) {
    delete kv.second;
  }
  delete g_lastCallTimePerFuncPerThread;
  delete g_lastCallTimeMapLock;
}

void __trec_init() {
  bool b = false;
  if (!std::atomic_compare_exchange_strong(&g_inited, &b, true)) {
    return;
  }

  DEBUG(printf("perfRT init\n"););

  char * env = getenv(g_envMode);
  if (env == nullptr || strcmp(env, "none") == 0) {
    g_mode = NONE;
    return;
  } else if (strcmp(env, "time") == 0) {
    g_mode = TIME;
  } else if (strcmp(env, "cycle") == 0) {
    g_mode = CYCLE;
  } else if (strcmp(env, "insn") == 0) {
    g_mode = INSN;
  } else {
    fprintf(stderr, 
      "[perfRT] Unknown value for env %s: %s, available ones: time, cycle, insn\n", g_envMode, env);
    abort();
  }
  
  env = getenv(g_envDataPath);
  if (env == nullptr) {
    fprintf(stderr, "[perfRT] env %s not set!\n", g_envDataPath);
    abort();
  }
  auto p = std::filesystem::path(env);
  if (std::filesystem::exists(p)) {
    if (!std::filesystem::is_directory(p)) {
      fprintf(stderr, "[perfRT] %s is not a directory!\n", env);
      abort();
    }
  } else {
    std::filesystem::create_directories(p);
  }

  g_pid = getpid();
  // generate data file name: trec_perf_comm_pid.bin
  std::string comm(program_invocation_short_name);
  std::string pidStr(std::to_string(g_pid));
  g_dataPath = new std::string(p.append("trec_perf_" + comm + "_" + pidStr + ".bin"));
  DEBUG(printf("[perfRT] data file: %s\n", g_dataPath->c_str()););

  env = getenv(g_envInterval);
  if (env != nullptr) {
    int step = atoi(env);
    if (step <= 0) {
      fprintf(stderr, "[perfRT] Invalid interval %s, defaults to %d\n", env, g_interval);
    } else {
      g_interval = step;
    }
  }

  // read program name and cmd args
  std::ifstream file("/proc/self/cmdline");
  if (file.bad()) {
    fprintf(stderr, "[perfRT] Fail to read /proc/self/cmdline\n");
    abort();
  }
  std::stringstream ss;
  char c;
  while (!file.eof()) {
    file >> c;
    ss << c;
  }
  g_cmdline = new std::string(ss.str());

  char buf[1024];
  memset(&buf, '\0', sizeof(buf));
  // read program binary path
  if (readlink("/proc/self/exe", buf, sizeof(buf)) < 0) {
      fprintf(stderr, "[perfRT] Fail to read /proc/self/exe\n");
      abort();
  }
  g_binPath = new std::string(buf);

  // read the initial working direcrory
  memset(&buf, '\0', sizeof(buf));
  if (readlink("/proc/self/cwd", buf, sizeof(buf)) < 0) {
      fprintf(stderr, "[perfRT] Fail to read /proc/self/cwd\n");
      abort();
  }
  g_pwd = new std::string(buf);

  // printf("bin: %s, pwd: %s\n", g_binPath->c_str(), g_pwd->c_str());

  initTimeIntervals();
  
  g_funcCallCounter = new std::unordered_map<long, std::vector<long>>();
  g_lock = new std::mutex();
  g_lastCallTimePerFuncPerThread = new std::unordered_map<pid_t, std::unordered_map<long, long> *>();
  g_lastCallTimeMapLock = new std::mutex();
  g_shouldQuit  = new std::atomic_bool(false);
  // spawn a thread for syncing data
  g_flusher = new std::thread(flushData);

  atexit(__trec_deinit);

  DEBUG(printf("perfRT init done\n"););
}

//===----------------------------------------------------------------------===//
//
// Internals.
//
//===----------------------------------------------------------------------===//

std::unordered_map<long, long> * getLastCallTimeMap() {
  g_lastCallTimeMapLock->lock();

  std::unordered_map<long, long> * theMap;
  pid_t tid = gettid();
  if (!g_lastCallTimePerFuncPerThread->contains(tid)) {
    theMap = new std::unordered_map<long, long>();
    (*g_lastCallTimePerFuncPerThread)[tid] = theMap;
  } else {
    theMap = g_lastCallTimePerFuncPerThread->at(tid);
  }

  g_lastCallTimeMapLock->unlock();

  return theMap;
}

inline static long currentTimeClock() {
  struct timespec ts;
  clock_gettime(CLOCK_REALTIME, &ts);

  return ts.tv_sec * 1000000000 + ts.tv_nsec;
}

#if defined (USE_PERF_SYSCALL)
inline static long currentTimePerf() {
  long count;
  read(tl_perffd.fd, &count, sizeof(count));

  return count;
}
#endif

inline static long currentTime() {
#if defined (USE_PERF_SYSCALL)
  return currentTimePerf();
#else
#endif
  return currentTimeClock();
}

static void flushImpl() {
  if (getpid() != g_pid) {
    // TODO write to a new file
    fprintf(stderr, "[perfRT] Program %s has forked, trec perf data is nor recorded in the child process\n", program_invocation_short_name);
    return;
  }

  g_lock->lock();

  std::ofstream ofs(g_dataPath->c_str(), std::ios::out | std::ios::binary | std::ios::trunc);
  ofs.write(g_cmdline->c_str(), g_cmdline->length());
  // End of Text: delimitor
  ofs.put('\3');
  ofs.write(g_binPath->c_str(), g_binPath->length());
  ofs.put('\3');
  ofs.write(g_pwd->c_str(), g_pwd->length());
  ofs.put('\3');
  // write mode
  ofs.write((const char *)&g_mode, sizeof(g_mode));
  // write vector length
  ofs.write((const char *)&g_defaultNumOfBuckets, sizeof(g_defaultNumOfBuckets));
  // write data
  for (auto & kv : *g_funcCallCounter) {
    // fid
    ofs.write((const char *)&kv.first, sizeof(kv.first));
    for (auto & c : kv.second) {
      // buckets
      ofs.write((const char *)&c, sizeof(c));
    }
  }

  ofs.close();

  g_lock->unlock();
}

static void flushData() {
  // Shouldn't handle signals on behalf of normal threads.
  sigset_t set;
  sigemptyset(&set);
  sigfillset(&set);
  pthread_sigmask (SIG_BLOCK, &set, NULL);

  DEBUG(printf("[perfRT] flusher started\n"););

  while (true) {
    // Sleep for 1s, but check for quit signal frequently.
    for (int i = 0; i < 20; i++) {
      if (*g_shouldQuit) {
        flushImpl();
        DEBUG(printf("[perfRT] flusher quit\n"););
        return;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }

    flushImpl();   
  }
}

static void initTimeIntervals() {
  int start = 0;
  for (int i = 0; i < g_defaultNumOfBuckets; i++) {
    g_timeIntervals[i] = start;
    start += g_interval;
  }
}

inline static int computeIndexFromDelta(unsigned int delta) {
  int m;
  int left = 0;
  int right = g_defaultNumOfBuckets - 1;

  // binary search
  while (left <= right) {
    if (left == right) {
      // == 0 or size - 1
      return left;
    }

    m = (left + right) / 2;
    if (delta < g_timeIntervals[m - 1]) {
      // move left
      right = m - 1;
    } else if (g_timeIntervals[m + 1] <= delta) {
      // move right
      left = m + 1;
    } else {
      // v[m - 1] <= delta <= v[m + 1]
      if (delta >= g_timeIntervals[m]) {
        return m;
      } else {
        return m - 1;
      }
    }
  }

  // unreachable
  return -1;
}
