#######################################################
### Clang-Unformat                                  ###
#######################################################
cmake_minimum_required(VERSION 3.10)
project(clang_unformat)

set(CXX_STANDARD 20)
set(CMAKE_POLICY_DEFAULT_CMP0063 NEW)
set(CMAKE_POLICY_DEFAULT_CMP0077 NEW)

#######################################################
### Dependencies                                    ###
#######################################################
include(FetchContent)

# Threads
find_package(Threads)

# Boost
# find_package(Boost 1.84.0 COMPONENTS asio config process program_options)
set(Boost_FOUND OFF)
if (NOT Boost_FOUND)
    set(BOOST_VERSION 1.84.0)
    message("Boost library not found or Version < 1.84.0 ; fetch and install Version ${BOOST_VERSION}")
    set(BOOST_INCLUDE_LIBRARIES asio config filesystem process program_options)
    set(BOOST_ENABLE_CMAKE ON)

    FetchContent_Declare(
        Boost
        URL https://github.com/boostorg/boost/releases/download/boost-${BOOST_VERSION}/boost-${BOOST_VERSION}.zip
        URL_HASH SHA256=f46e9a747e0828130d37ead82b796ab82348e3a7ee688cd43b6c5f35f5e71aef
        DOWNLOAD_EXTRACT_TIMESTAMP true
        GIT_TAG boost-${BOOST_VERSION}
    )
    FetchContent_MakeAvailable(Boost)
endif()

# fmt
# find_package(fmt QUIET)
set(fmt_FOUND OFF)
if (NOT fmt_FOUND)
    option(FMT_DOC OFF)
    option(FMT_TEST OFF)
    option(FMT_INSTALL OFF)
    FetchContent_Declare(fmt
        URL https://github.com/fmtlib/fmt/releases/download/10.2.1/fmt-10.2.1.zip
        URL_HASH SHA256=312151a2d13c8327f5c9c586ac6cf7cddc1658e8f53edae0ec56509c8fa516c9
        DOWNLOAD_EXTRACT_TIMESTAMP true
    )
    FetchContent_MakeAvailable(fmt)
endif()

# futures
option(FUTURES_PREFER_BOOST ON)
FetchContent_Declare(futures
    URL https://github.com/alandefreitas/futures/archive/refs/tags/v0.1.5.zip
    URL_HASH SHA256=09472daf7a49a9194085dce7e436b06fe1cc435a95aa50e2f8676191d71a9759
    DOWNLOAD_EXTRACT_TIMESTAMP true
)
FetchContent_MakeAvailable(futures)

# edlib
# find_package(edlib CONFIG QUIET)
if (NOT edlib_FOUND)
    FetchContent_Declare(edlib
        URL https://github.com/Martinsos/edlib/archive/refs/tags/v1.2.7.zip
        URL_HASH SHA256=e8f6919998a3f45fe62837549751082f57d67f0a2be0fdc35c2ff8d13a2dfea5
        DOWNLOAD_EXTRACT_TIMESTAMP true
    )
    FetchContent_MakeAvailable(edlib)
endif()

# add_compile_options(-glldb)
# add_compile_options(-O0 -fno-omit-frame-pointer)

#######################################################
### Executable                                      ###
#######################################################
add_executable(clang-unformat
        standalone/application.cpp
        standalone/application.hpp
        standalone/clang_format.cpp
        standalone/clang_format.hpp
        standalone/cli_config.cpp
        standalone/cli_config.hpp
        standalone/levenshtein.cpp
        standalone/levenshtein.hpp
        standalone/main.cpp)
target_include_directories(clang-unformat PRIVATE standalone)
target_compile_features(clang-unformat PRIVATE cxx_std_20)
# target_compile_options(clang-unformat PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(clang-unformat PRIVATE
    Boost::asio
    Boost::filesystem
    Boost::process
    Boost::program_options
    edlib::edlib
    fmt::fmt
    futures::futures
    Threads::Threads
)
install(TARGETS clang-unformat
    RUNTIME DESTINATION bin
)
