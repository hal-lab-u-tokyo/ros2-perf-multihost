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
#include <unordered_map>
#include <utility>
#include <vector>

#include "benchmark_options/cli_options.hpp"
#include "message_registry.hpp"

struct PublishLog {
  uint32_t message_idx;
  rclcpp::Time time_stamp;
};

struct SubscribeLog {
  std::string pub_node_name;
  uint32_t message_idx;
  rclcpp::Time time_stamp;
};

static benchmark_options::Options parse_options(int argc, char** argv) {
  auto non_ros_args = rclcpp::remove_ros_arguments(argc, argv);
  std::vector<char*> non_ros_args_c_strings;
  for (auto& argument : non_ros_args) {
    non_ros_args_c_strings.push_back(argument.data());
  }
  return benchmark_options::Options(static_cast<int>(non_ros_args_c_strings.size()),
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
      publish_end_times_.emplace(topic_name,
                                 start_time + rclcpp::Duration::from_seconds(options_.eval_time));
      publish_indices_.emplace(topic_name, 0);
      publish_logs_.try_emplace(topic_name);
      const int period_ms = options_.period_ms[index];
      configure_publisher(topic_name, options_.msg_types_pub[index], options_.msg_sizes_pub[index],
                          options_.msg_pass_by_pub[index], period_ms, qos);
    }

    for (size_t index = 0; index < options_.topic_names_sub.size(); ++index) {
      const auto& topic_name = options_.topic_names_sub[index];
      const auto start_time = get_clock()->now();
      subscribe_start_times_.emplace(topic_name, start_time);
      subscribe_logs_.try_emplace(topic_name);
      subscribe_end_times_.emplace(topic_name,
                                   start_time + rclcpp::Duration::from_seconds(options_.eval_time));
      configure_subscription(topic_name, options_.msg_types_sub[index],
                             options_.msg_pass_by_sub[index], qos);
    }

    shutdown_timer_ = create_wall_timer(std::chrono::seconds(options_.eval_time + 10),
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
    file << "\nMsgPassBy(Pub): ";
    write_csv(file, options_.msg_pass_by_pub);
    file << "\nPayloadSize: ";
    for (size_t index = 0; index < options_.msg_types_pub.size(); ++index) {
      file << payload_size(options_.msg_types_pub[index], options_.msg_sizes_pub[index]) << ',';
    }
    file << "\nPeriod: ";
    write_csv(file, options_.period_ms);
    file << "\nTopics(Sub): ";
    write_csv(file, options_.topic_names_sub);
    file << "\nMsgTypes(Sub): ";
    write_csv(file, options_.msg_types_sub);
    file << "\nMsgPassBy(Sub): ";
    write_csv(file, options_.msg_pass_by_sub);
    file << '\n';
  }

  template <typename ValueType>
  static void write_csv(std::ostream& stream, const std::vector<ValueType>& values) {
    for (const auto& value : values) {
      stream << value << ',';
    }
  }

  std::filesystem::path log_directory() const {
    return std::filesystem::path(log_dir_) / (options_.node_name + "_log");
  }

  static int payload_size(const std::string& msg_type, int msg_size) {
#define GET_PAYLOAD_SIZE(topology_name, ros_name, variable_size, element_size, fixed_size) \
  if (msg_type == #topology_name) {                                                        \
    return variable_size ? msg_size : fixed_size;                                          \
  }
    ROS2_PERF_FOR_EACH_MESSAGE_TYPE(GET_PAYLOAD_SIZE)
#undef GET_PAYLOAD_SIZE
    return 0;
  }

  template <typename MessageType, bool VariableSize>
  void configure_publisher(const std::string& topic_name, int msg_size,
                           const std::string& msg_pass_by, int period_ms, const rclcpp::QoS& qos) {
    publishers_.emplace(topic_name, create_publisher<MessageType>(topic_name, qos));
    timers_.emplace(topic_name, create_wall_timer(std::chrono::milliseconds(period_ms),
                                                  [this, topic_name, msg_size, msg_pass_by]() {
                                                    publish_message<MessageType, VariableSize>(
                                                        topic_name, msg_size, msg_pass_by);
                                                  }));
  }

  void configure_publisher(const std::string& topic_name, const std::string& msg_type, int msg_size,
                           const std::string& msg_pass_by, int period_ms, const rclcpp::QoS& qos) {
#define CONFIGURE_PUBLISHER(topology_name, ros_name, variable_size, element_size, fixed_size) \
  if (msg_type == #topology_name) {                                                           \
    configure_publisher<ros2_perf_multihost_nodes::msg::ros_name, variable_size>(             \
        topic_name, msg_size / element_size, msg_pass_by, period_ms, qos);                    \
    return;                                                                                   \
  }
    ROS2_PERF_FOR_EACH_MESSAGE_TYPE(CONFIGURE_PUBLISHER)
#undef CONFIGURE_PUBLISHER
  }

  template <typename MessageType>
  void configure_subscription(const std::string& topic_name, const std::string& msg_pass_by,
                              const rclcpp::QoS& qos) {
    if (msg_pass_by == "const_shared_ptr_with_info") {
      subscribers_.emplace(
          topic_name, create_subscription<MessageType>(
                          topic_name, qos,
                          [this, topic_name](const typename MessageType::ConstSharedPtr message,
                                             const rclcpp::MessageInfo&) {
                            record_received_message(topic_name, *message);
                          }));
      return;
    }
    subscribers_.emplace(
        topic_name, create_subscription<MessageType>(
                        topic_name, qos,
                        [this, topic_name](const typename MessageType::ConstSharedPtr message) {
                          record_received_message(topic_name, *message);
                        }));
  }

  void configure_subscription(const std::string& topic_name, const std::string& msg_type,
                              const std::string& msg_pass_by, const rclcpp::QoS& qos) {
#define CONFIGURE_SUBSCRIPTION(topology_name, ros_name, variable_size, element_size, fixed_size) \
  if (msg_type == #topology_name) {                                                              \
    configure_subscription<ros2_perf_multihost_nodes::msg::ros_name>(topic_name, msg_pass_by,    \
                                                                     qos);                       \
    return;                                                                                      \
  }
    ROS2_PERF_FOR_EACH_MESSAGE_TYPE(CONFIGURE_SUBSCRIPTION)
#undef CONFIGURE_SUBSCRIPTION
  }

  template <typename MessageType, bool VariableSize>
  void publish_message(const std::string& topic_name, int msg_size,
                       const std::string& msg_pass_by) {
    const auto now = get_clock()->now();
    if (now >= publish_end_times_.at(topic_name)) {
      timers_.at(topic_name)->cancel();
      return;
    }
    auto initialize_message = [this, &topic_name, msg_size, &now](MessageType& message) {
      if constexpr (VariableSize) {
        message.data.assign(msg_size, 0);
      }
      message.header.stamp.sec =
          static_cast<int32_t>((now - publish_start_times_.at(topic_name)).seconds());
      message.header.stamp.nanosec = static_cast<uint32_t>(
          (now - publish_start_times_.at(topic_name)).nanoseconds() % 1000000000);
      message.header.pub_idx = publish_indices_.at(topic_name);
      message.header.node_name = options_.node_name;
    };
    const auto publisher =
        std::static_pointer_cast<rclcpp::Publisher<MessageType>>(publishers_.at(topic_name));
    if (msg_pass_by == "unique_ptr") {
      auto message = std::make_unique<MessageType>();
      initialize_message(*message);
      publish_logs_[topic_name].push_back({message->header.pub_idx, now});
      publisher->publish(std::move(message));
    } else {
      MessageType message;
      initialize_message(message);
      publish_logs_[topic_name].push_back({message.header.pub_idx, now});
      publisher->publish(message);
    }
    ++publish_indices_.at(topic_name);
  }

  template <typename MessageType>
  void record_received_message(const std::string& topic_name, const MessageType& message) {
    const auto now = get_clock()->now();
    if (now >= subscribe_end_times_.at(topic_name)) {
      return;
    }
    subscribe_logs_[topic_name].push_back({message.header.node_name, message.header.pub_idx, now});
  }

  void write_publish_logs() const {
    if (log_dir_.empty()) {
      return;
    }
    for (const auto& [topic_name, logs] : publish_logs_) {
      std::ofstream file(log_directory() / (topic_name + "_pub_log.txt"), std::ios::trunc);
      file << "StartTime: " << publish_start_times_.at(topic_name).nanoseconds()
           << "\nEndTime: " << publish_end_times_.at(topic_name).nanoseconds() << '\n';
      for (const auto& log : logs) {
        file << "Index: " << log.message_idx << ", Timestamp: " << log.time_stamp.nanoseconds()
             << '\n';
      }
    }
  }

  void write_subscribe_logs() const {
    if (log_dir_.empty()) {
      return;
    }
    for (const auto& [topic_name, logs] : subscribe_logs_) {
      std::ofstream file(log_directory() / (topic_name + "_sub_log.txt"), std::ios::trunc);
      file << "StartTime: " << subscribe_start_times_.at(topic_name).nanoseconds()
           << "\nEndTime: " << subscribe_end_times_.at(topic_name).nanoseconds() << '\n';
      for (const auto& log : logs) {
        file << "Pub Node_Name: " << log.pub_node_name << ", Index: " << log.message_idx
             << ", Timestamp: " << log.time_stamp.nanoseconds() << '\n';
      }
    }
  }

  benchmark_options::Options options_;
  std::string log_dir_;
  std::unordered_map<std::string, rclcpp::PublisherBase::SharedPtr> publishers_;
  std::unordered_map<std::string, rclcpp::SubscriptionBase::SharedPtr> subscribers_;
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
