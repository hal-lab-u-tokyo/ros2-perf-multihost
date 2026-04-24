#include "node_options/cli_options.hpp"

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
  log_dir = "";
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
      "ROS 2 performance benchmark node options (publisher/subscriber).");
  options.custom_help("[OPTIONS]");

  options.add_options()("h,help", "Show this help message and exit")(
      "node_name", "Node name (required)",
      cxxopts::value<std::string>(node_name))(
      "topic_names",
      "Topic names (required, repeatable, e.g. --topic_names t1 --topic_names "
      "t2)",
      cxxopts::value<std::vector<std::string>>(topic_names))(
      "s,size",
      "Payload size in bytes for each topic. Provide once to broadcast to all "
      "topics, or provide one value per topic.",
      cxxopts::value<std::vector<int>>(payload_size),
      "bytes")("p,period",
               "Publish period in milliseconds for each topic. Provide once to "
               "broadcast to all topics, or provide one value per topic.",
               cxxopts::value<std::vector<int>>(period_ms), "ms")(
      "eval_time", "Evaluation duration in seconds",
      cxxopts::value<int>(eval_time)->default_value("60"), "sec")(
      "log_dir",
      "Directory to write logs and metadata. If omitted, no log files are "
      "created.",
      cxxopts::value<std::string>(log_dir))(
      "qos_history", "QoS history policy: KEEP_LAST or KEEP_ALL",
      cxxopts::value<std::string>(qos_history)->default_value("KEEP_LAST"))(
      "qos_depth", "QoS depth when qos_history=KEEP_LAST",
      cxxopts::value<int>(qos_depth)->default_value("1"))(
      "qos_reliability", "QoS reliability: RELIABLE or BEST_EFFORT",
      cxxopts::value<std::string>(qos_reliability)->default_value("RELIABLE"));

  auto print_help = [&options, &executable_name]() {
    std::cout << "Node role:\n";
    if (executable_name == "subscriber_node") {
      std::cout
          << "  Subscriber: receives messages on --topic_names and records "
             "receive timestamps and metadata when --log_dir is set.\n\n"
          << options.help() << "\n"
          << "Example:\n"
          << "  ros2 run ros2_perf_multihost_nodes subscriber_node \\\n"
          << "    --node_name sub1 --topic_names topic1\n";
      return;
    }

    std::cout
        << "  Publisher: periodically publishes payloads to --topic_names and "
           "records publish timestamps and metadata when --log_dir is set.\n\n"
        << options.help() << "\n"
        << "Example:\n"
        << "  ros2 run ros2_perf_multihost_nodes " << executable_name << " \\\n"
        << "    --node_name pub1 --topic_names topic1 --size 64 --period "
           "100\n";
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

    if (result.count("topic_names") == 0) {
      std::cout << "Error: --topic_names is required.\n\n";
      print_help();
      std::exit(1);
    }

    if (!payload_size.empty() && payload_size.size() == 1 &&
        !topic_names.empty()) {
      payload_size = std::vector<int>(topic_names.size(), payload_size[0]);
    } else if (!payload_size.empty() &&
               payload_size.size() != topic_names.size()) {
      std::cout << "Error: --size must be specified once or match the number "
                   "of --topic_names entries.\n\n";
      print_help();
      std::exit(1);
    }

    if (!period_ms.empty() && period_ms.size() == 1 && !topic_names.empty()) {
      period_ms = std::vector<int>(topic_names.size(), period_ms[0]);
    } else if (!period_ms.empty() && period_ms.size() != topic_names.size()) {
      std::cout << "Error: --period must be specified once or match the "
                   "number of --topic_names entries.\n\n";
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
  os << "Log output: "
     << (options.log_dir.empty() ? "disabled" : options.log_dir) << std::endl;

  for (size_t i = 0; i < options.topic_names.size(); ++i) {
    os << "Topic: " << options.topic_names[i] << std::endl;

    if (!options.payload_size.empty()) {
      os << "payload_size: " << options.payload_size[i] << " bytes"
         << std::endl;
    }

    if (!options.period_ms.empty()) {
      os << "period_ms: " << options.period_ms[i] << " ms" << std::endl;
    }
  }

  return os;
}

}  // namespace node_options
