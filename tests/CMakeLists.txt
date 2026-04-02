#
# CMakeLists.txt - CMake configuration file for epanet/tests
#
# Created: February 13, 2018
#
# Modified by: Michael E. Tryby
#              US EPA ORD/NRMRL
#


# Sets for output directory for executables and libraries.
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

find_package(Python3 QUIET COMPONENTS Interpreter)

if(UNIX)
    set(CMAKE_CXX_FLAGS "-std=c++11")
endif(UNIX)


add_executable(test_net_builder test_net_builder.cpp)
target_link_libraries(test_net_builder ${Boost_LIBRARIES} epanet2)
add_test(NAME test_net_builder
    COMMAND ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/test_net_builder
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/data)


set(toolkit_test_srcs
     test_toolkit.cpp
     test_project.cpp
     test_hydraulics.cpp
     test_quality.cpp
     test_report.cpp
     test_analysis.cpp
     test_node.cpp
     test_demand.cpp
     test_link.cpp
#     test_pump.cpp
     test_pattern.cpp
     test_curve.cpp
     test_control.cpp
     test_overflow.cpp
     test_pda.cpp
     test_valve.cpp
     test_units.cpp
     test_leakage.cpp
)

add_executable(test_toolkit ${toolkit_test_srcs})
target_link_libraries(test_toolkit ${Boost_LIBRARIES} epanet2)
add_test(NAME test_toolkit
    COMMAND ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/test_toolkit
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/data)



add_executable(test_reent test_reent.cpp)

IF(MSVC)
    target_link_libraries(test_reent ${Boost_LIBRARIES} epanet2)
ELSE(TRUE)
    target_link_libraries(test_reent ${Boost_LIBRARIES} pthread epanet2)
ENDIF(MSVC)

add_test(NAME test_reent
    COMMAND ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/test_reent
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/data)


# ctest doesn't like tests added in subdirectories so adding them here
add_test(NAME test_errormanager
    COMMAND ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/test_errormanager)

add_test(NAME test_filemanager
    COMMAND ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/test_filemanager
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/outfile/data)

add_test(NAME test_output
    COMMAND ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/test_output
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/outfile/data)

if(Python3_Interpreter_FOUND)
    add_test(NAME test_cli_parity_small
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_cli_parity.py
            --epanetx-exe ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/epanetx
            --fixture ${CMAKE_CURRENT_SOURCE_DIR}/fixtures/canonical_small_loop.inp
            --workdir ${CMAKE_BINARY_DIR}/tests/parity/small)
    set_tests_properties(test_cli_parity_small PROPERTIES
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})

    if(EXISTS ${PROJECT_SOURCE_DIR}/benchmarks/networks/realistic_city_60x60.inp)
        add_test(NAME test_cli_parity_large
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_cli_parity.py
                --epanetx-exe ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/epanetx
                --fixture ${PROJECT_SOURCE_DIR}/benchmarks/networks/realistic_city_60x60.inp
                --workdir ${CMAKE_BINARY_DIR}/tests/parity/large)
        set_tests_properties(test_cli_parity_large PROPERTIES
            WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})
    else()
        message(STATUS "realistic_city_60x60.inp not found; skipping test_cli_parity_large registration")
    endif()
else()
    message(STATUS "Python3 interpreter not found; skipping CLI parity test registration")
endif()
