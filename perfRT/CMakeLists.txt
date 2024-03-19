set(PERFRT_SRC perfRT.cpp)
add_library(perfRT STATIC ${PERFRT_SRC})
# target_link_libraries(perfRT pthread)
set(CMAKE_CXX_STANDARD_REQUIRED true)
target_compile_features(perfRT PUBLIC cxx_std_17)
target_compile_options(perfRT PUBLIC "-fno-exceptions" "-fno-rtti" "-g" "-Og")

option(USE_PERF_SYSCALL "Use perf_event_open() instead of clock_gettime() if enabled" OFF)
if (USE_PERF_SYSCALL)
    target_compile_definitions(perfRT PUBLIC "USE_PERF_SYSCALL")
    message("Using perf_event_open()")
endif()

install(TARGETS perfRT)