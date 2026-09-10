#include "benchmark_options/cli_options.hpp"

#include <cstdlib>
#include <iostream>
#include <vector>

#include "cxxopts.hpp"

namespace benchmark_options {

Options::Options()
    : eval_time(60),
      qos_history("KEEP_LAST"),
      qos_depth(1),
      qos_reliability("RELIABLE") {}

Options::Options(int argc, char** argv) : Options() { parse(argc, argv); }

void Options::parse(int argc, char** argv) {
  constexpr int kDefaultPayloadSize = 64;
  constexpr int kDefaultPeriodMs = 100;

  cxxopts::Options options("ros2 run ros2_perf_multihost_nodes benchmark_node",
                           "ROS 2 performance benchmark node options.");
  options.custom_help("[OPTIONS]");
  options.add_options()("h,help", "Show this help message and exit")(
      "node-name", "Node name (required)",
      cxxopts::value<std::string>(node_name))(
      "topic-names-pub", "Publisher topic names (repeatable)",
      cxxopts::value<std::vector<std::string>>(topic_names_pub))(
      "topic-names-sub", "Subscriber topic names (repeatable)",
      cxxopts::value<std::vector<std::string>>(topic_names_sub))(
      "s,size", "Payload size in bytes for publisher topics",
      cxxopts::value<std::vector<int>>(payload_size), "bytes")(
      "p,period", "Publish period in milliseconds for publisher topics",
      cxxopts::value<std::vector<int>>(period_ms),
      "ms")("eval-time", "Evaluation duration in seconds",
            cxxopts::value<int>(eval_time)->default_value("60"),
            "sec")("log-dir", "Directory to write logs and metadata",
                   cxxopts::value<std::string>(log_dir))(
      "qos-history", "QoS history policy: KEEP_LAST or KEEP_ALL",
      cxxopts::value<std::string>(qos_history)->default_value("KEEP_LAST"))(
      "qos-depth", "QoS depth when qos_history=KEEP_LAST",
      cxxopts::value<int>(qos_depth)->default_value("1"))(
      "qos-reliability", "QoS reliability: RELIABLE or BEST_EFFORT",
      cxxopts::value<std::string>(qos_reliability)->default_value("RELIABLE"));

  auto print_help = [&options]() {
    std::cout << "Node role:\n"
              << "  Benchmark: periodically publishes on --topic-names-pub "
                 "and records messages received on --topic-names-sub.\n\n"
              << options.help() << "\nExample:\n"
              << "  ros2 run ros2_perf_multihost_nodes benchmark_node \\\n"
              << "    --node-name node1 --topic-names-pub output \\\n"
              << "    --topic-names-sub input --size 64 --period 100\n";
  };

  try {
    const auto result = options.parse(argc, argv);
    if (result.count("help") > 0) {
      print_help();
      std::exit(0);
    }
    if (result.count("node-name") == 0) {
      std::cout << "Error: --node-name is required.\n\n";
      print_help();
      std::exit(1);
    }
    if (topic_names_pub.empty() && topic_names_sub.empty()) {
      std::cout << "Error: at least one publisher or subscriber topic is "
                   "required.\n\n";
      print_help();
      std::exit(1);
    }
    for (const auto& publisher_topic : topic_names_pub) {
      for (const auto& subscriber_topic : topic_names_sub) {
        if (publisher_topic == subscriber_topic) {
          std::cout
              << "Error: publisher and subscriber topics must not overlap: "
              << publisher_topic << ".\n\n";
          print_help();
          std::exit(1);
        }
      }
    }
    if (!payload_size.empty() && topic_names_pub.empty()) {
      std::cout << "Error: --size requires --topic-names-pub.\n\n";
      print_help();
      std::exit(1);
    }
    if (!period_ms.empty() && topic_names_pub.empty()) {
      std::cout << "Error: --period requires --topic-names-pub.\n\n";
      print_help();
      std::exit(1);
    }

    if (payload_size.empty()) {
      payload_size.assign(topic_names_pub.size(), kDefaultPayloadSize);
    } else if (payload_size.size() == 1) {
      payload_size.assign(topic_names_pub.size(), payload_size.front());
    } else if (payload_size.size() != topic_names_pub.size()) {
      std::cout << "Error: --size must be specified once or match the number "
                   "of --topic-names-pub entries.\n\n";
      print_help();
      std::exit(1);
    }
    for (const int size : payload_size) {
      if (size <= 0) {
        std::cout << "Error: --size values must be positive.\n\n";
        print_help();
        std::exit(1);
      }
    }

    if (period_ms.empty()) {
      period_ms.assign(topic_names_pub.size(), kDefaultPeriodMs);
    } else if (period_ms.size() == 1) {
      period_ms.assign(topic_names_pub.size(), period_ms.front());
    } else if (period_ms.size() != topic_names_pub.size()) {
      std::cout << "Error: --period must be specified once or match the "
                   "number of --topic-names-pub entries.\n\n";
      print_help();
      std::exit(1);
    }
    for (const int period : period_ms) {
      if (period <= 0) {
        std::cout << "Error: --period values must be positive.\n\n";
        print_help();
        std::exit(1);
      }
    }
  } catch (const cxxopts::exceptions::exception& exception) {
    std::cout << "Error parsing options: " << exception.what() << "\n\n";
    print_help();
    std::exit(1);
  }
}

std::ostream& operator<<(std::ostream& os, const Options& options) {
  os << "Node Name: " << options.node_name << '\n'
     << "Evaluation time: " << options.eval_time << "s\n"
     << "Log output: "
     << (options.log_dir.empty() ? "disabled" : options.log_dir) << '\n';
  return os;
}

}  // namespace benchmark_options