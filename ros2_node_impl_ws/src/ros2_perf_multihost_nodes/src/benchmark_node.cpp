#include <chrono>
#include <csignal>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <rclcpp/rclcpp.hpp>
#include <sstream>
#include <string>
#include <stdexcept>
#include <type_traits>
#include <unordered_map>
#include <utility>
#include <vector>

#include "benchmark_options/cli_options.hpp"
#include "ros2_perf_multihost_nodes/msg/stamped12_float32.hpp"
#include "ros2_perf_multihost_nodes/msg/stamped3_float32.hpp"
#include "ros2_perf_multihost_nodes/msg/stamped4_float32.hpp"
#include "ros2_perf_multihost_nodes/msg/stamped4_int32.hpp"
#include "ros2_perf_multihost_nodes/msg/stamped9_float32.hpp"
#include "ros2_perf_multihost_nodes/msg/stamped_int64.hpp"
#include "ros2_perf_multihost_nodes/msg/stamped_vector.hpp"

struct PublishLog {
  uint32_t message_idx;
  rclcpp::Time time_stamp;
};

struct SubscribeLog {
  std::string pub_node_name;
  uint32_t message_idx;
  rclcpp::Time time_stamp;
};

using Stamped3Float32 = ros2_perf_multihost_nodes::msg::Stamped3Float32;
using Stamped4Float32 = ros2_perf_multihost_nodes::msg::Stamped4Float32;
using Stamped4Int32 = ros2_perf_multihost_nodes::msg::Stamped4Int32;
using Stamped9Float32 = ros2_perf_multihost_nodes::msg::Stamped9Float32;
using Stamped12Float32 = ros2_perf_multihost_nodes::msg::Stamped12Float32;
using StampedInt64 = ros2_perf_multihost_nodes::msg::StampedInt64;
using StampedVector = ros2_perf_multihost_nodes::msg::StampedVector;

static benchmark_options::Options parse_options(int argc, char** argv) {
  auto non_ros_args = rclcpp::remove_ros_arguments(argc, argv);
  std::vector<char*> non_ros_args_c_strings;
  for (auto& argument : non_ros_args) {
    non_ros_args_c_strings.push_back(argument.data());
  }
  return benchmark_options::Options(
      static_cast<int>(non_ros_args_c_strings.size()),
      non_ros_args_c_strings.data());
}

class BenchmarkNode : public rclcpp::Node {
 public:
  explicit BenchmarkNode(const benchmark_options::Options& options)
      : Node(options.node_name), options_(options), log_dir_(options.log_dir) {
    create_result_directory();
    create_metadata_file();
    const auto qos = create_qos();

    for (size_t index = 0; index < options_.topic_names_pub.size(); ++index) {
      const auto& topic_name = options_.topic_names_pub[index];
      const auto start_time = get_clock()->now();
      publish_start_times_.emplace(topic_name, start_time);
      publish_end_times_.emplace(
          topic_name,
          start_time + rclcpp::Duration::from_seconds(options_.eval_time));
      publish_indices_.emplace(topic_name, 0);
      publish_logs_.try_emplace(topic_name);
      const int period_ms = options_.period_ms[index];
      configure_publisher(topic_name, options_.msg_types_pub[index],
                          options_.msg_sizes_pub[index], period_ms, qos);
    }

    for (size_t index = 0; index < options_.topic_names_sub.size(); ++index) {
      const auto& topic_name = options_.topic_names_sub[index];
      const auto start_time = get_clock()->now();
      subscribe_start_times_.emplace(topic_name, start_time);
      subscribe_logs_.try_emplace(topic_name);
      subscribe_end_times_.emplace(
          topic_name,
          start_time + rclcpp::Duration::from_seconds(options_.eval_time));
      configure_subscription(topic_name, options_.msg_types_sub[index], qos);
    }

    shutdown_timer_ =
        create_wall_timer(std::chrono::seconds(options_.eval_time + 10),
                          []() { rclcpp::shutdown(); });
  }

  ~BenchmarkNode() override {
    write_publish_logs();
    write_subscribe_logs();
  }

 private:
  rclcpp::QoS create_qos() const {
    auto qos = rclcpp::QoS(rclcpp::KeepLast(1));
    if (options_.qos_history == "KEEP_ALL") {
      qos.keep_all();
    } else {
      qos.keep_last(options_.qos_depth);
    }
    if (options_.qos_reliability == "BEST_EFFORT") {
      qos.best_effort();
    }
    return qos;
  }

  void create_result_directory() const {
    if (!log_dir_.empty()) {
      std::filesystem::create_directories(log_directory());
    }
  }

