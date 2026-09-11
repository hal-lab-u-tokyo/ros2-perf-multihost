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
      qos_reliability("RELIABLE"),
      qos_override(false) {}

Options::Options(int argc, char** argv) : Options() { parse(argc, argv); }

void Options::parse(int argc, char** argv) {
  constexpr int kDefaultPeriodMs = 100;

  cxxopts::Options options("ros2 run ros2_perf_multihost_nodes benchmark_node",
                           "ROS 2 performance benchmark node options.");
  options.custom_help("[OPTIONS]");
  options.add_options()("h,help", "Show this help message and exit")(
      "node-name", "Node name (required)", cxxopts::value<std::string>(node_name))(
      "topic-names-pub", "Publisher topic names (repeatable)",
      cxxopts::value<std::vector<std::string>>(topic_names_pub))(
      "topic-names-sub", "Subscriber topic names (repeatable)",
      cxxopts::value<std::vector<std::string>>(topic_names_sub))(
      "msg-types-pub", "Message types for publisher topics (repeatable)",
      cxxopts::value<std::vector<std::string>>(msg_types_pub))(
      "msg-types-sub", "Message types for subscriber topics (repeatable)",
      cxxopts::value<std::vector<std::string>>(msg_types_sub))(
      "msg-sizes-pub", "Message sizes in bytes for publisher topics",
      cxxopts::value<std::vector<int>>(msg_sizes_pub),
      "bytes")("msg-pass-by-pub", "Publisher message passing modes (repeatable)",
               cxxopts::value<std::vector<std::string>>(msg_pass_by_pub))(
      "msg-pass-by-sub", "Subscriber message passing modes (repeatable)",
      cxxopts::value<std::vector<std::string>>(msg_pass_by_sub))(
      "p,period", "Publish period in milliseconds for publisher topics",
      cxxopts::value<std::vector<int>>(period_ms),
      "ms")("eval-time", "Evaluation duration in seconds",
            cxxopts::value<int>(eval_time)->default_value("60"), "sec")(
      "log-dir", "Directory to write logs and metadata", cxxopts::value<std::string>(log_dir))(
      "qos-history-pub", "QoS history per publisher topic",
      cxxopts::value<std::vector<std::string>>(qos_history_pub))(
      "qos-history-sub", "QoS history per subscriber topic",
      cxxopts::value<std::vector<std::string>>(qos_history_sub))(
      "qos-depth-pub", "QoS depth per publisher topic",
      cxxopts::value<std::vector<int>>(qos_depth_pub))(
      "qos-depth-sub", "QoS depth per subscriber topic",
      cxxopts::value<std::vector<int>>(qos_depth_sub))(
      "qos-reliability-pub", "QoS reliability per publisher topic",
      cxxopts::value<std::vector<std::string>>(qos_reliability_pub))(
      "qos-reliability-sub", "QoS reliability per subscriber topic",
      cxxopts::value<std::vector<std::string>>(qos_reliability_sub))(
      "qos-source-pub", "QoS source per publisher topic",
      cxxopts::value<std::vector<std::string>>(qos_source_pub))(
      "qos-source-sub", "QoS source per subscriber topic",
      cxxopts::value<std::vector<std::string>>(qos_source_sub))(
      "qos-history", "QoS history policy: KEEP_LAST or KEEP_ALL",
      cxxopts::value<std::string>(qos_history)->default_value("KEEP_LAST"))(
      "qos-depth", "QoS depth when qos_history=KEEP_LAST",
      cxxopts::value<int>(qos_depth)->default_value("1"))(
      "qos-reliability", "QoS reliability: RELIABLE or BEST_EFFORT",
      cxxopts::value<std::string>(qos_reliability)->default_value("RELIABLE"))(
      "qos-override", "Apply global QoS options to every endpoint",
      cxxopts::value<bool>(qos_override)->default_value("false")->implicit_value("true"));

  auto print_help = [&options]() {
    std::cout << "Node role:\n"
              << "  Benchmark: periodically publishes on --topic-names-pub "
                 "and records messages received on --topic-names-sub.\n\n"
              << options.help() << "\nExample:\n"
              << "  ros2 run ros2_perf_multihost_nodes benchmark_node \\\n"
              << "    --node-name node1 --topic-names-pub output \\\n"
              << "    --msg-types-pub stamped_vector --msg-sizes-pub 64 \\\n"
              << "    --msg-pass-by-pub unique_ptr \\\n"
              << "    --topic-names-sub input --msg-types-sub stamped_vector \\\n"
              << "    --msg-pass-by-sub const_shared_ptr_with_info \\\n"
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
    if (qos_reliability != "RELIABLE" && qos_reliability != "BEST_EFFORT") {
      std::cout << "Error: --qos-reliability must be RELIABLE or BEST_EFFORT.\n\n";
      print_help();
      std::exit(1);
    }

    auto validate_unique_topics = [&print_help](const std::vector<std::string>& topics,
                                                const char* role) {
      std::unordered_set<std::string> unique_topics;
      for (const auto& topic : topics) {
        if (!unique_topics.insert(topic).second) {
          std::cout << "Error: duplicate " << role << " topic: " << topic << ".\n\n";
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
          std::cout << "Error: publisher and subscriber topics must not overlap: "
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
    if (msg_pass_by_pub.empty()) {
      msg_pass_by_pub.assign(topic_names_pub.size(), "const_ref");
    } else if (msg_pass_by_pub.size() != topic_names_pub.size()) {
      std::cout << "Error: --msg-pass-by-pub must match the number of "
                   "--topic-names-pub entries.\n\n";
      print_help();
      std::exit(1);
    }
    for (const auto& msg_pass_by : msg_pass_by_pub) {
      if (msg_pass_by != "const_ref" && msg_pass_by != "unique_ptr") {
        std::cout << "Error: --msg-pass-by-pub must be const_ref or "
                     "unique_ptr.\n\n";
        print_help();
        std::exit(1);
      }
    }
    if (msg_pass_by_sub.empty()) {
      msg_pass_by_sub.assign(topic_names_sub.size(), "const_shared_ptr");
    } else if (msg_pass_by_sub.size() != topic_names_sub.size()) {
      std::cout << "Error: --msg-pass-by-sub must match the number of "
                   "--topic-names-sub entries.\n\n";
      print_help();
      std::exit(1);
    }
    for (const auto& msg_pass_by : msg_pass_by_sub) {
      if (msg_pass_by != "const_shared_ptr" && msg_pass_by != "const_shared_ptr_with_info") {
        std::cout << "Error: --msg-pass-by-sub must be const_shared_ptr or "
                     "const_shared_ptr_with_info.\n\n";
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
    auto validate_qos_vectors = [&print_help](std::vector<std::string>& histories,
                                               std::vector<int>& depths,
                                               std::vector<std::string>& reliabilities,
                                               size_t endpoint_count, const char* role) {
      if (histories.empty()) {
        histories.assign(endpoint_count, "KEEP_LAST");
      }
      if (depths.empty()) {
        depths.assign(endpoint_count, 1);
      }
      if (reliabilities.empty()) {
        reliabilities.assign(endpoint_count, "RELIABLE");
      }
      if (histories.size() != endpoint_count || depths.size() != endpoint_count ||
          reliabilities.size() != endpoint_count) {
        std::cout << "Error: per-" << role
                  << " QoS options must match the number of topic entries.\n\n";
        print_help();
        std::exit(1);
      }
      for (const auto& history : histories) {
        if (history != "KEEP_LAST" && history != "KEEP_ALL") {
          std::cout << "Error: per-" << role
                    << " QoS history must be KEEP_LAST or KEEP_ALL.\n\n";
          print_help();
          std::exit(1);
        }
      }
      for (const int depth : depths) {
        if (depth <= 0) {
          std::cout << "Error: per-" << role << " QoS depth must be positive.\n\n";
          print_help();
          std::exit(1);
        }
      }
      for (const auto& reliability : reliabilities) {
        if (reliability != "RELIABLE" && reliability != "BEST_EFFORT") {
          std::cout << "Error: per-" << role
                    << " QoS reliability must be RELIABLE or BEST_EFFORT.\n\n";
          print_help();
          std::exit(1);
        }
      }
    };
    validate_qos_vectors(qos_history_pub, qos_depth_pub, qos_reliability_pub,
                         topic_names_pub.size(), "publisher");
    validate_qos_vectors(qos_history_sub, qos_depth_sub, qos_reliability_sub,
                         topic_names_sub.size(), "subscriber");
    if (qos_source_pub.empty()) {
      qos_source_pub.assign(topic_names_pub.size(), "root_default");
    }
    if (qos_source_sub.empty()) {
      qos_source_sub.assign(topic_names_sub.size(), "root_default");
    }
    if (qos_source_pub.size() != topic_names_pub.size() ||
        qos_source_sub.size() != topic_names_sub.size()) {
      std::cout << "Error: per-endpoint QoS source options must match topic entries.\n\n";
      print_help();
      std::exit(1);
    }
    if (qos_override) {
      qos_history_pub.assign(topic_names_pub.size(), qos_history);
      qos_depth_pub.assign(topic_names_pub.size(), qos_depth);
      qos_reliability_pub.assign(topic_names_pub.size(), qos_reliability);
      qos_history_sub.assign(topic_names_sub.size(), qos_history);
      qos_depth_sub.assign(topic_names_sub.size(), qos_depth);
      qos_reliability_sub.assign(topic_names_sub.size(), qos_reliability);
      qos_source_pub.assign(topic_names_pub.size(), "sweep");
      qos_source_sub.assign(topic_names_sub.size(), "sweep");
    }
    auto validate_message_type = [&print_help](const std::string& msg_type, int msg_size,
                                               bool requires_msg_size, const char* role) {
      bool supported = false;
      bool variable_size = false;
#define FIND_MESSAGE_TYPE(topology_name, ros_name, is_variable, element_size, fixed_size)    \
  if (msg_type == #topology_name) {                                                          \
    supported = true;                                                                        \
    variable_size = is_variable;                                                             \
    if (requires_msg_size && is_variable && msg_size % element_size != 0) {                  \
      std::cout << "Error: --msg-sizes-pub must be divisible by " << element_size << " for " \
                << msg_type << ".\n\n";                                                      \
      print_help();                                                                          \
      std::exit(1);                                                                          \
    }                                                                                        \
  }
      ROS2_PERF_FOR_EACH_MESSAGE_TYPE(FIND_MESSAGE_TYPE)
#undef FIND_MESSAGE_TYPE
      if (!supported) {
        std::cout << "Error: unsupported " << role << " message type: " << msg_type << ".\n\n";
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
        std::cout << "Error: --msg-sizes-pub is valid only for variable-length " << role
                  << " messages.\n\n";
        print_help();
        std::exit(1);
      }
    };
    for (size_t index = 0; index < msg_types_pub.size(); ++index) {
      validate_message_type(msg_types_pub[index], msg_sizes_pub[index], true, "publisher");
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
     << "Log output: " << (options.log_dir.empty() ? "disabled" : options.log_dir) << '\n';
  return os;
}

}  // namespace benchmark_options
