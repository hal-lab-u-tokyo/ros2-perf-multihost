cmake_minimum_required(VERSION 3.12)
project(publisher_node)

set(CMAKE_CXX_STANDARD 17)

# 依存パッケージの発見
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(std_msgs REQUIRED)

find_package(node_options REQUIRED)

# カスタムメッセージ関連
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
set(msg_files "msg/PerformanceHeader.msg" "msg/IntMessage.msg")
rosidl_generate_interfaces(${PROJECT_NAME} ${msg_files} DEPENDENCIES
                           builtin_interfaces)

# 変数の設定
set(LIBRARY_NAME ${PROJECT_NAME})
set(LIBRARY_DEPENDENCIES rclcpp std_msgs node_options)

# 実行ファイルの追加　ここではsrc/publisher_node.cppをpublisher_node_exeという名前で登録
add_executable(${LIBRARY_NAME}_exe src/${LIBRARY_NAME}.cpp)

# インクルードしたいincludeフォルダの場所を指定
target_include_directories(
  ${LIBRARY_NAME}_exe
  PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../node_options/include>
         $<INSTALL_INTERFACE:include>)

rosidl_get_typesupport_target(cpp_typesupport_target ${LIBRARY_NAME}
                              rosidl_typesupport_cpp)
target_link_libraries(${LIBRARY_NAME}_exe "${cpp_typesupport_target}")

# 依存関係の解決
ament_target_dependencies(${LIBRARY_NAME}_exe ${LIBRARY_DEPENDENCIES})

# colcon buildの際にinstallに入るものを設定
install(TARGETS ${LIBRARY_NAME}_exe
        DESTINATION lib/${LIBRARY_NAME} # 実行ファイルを lib/<パッケージ名>/ に配置
)

# パッケージをROS2のパッケージ管理システムに認識させる
ament_package()