  void create_metadata_file() const {
    if (log_dir_.empty()) {
      return;
    }
    std::ofstream file(log_directory() / "metadata.txt", std::ios::trunc);
    if (!file.is_open()) {
      RCLCPP_ERROR(get_logger(), "Failed to create metadata file.");
      return;
    }
    file << "Name: " << options_.node_name << "\n"
         << "NodeType: Benchmark\n"
         << "Topics(Pub): ";
    write_csv(file, options_.topic_names_pub);
    file << "\nMsgTypes(Pub): ";
    write_csv(file, options_.msg_types_pub);
    file << "\nMsgSizes(Pub): ";
    write_csv(file, options_.msg_sizes_pub);
    file << "\nPayloadSize: ";
    for (size_t index = 0; index < options_.msg_types_pub.size(); ++index) {
      file << payload_size(options_.msg_types_pub[index],
                           options_.msg_sizes_pub[index])
           << ',';
    }
    file << "\nPeriod: ";
    write_csv(file, options_.period_ms);
    file << "\nTopics(Sub): ";
    write_csv(file, options_.topic_names_sub);
    file << "\nMsgTypes(Sub): ";
    write_csv(file, options_.msg_types_sub);
    file << '\n';
  }

  template <typename ValueType>
  static void write_csv(std::ostream& stream,
                        const std::vector<ValueType>& values) {
    for (const auto& value : values) {
      stream << value << ',';
    }
  }

  std::filesystem::path log_directory() const {
    return std::filesystem::path(log_dir_) / (options_.node_name + "_log");
  }

  static int payload_size(const std::string& msg_type, int msg_size) {
    if (msg_type == "stamped3_float32") return 3 * 4;
    if (msg_type == "stamped4_float32" || msg_type == "stamped4_int32") return 4 * 4;
    if (msg_type == "stamped9_float32") return 9 * 4;
    if (msg_type == "stamped12_float32") return 12 * 4;
    if (msg_type == "stamped_int64") return 8;
    return msg_size;
  }

  template <typename MessageType>
  void configure_publisher(const std::string& topic_name, int msg_size,
                           int period_ms, const rclcpp::QoS& qos) {
    publishers_.emplace(topic_name, create_publisher<MessageType>(topic_name, qos));
    timers_.emplace(topic_name,
                    create_wall_timer(std::chrono::milliseconds(period_ms),
                                      [this, topic_name, msg_size]() {
                                        publish_message<MessageType>(topic_name,
                                                                     msg_size);
                                      }));
  }

  void configure_publisher(const std::string& topic_name,
                           const std::string& msg_type, int msg_size,
                           int period_ms, const rclcpp::QoS& qos) {
    if (msg_type == "stamped3_float32") {
      configure_publisher<Stamped3Float32>(topic_name, msg_size, period_ms, qos);
    } else if (msg_type == "stamped4_float32") {
      configure_publisher<Stamped4Float32>(topic_name, msg_size, period_ms, qos);
    } else if (msg_type == "stamped4_int32") {
      configure_publisher<Stamped4Int32>(topic_name, msg_size, period_ms, qos);
    } else if (msg_type == "stamped9_float32") {
      configure_publisher<Stamped9Float32>(topic_name, msg_size, period_ms, qos);
    } else if (msg_type == "stamped12_float32") {
      configure_publisher<Stamped12Float32>(topic_name, msg_size, period_ms, qos);
    } else if (msg_type == "stamped_int64") {
      configure_publisher<StampedInt64>(topic_name, msg_size, period_ms, qos);
    } else if (msg_type == "stamped_vector") {
      configure_publisher<StampedVector>(topic_name, msg_size, period_ms, qos);
    } else {
      throw std::invalid_argument("Unsupported publisher message type: " + msg_type);
    }
  }

  template <typename MessageType>
  void configure_subscription(const std::string& topic_name,
                              const rclcpp::QoS& qos) {
    subscribers_.emplace(
        topic_name, create_subscription<MessageType>(
                        topic_name, qos,
                        [this, topic_name](const typename MessageType::SharedPtr message) {
                          record_received_message(topic_name, *message);
                        }));
  }

  void configure_subscription(const std::string& topic_name,
                              const std::string& msg_type,
                              const rclcpp::QoS& qos) {
    if (msg_type == "stamped3_float32") {
      configure_subscription<Stamped3Float32>(topic_name, qos);
    } else if (msg_type == "stamped4_float32") {
      configure_subscription<Stamped4Float32>(topic_name, qos);
    } else if (msg_type == "stamped4_int32") {
      configure_subscription<Stamped4Int32>(topic_name, qos);
    } else if (msg_type == "stamped9_float32") {
      configure_subscription<Stamped9Float32>(topic_name, qos);
    } else if (msg_type == "stamped12_float32") {
      configure_subscription<Stamped12Float32>(topic_name, qos);
    } else if (msg_type == "stamped_int64") {
      configure_subscription<StampedInt64>(topic_name, qos);
    } else if (msg_type == "stamped_vector") {
      configure_subscription<StampedVector>(topic_name, qos);
    } else {
      throw std::invalid_argument("Unsupported subscriber message type: " + msg_type);
    }
  }

