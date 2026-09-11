#include "benchmark_options/cli_options.hpp"

#include <cstdlib>
#include <iostream>
#include <unordered_set>
#include <vector>

#include "cxxopts.hpp"
#include "message_registry.hpp"

namespace benchmark_options {

Options::Options()
    : eval_time(60),
      qos_history("KEEP_LAST"),
      qos_depth(1),
      qos_reliability("RELIABLE") {}

Options::Options(int argc, char** argv) : Options() { parse(argc, argv); }

void Options::parse(int argc, char** argv) {
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
      "msg-types-pub", "Message types for publisher topics (repeatable)",
      cxxopts::value<std::vector<std::string>>(msg_types_pub))(
      "msg-types-sub", "Message types for subscriber topics (repeatable)",
      cxxopts::value<std::vector<std::string>>(msg_types_sub))(
      "msg-sizes-pub", "Message sizes in bytes for publisher topics",
      cxxopts::value<std::vector<int>>(msg_sizes_pub), "bytes")(
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
              << "    --msg-types-pub stamped_vector --msg-sizes-pub 64 \\\n"
              << "    --topic-names-sub input --msg-types-sub stamped_vector \\\n"
              << "    --period 100\n";
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
    if (qos_history != "KEEP_LAST" && qos_history != "KEEP_ALL") {
      std::cout << "Error: --qos-history must be KEEP_LAST or KEEP_ALL.\n\n";
      print_help();
      std::exit(1);
    }
    if (qos_depth <= 0) {
      std::cout << "Error: --qos-depth must be positive.\n\n";
      print_help();
      std::exit(1);
    }
    if (qos_reliability != "RELIABLE" &&
        qos_reliability != "BEST_EFFORT") {
      std::cout << "Error: --qos-reliability must be RELIABLE or BEST_EFFORT.\n\n";
      print_help();
      std::exit(1);
    }

    auto validate_unique_topics = [&print_help](
                                      const std::vector<std::string>& topics,
                                      const char* role) {
      std::unordered_set<std::string> unique_topics;
      for (const auto& topic : topics) {
        if (!unique_topics.insert(topic).second) {
          std::cout << "Error: duplicate " << role << " topic: " << topic
                    << ".\n\n";
          print_help();
          std::exit(1);
        }
      }
    };
    validate_unique_topics(topic_names_pub, "publisher");
    validate_unique_topics(topic_names_sub, "subscriber");

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
    if (!msg_sizes_pub.empty() && topic_names_pub.empty()) {
      std::cout << "Error: --msg-sizes-pub requires --topic-names-pub.\n\n";
      print_help();
      std::exit(1);
    }
    if (!period_ms.empty() && topic_names_pub.empty()) {
      std::cout << "Error: --period requires --topic-names-pub.\n\n";
      print_help();
      std::exit(1);
    }

    if (msg_types_pub.size() != topic_names_pub.size()) {
      std::cout << "Error: --msg-types-pub must match the number of "
                   "--topic-names-pub entries.\n\n";
      print_help();
      std::exit(1);
    }
    if (msg_types_sub.size() != topic_names_sub.size()) {
      std::cout << "Error: --msg-types-sub must match the number of "
                   "--topic-names-sub entries.\n\n";
      print_help();
      std::exit(1);
    }
    if (msg_sizes_pub.empty()) {
      msg_sizes_pub.assign(topic_names_pub.size(), 0);
    } else if (msg_sizes_pub.size() != topic_names_pub.size()) {
      std::cout << "Error: --msg-sizes-pub must match the number of "
                   "--topic-names-pub entries.\n\n";
      print_help();
      std::exit(1);
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
    auto validate_message_type = [&print_help](const std::string& msg_type,
                          int msg_size,
                          bool requires_msg_size,
                          const char* role) {
      bool supported = false;
      bool variable_size = false;
#define FIND_MESSAGE_TYPE(topology_name, ros_name, is_variable, fixed_size) \
      if (msg_type == #topology_name) {                                    \
        supported = true;                                                   \
        variable_size = is_variable;                                        \
      }
      ROS2_PERF_FOR_EACH_MESSAGE_TYPE(FIND_MESSAGE_TYPE)
#undef FIND_MESSAGE_TYPE
      if (!supported) {
        std::cout << "Error: unsupported " << role << " message type: "
                  << msg_type << ".\n\n";
        print_help();
        std::exit(1);
      }
      if (requires_msg_size && variable_size && msg_size <= 0) {
        std::cout << "Error: variable-length " << role
                  << " messages require a positive --msg-sizes-pub value.\n\n";
        print_help();
        std::exit(1);
      }
      if (requires_msg_size && !variable_size && msg_size != 0) {
        std::cout << "Error: --msg-sizes-pub is valid only for variable-length "
                  << role << " messages.\n\n";
        print_help();
        std::exit(1);
      }
    };
    for (size_t index = 0; index < msg_types_pub.size(); ++index) {
      validate_message_type(msg_types_pub[index], msg_sizes_pub[index], true,
                            "publisher");
    }
    for (const auto& msg_type : msg_types_sub) {
      validate_message_type(msg_type, 0, false, "subscriber");
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