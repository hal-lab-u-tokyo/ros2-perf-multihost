#include "node_options_intermediate/cli_options.hpp"

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

#include "cxxopts.hpp"

namespace node_options {

// デフォルト値
Options::Options() {
  eval_time = 60;
  log_dir = "./logs";
  qos_history = "KEEP_LAST";
  qos_depth = 1;
  qos_reliability = "RELIABLE";
}

// コンストラクタ
Options::Options(int argc, char** argv) : Options() { parse(argc, argv); }

// 受け取ったコマンドライン引数をもとに、option変数を更新
void Options::parse(int argc, char** argv) {
  const std::string executable_name =
      std::filesystem::path(argv[0]).filename().string();
  const std::string usage_command =
      "ros2 run ros2_perf_multihost_nodes " + executable_name;
  cxxopts::Options options(
      usage_command,
      "ROS 2 performance benchmark node options (intermediate node).");
  options.custom_help("[OPTIONS]");

  options.add_options()("h,help", "Show this help message and exit")(
      "node_name", "Node name (required)",
      cxxopts::value<std::string>(node_name))(
      "topic_names_pub",
      "Publisher topic names (optional, repeatable). Required when --size or "
      "--period is provided.",
      cxxopts::value<std::vector<std::string>>(topic_names_pub))(
      "topic_names_sub", "Subscriber topic names (optional, repeatable)",
      cxxopts::value<std::vector<std::string>>(topic_names_sub))(
      "s,size",
      "Payload size in bytes for publisher topics. Provide once to broadcast "
      "to all publisher topics, or provide one value per publisher topic.",
      cxxopts::value<std::vector<int>>(payload_size), "bytes")(
      "p,period",
      "Publish period in milliseconds for publisher topics. Provide once to "
      "broadcast to all publisher topics, or provide one value per publisher "
      "topic.",
      cxxopts::value<std::vector<int>>(period_ms),
      "ms")("eval_time", "Evaluation duration in seconds",
            cxxopts::value<int>(eval_time)->default_value("60"), "sec")(
      "log_dir", "Directory to write logs",
      cxxopts::value<std::string>(log_dir)->default_value("./logs"))(
      "qos_history", "QoS history policy: KEEP_LAST or KEEP_ALL",
      cxxopts::value<std::string>(qos_history)->default_value("KEEP_LAST"))(
      "qos_depth", "QoS depth when qos_history=KEEP_LAST",
      cxxopts::value<int>(qos_depth)->default_value("1"))(
      "qos_reliability", "QoS reliability: RELIABLE or BEST_EFFORT",
      cxxopts::value<std::string>(qos_reliability)->default_value("RELIABLE"));

  auto print_help = [&options]() {
    std::cout
        << "Node role:\n"
        << "  Intermediate: can subscribe on --topic_names_sub, publish on "
           "--topic_names_pub, and relay when topic names overlap.\n\n"
        << options.help() << "\n"
        << "Examples:\n"
        << "  ros2 run ros2_perf_multihost_nodes intermediate_node \\\n"
        << "    --node_name relay1 --topic_names_pub topic_out "
           "--topic_names_sub "
           "topic_in \\\n"
        << "    --size 64 --period 100\n"
        << "  ros2 run ros2_perf_multihost_nodes intermediate_node \\\n"
        << "    --node_name sub_only --topic_names_sub topic_in\n";
  };

  try {
    auto result = options.parse(argc, argv);

    if (result.count("help") > 0) {
      print_help();
      std::exit(0);
    }

    if (result.count("node_name") == 0) {
      std::cout << "Error: --node_name is required.\n\n";
      print_help();
      std::exit(1);
    }

    if (!payload_size.empty() && payload_size.size() == 1 &&
        !topic_names_pub.empty()) {
      payload_size = std::vector<int>(topic_names_pub.size(), payload_size[0]);
    } else if (!payload_size.empty() &&
               payload_size.size() != topic_names_pub.size()) {
      std::cout << "Error: --size must be specified once or match the number "
                   "of --topic_names_pub entries.\n\n";
      print_help();
      std::exit(1);
    }

    if (!period_ms.empty() && period_ms.size() == 1 &&
        !topic_names_pub.empty()) {
      period_ms = std::vector<int>(topic_names_pub.size(), period_ms[0]);
    } else if (!period_ms.empty() &&
               period_ms.size() != topic_names_pub.size()) {
      std::cout << "Error: --period must be specified once or match the "
                   "number of --topic_names_pub entries.\n\n";
      print_help();
      std::exit(1);
    }

    if (result.count("topic_names_pub") == 0 &&
        result.count("topic_names_sub") == 0) {
      std::cout << "Error: at least one of --topic_names_pub or "
                   "--topic_names_sub is required.\n\n";
      print_help();
      std::exit(1);
    }

    if ((result.count("size") > 0 || result.count("period") > 0) &&
        result.count("topic_names_pub") == 0) {
      std::cout << "Error: --size and --period require --topic_names_pub.\n\n";
      print_help();
      std::exit(1);
    }

  } catch (const cxxopts::exceptions::exception& e) {
    std::cout << "Error parsing options: " << e.what() << "\n\n";
    print_help();
    std::exit(1);
  }
}

// コマンドラインでの表示を見やすくするためのオーバーロード処理
std::ostream& operator<<(std::ostream& os, const Options& options) {
  os << "Node Name: " << options.node_name << std::endl;
  os << "Evaluation time: " << options.eval_time << "s" << std::endl;

  if (!options.topic_names_pub.empty()) {
    for (size_t i = 0; i < options.topic_names_pub.size(); ++i) {
      os << "Topic: " << options.topic_names_pub[i] << std::endl;

      if (!options.payload_size.empty()) {
        os << "payload_size: " << options.payload_size[i] << " bytes"
           << std::endl;
      }

      if (!options.period_ms.empty()) {
        os << "period_ms: " << options.period_ms[i] << " ms" << std::endl;
      }
    }
  }

  if (!options.topic_names_sub.empty()) {
    for (size_t i = 0; i < options.topic_names_sub.size(); ++i) {
      os << "Topic: " << options.topic_names_sub[i] << std::endl;
    }
  }

  return os;
}

}  // namespace node_options
