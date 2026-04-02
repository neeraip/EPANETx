# EPANET COMMAND LINE EXECUTABLE
cmake_minimum_required (VERSION 3.8.0)

if(POLICY CMP0069)
  cmake_policy(SET CMP0069 NEW)
endif()


# Sets for output directory for executables and libraries.
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)

# Sets the position independent code property for all targets.
set(CMAKE_POSITION_INDEPENDENT_CODE ON)


# Link to multi-threaded static runtime library
IF (MSVC)
  add_definitions(-D_CRT_SECURE_NO_DEPRECATE -MT)
ENDIF (MSVC)


# Set up file groups for exe target
set(EPANET_CLI_SOURCES main.c)
include_directories(include)

source_group("CLI" FILES ${EPANET_CLI_SOURCES})


# Creates the EPANETx command line executable
add_executable(epanetx ${EPANET_CLI_SOURCES})
if(NOT WIN32)
  target_link_libraries(epanetx LINK_PUBLIC epanet2 m)
else(NOT WIN32)
  target_link_libraries(epanetx LINK_PUBLIC epanet2)
endif(NOT WIN32)

