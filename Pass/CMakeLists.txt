# set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${PROJECT_SOURCE_DIR}/lib)
link_libraries(sqlite3)
add_llvm_pass_plugin(PerfInstrPass
    # List your source files here.
    PerfInstrPass.cpp
    SqliteDebugWriter.cpp
)
#target_compile_options(PerfInstrPass PUBLIC "-g" "-Og")
target_compile_options(PerfInstrPass PUBLIC "-O2")