  template <typename MessageType>
  void publish_message(const std::string& topic_name, int msg_size) {
    const auto now = get_clock()->now();
    if (now >= publish_end_times_.at(topic_name)) {
      timers_.at(topic_name)->cancel();
      return;
    }
    auto message = std::make_unique<MessageType>();
    if constexpr (std::is_same_v<MessageType, StampedVector>) {
      message->data.assign(msg_size, 0);
    }
    message->header.stamp.sec = static_cast<int32_t>(
        (now - publish_start_times_.at(topic_name)).seconds());
    message->header.stamp.nanosec = static_cast<uint32_t>(
        (now - publish_start_times_.at(topic_name)).nanoseconds() % 1000000000);
    message->header.pub_idx = publish_indices_.at(topic_name);
    message->header.node_name = options_.node_name;
    publish_logs_[topic_name].push_back({message->header.pub_idx, now});
    std::static_pointer_cast<rclcpp::Publisher<MessageType>>(
      publishers_.at(topic_name))->publish(std::move(message));
    ++publish_indices_.at(topic_name);
  }

  template <typename MessageType>
  void record_received_message(const std::string& topic_name,
                               const MessageType& message) {
    const auto now = get_clock()->now();
    if (now >= subscribe_end_times_.at(topic_name)) {
      return;
    }
    subscribe_logs_[topic_name].push_back(
        {message.header.node_name, message.header.pub_idx, now});
  }

  void write_publish_logs() const {
    if (log_dir_.empty()) {
      return;
    }
    for (const auto& [topic_name, logs] : publish_logs_) {
      std::ofstream file(log_directory() / (topic_name + "_pub_log.txt"),
                         std::ios::trunc);
      file << "StartTime: " << publish_start_times_.at(topic_name).nanoseconds()
           << "\nEndTime: " << publish_end_times_.at(topic_name).nanoseconds()
           << '\n';
      for (const auto& log : logs) {
        file << "Index: " << log.message_idx
             << ", Timestamp: " << log.time_stamp.nanoseconds() << '\n';
      }
    }
  }

  void write_subscribe_logs() const {
    if (log_dir_.empty()) {
      return;
    }
    for (const auto& [topic_name, logs] : subscribe_logs_) {
      std::ofstream file(log_directory() / (topic_name + "_sub_log.txt"),
                         std::ios::trunc);
      file << "StartTime: "
           << subscribe_start_times_.at(topic_name).nanoseconds()
           << "\nEndTime: " << subscribe_end_times_.at(topic_name).nanoseconds()
           << '\n';
      for (const auto& log : logs) {
        file << "Pub Node_Name: " << log.pub_node_name
             << ", Index: " << log.message_idx
             << ", Timestamp: " << log.time_stamp.nanoseconds() << '\n';
      }
    }
  }

  benchmark_options::Options options_;
  std::string log_dir_;
    std::unordered_map<std::string, rclcpp::PublisherBase::SharedPtr> publishers_;
    std::unordered_map<std::string, rclcpp::SubscriptionBase::SharedPtr>
      subscribers_;
  std::unordered_map<std::string, rclcpp::TimerBase::SharedPtr> timers_;
  rclcpp::TimerBase::SharedPtr shutdown_timer_;
  std::unordered_map<std::string, uint32_t> publish_indices_;
  std::unordered_map<std::string, rclcpp::Time> publish_start_times_;
  std::unordered_map<std::string, rclcpp::Time> publish_end_times_;
  std::unordered_map<std::string, rclcpp::Time> subscribe_start_times_;
  std::unordered_map<std::string, rclcpp::Time> subscribe_end_times_;
  std::map<std::string, std::vector<PublishLog>> publish_logs_;
  std::map<std::string, std::vector<SubscribeLog>> subscribe_logs_;
};

void sigint_handler(int) { rclcpp::shutdown(); }

int main(int argc, char* argv[]) {
  const auto options = parse_options(argc, argv);
  std::cout << options << "Start Benchmark Node!" << std::endl;
  setvbuf(stdout, nullptr, _IONBF, BUFSIZ);
  rclcpp::init(argc, argv);
  std::signal(SIGINT, sigint_handler);
  std::signal(SIGTERM, sigint_handler);
  rclcpp::spin(std::make_shared<BenchmarkNode>(options));
  rclcpp::shutdown();
  return 0;
}