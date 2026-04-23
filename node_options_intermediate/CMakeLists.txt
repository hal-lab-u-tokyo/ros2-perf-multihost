cmake_minimum_required(VERSION 3.12)
project(node_options_intermediate)

set(CMAKE_CXX_STANDARD 17)

find_package(ament_cmake REQUIRED)
find_package(cxxopts REQUIRED)

set(LIBRARY_SRC src/cli_options.cpp)
set(LIBRARY_DEPENDENCIES cxxopts)
set(LIBRARY_NAME ${PROJECT_NAME})

add_library(${LIBRARY_NAME} SHARED ${LIBRARY_SRC})

target_include_directories(
  node_options_intermediate
  PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include> # ビルド時のパス
         $<INSTALL_INTERFACE:include> # インストール後のパス
)

ament_target_dependencies(${LIBRARY_NAME} ${LIBRARY_DEPENDENCIES})

# ビルドシステムで定義されたターゲット（ライブラリや実行ファイル）を他のパッケージが利用できるようにエクスポート
ament_export_targets(export_${LIBRARY_NAME} HAS_LIBRARY_TARGET)
ament_export_dependencies(cxxopts)

# includeディレクトリ自体をinstall内にコピー
install(DIRECTORY include/ DESTINATION include)

install(
  TARGETS ${LIBRARY_NAME}
  EXPORT export_${LIBRARY_NAME} # export_minimal_comp_node という名前でターゲットをエクスポート
  ARCHIVE DESTINATION lib # 静的ライブラリは lib にインストール
  LIBRARY DESTINATION lib # 動的ライブラリは lib にインストール
  RUNTIME DESTINATION bin # 実行ファイルは bin にインストール
  INCLUDES
  DESTINATION include # ヘッダーファイルは include にインストール
)

ament_package()
