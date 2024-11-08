cmake_minimum_required(VERSION 3.22)
project(TraceRecorder)
include(GNUInstallDirs)

# use C++20.
set(CMAKE_CXX_STANDARD 20)

# Load LLVMConfig.cmake. If this fails, consider setting `LLVM_DIR` to point
# to your LLVM installation's `lib/cmake/llvm` directory.
find_package(LLVM REQUIRED CONFIG)

# Include the part of LLVM's CMake libraries that defines
# `add_llvm_pass_plugin`.
include(AddLLVM)

# Use LLVM's preprocessor definitions, include directories, and library search
# paths.
add_definitions(${LLVM_DEFINITIONS})
include_directories(${LLVM_INCLUDE_DIRS})
link_directories(${LLVM_LIBRARY_DIRS})



# Our pass lives in this subdirectory.
# add_subdirectory(skeleton)
add_subdirectory(Pass)
add_subdirectory(perfRT)

configure_file(perf-clang.in   ${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_BINDIR}/perf-clang   FILE_PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)
configure_file(perf-clang++.in ${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_BINDIR}/perf-clang++ FILE_PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)
