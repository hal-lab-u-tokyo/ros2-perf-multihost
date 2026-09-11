cmake_minimum_required(VERSION 3.8)
project(ros2_perf_multihost_nodes)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(cxxopts REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

file(GLOB absolute_message_files CONFIGURE_DEPENDS msg/*.msg)
set(message_files)
foreach(message_file IN LISTS absolute_message_files)
  file(RELATIVE_PATH relative_message_file ${CMAKE_CURRENT_SOURCE_DIR}
       ${message_file})
  list(APPEND message_files ${relative_message_file})
endforeach()

rosidl_generate_interfaces(${PROJECT_NAME} ${message_files} DEPENDENCIES
                           builtin_interfaces)

rosidl_get_typesupport_target(cpp_typesupport_target ${PROJECT_NAME}
                              rosidl_typesupport_cpp)

set(message_registry_script
    ${CMAKE_CURRENT_SOURCE_DIR}/../../../manager_scripts/generate_exec/message_registry.py
)
set(generated_include_dir ${CMAKE_CURRENT_BINARY_DIR}/generated/include)
set(generated_message_registry ${generated_include_dir}/message_registry.hpp)
add_custom_command(
  OUTPUT ${generated_message_registry}
  COMMAND
    ${Python3_EXECUTABLE} ${message_registry_script} --msg-dir
    ${CMAKE_CURRENT_SOURCE_DIR}/msg --cpp-output ${generated_message_registry}
  DEPENDS ${message_registry_script} ${message_files}
  VERBATIM)
add_custom_target(generate_message_registry
                  DEPENDS ${generated_message_registry})

add_library(benchmark_options SHARED src/benchmark_options/cli_options.cpp)
target_include_directories(
  benchmark_options
  PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
         $<BUILD_INTERFACE:${generated_include_dir}>
         $<INSTALL_INTERFACE:include>)
ament_target_dependencies(benchmark_options cxxopts)
target_link_libraries(benchmark_options "${cpp_typesupport_target}")
add_dependencies(benchmark_options generate_message_registry)

add_executable(benchmark_node src/benchmark_node.cpp)
target_include_directories(
  benchmark_node
  PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
         $<BUILD_INTERFACE:${generated_include_dir}>
         $<INSTALL_INTERFACE:include>)
ament_target_dependencies(benchmark_node rclcpp std_msgs)
target_link_libraries(benchmark_node benchmark_options
                      "${cpp_typesupport_target}")
add_dependencies(benchmark_node generate_message_registry)

install(DIRECTORY include/ DESTINATION include)

install(
  TARGETS benchmark_options
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)

install(TARGETS benchmark_node DESTINATION lib/${PROJECT_NAME})

install(DIRECTORY launch DESTINATION share/${PROJECT_NAME})

ament_export_dependencies(rosidl_default_runtime)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights comment the
  # line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo) comment the line
  # when this package is in a git repo and when a copyright and license is added
  # to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
