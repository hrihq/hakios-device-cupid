cmake_minimum_required(VERSION 3.16)
project(hakimetal CXX)

# HakiMetal -- an experimental, backend-independent graphics API for HakiOS.
#
# Phase 1 scope: the frontend, the backend interface, a null backend, a Vulkan backend that detects
# Vulkan and reports what it can, and a test suite that runs without a GPU.

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

add_library(hakimetal STATIC
    src/frontend.cpp
    src/registry.cpp
    src/backend_null.cpp
    src/backend_vulkan.cpp
)

target_include_directories(hakimetal PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)

# dlopen/dlsym live in libdl on glibc < 2.34 and on some BSDs; on newer glibc they are in libc.
# CMAKE_DL_LIBS is empty where they are not needed.
target_link_libraries(hakimetal PUBLIC ${CMAKE_DL_LIBS})

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(hakimetal PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(hakimetal-tests
    tests/test_main.cpp
)

target_link_libraries(hakimetal-tests PRIVATE hakimetal)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(hakimetal-tests PRIVATE -Wall -Wextra -Wpedantic)
endif()

enable_testing()
add_test(NAME hakimetal-tests COMMAND hakimetal-tests)
