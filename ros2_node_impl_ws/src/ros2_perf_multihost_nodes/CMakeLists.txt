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

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(message_files msg/PerformanceHeader.msg msg/IntMessage.msg)

rosidl_generate_interfaces(${PROJECT_NAME} ${message_files} DEPENDENCIES
                           builtin_interfaces)

rosidl_get_typesupport_target(cpp_typesupport_target ${PROJECT_NAME}
                              rosidl_typesupport_cpp)

add_library(node_options SHARED src/node_options/cli_options.cpp)
target_include_directories(
  node_options PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
                      $<INSTALL_INTERFACE:include>)
ament_target_dependencies(node_options cxxopts)

add_library(node_options_intermediate SHARED
            src/node_options_intermediate/cli_options.cpp)
target_include_directories(
  node_options_intermediate
  PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
         $<INSTALL_INTERFACE:include>)
ament_target_dependencies(node_options_intermediate cxxopts)

add_executable(publisher_node src/publisher_node.cpp)
target_include_directories(
  publisher_node PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
                        $<INSTALL_INTERFACE:include>)
ament_target_dependencies(publisher_node rclcpp std_msgs)
target_link_libraries(publisher_node node_options "${cpp_typesupport_target}")

add_executable(subscriber_node src/subscriber_node.cpp)
target_include_directories(
  subscriber_node PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
                         $<INSTALL_INTERFACE:include>)
ament_target_dependencies(subscriber_node rclcpp std_msgs)
target_link_libraries(subscriber_node node_options "${cpp_typesupport_target}")

add_executable(intermediate_node src/intermediate_node.cpp)
target_include_directories(
  intermediate_node
  PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
         $<INSTALL_INTERFACE:include>)
ament_target_dependencies(intermediate_node rclcpp std_msgs)
target_link_libraries(intermediate_node node_options_intermediate
                      "${cpp_typesupport_target}")

install(DIRECTORY include/ DESTINATION include)

install(
  TARGETS node_options node_options_intermediate
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)

install(TARGETS publisher_node subscriber_node intermediate_node
        DESTINATION lib/${PROJECT_NAME})

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
