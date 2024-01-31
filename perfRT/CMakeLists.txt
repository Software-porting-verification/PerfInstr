set(PERFRT_SRC perfRT.cpp)
add_library(perfRT STATIC ${PERFRT_SRC})
# target_link_libraries(perfRT pthread)
set(CMAKE_CXX_STANDARD_REQUIRED true)
target_compile_features(perfRT PUBLIC cxx_std_17)
target_compile_options(perfRT PUBLIC "-fno-exceptions" "-fno-rtti" "-g" "-Og")

install(TARGETS perfRT)