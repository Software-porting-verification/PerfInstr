set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${PROJECT_SOURCE_DIR}/lib)
add_llvm_pass_plugin(SkeletonPass
    # List your source files here.
    Skeleton.cpp
)
