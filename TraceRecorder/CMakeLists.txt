set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${PROJECT_SOURCE_DIR}/lib)
link_libraries(sqlite3)
add_llvm_pass_plugin(TraceRecorder
    # List your source files here.
    TraceRecorder.cpp
    DEPENDS
    clang_rt.trec-x86_64  
    clang_rt.trec_cxx-x86_64
)


