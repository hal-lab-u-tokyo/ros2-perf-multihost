cmake_minimum_required(VERSION 3.12)
project(subscriber_node)

set(CMAKE_CXX_STANDARD 17)

# 依存パッケージの発見
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(std_msgs REQUIRED)
find_package(node_options REQUIRED)
find_package(publisher_node REQUIRED)

# 変数の設定
set(LIBRARY_NAME ${PROJECT_NAME})
set(LIBRARY_DEPENDENCIES rclcpp std_msgs node_options publisher_node)

# 実行ファイルの追加　ここではsrc/subscriber_node.cppをsubscriber_nodeという名前で登録
add_executable(${LIBRARY_NAME} src/${LIBRARY_NAME}.cpp)

# インクルードしたいincludeフォルダの場所を指定
target_include_directories(
  ${LIBRARY_NAME}
  PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../node_options/include>
         $<INSTALL_INTERFACE:include>)

# 依存関係の解決
ament_target_dependencies(${LIBRARY_NAME} ${LIBRARY_DEPENDENCIES})

# colcon buildの際にinstallに入るものを設定
install(TARGETS ${LIBRARY_NAME}
        DESTINATION lib/${LIBRARY_NAME} # 実行ファイルを lib/<パッケージ名>/ に配置
)

# パッケージをROS2のパッケージ管理システムに認識させる
ament_package()
