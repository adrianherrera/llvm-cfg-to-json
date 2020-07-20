# Same version required by LLVM 7
cmake_minimum_required(VERSION 3.4.3)

set(CMAKE_CXX_STANDARD 11)

set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Werror -fno-rtti")

find_package(LLVM REQUIRED CONFIG)
message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")

list(APPEND CMAKE_MODULE_PATH "${LLVM_CMAKE_DIR}")
include(AddLLVM)

add_definitions(${LLVM_DEFINITIONS})
include_directories(${LLVM_INCLUDE_DIRS} ${CMAKE_CURRENT_SOURCE_DIR}/jsoncpp)

add_library(LLVMCFGToJSON MODULE CFGToJSON.cpp jsoncpp/jsoncpp.cpp)
