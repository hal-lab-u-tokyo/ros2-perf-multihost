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
#include "ros2_perf_multihost_nodes/msg/int_message.hpp"

struct PublishLog {
  uint32_t message_idx;
  rclcpp::Time time_stamp;
};

struct SubscribeLog {
  std::string pub_node_name;
  uint32_t message_idx;
  rclcpp::Time time_stamp;
};

using Message = ros2_perf_multihost_nodes::msg::IntMessage;

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
      publishers_.emplace(
          topic_name, create_publisher<Message>(topic_name, qos));

      const int payload_size = options_.payload_size[index];
      const int period_ms = options_.period_ms[index];
      timers_.emplace(
          topic_name,
          create_wall_timer(std::chrono::milliseconds(period_ms),
                            [this, topic_name, payload_size]() {
                              publish_message(topic_name, payload_size);
                            }));
    }

    for (const auto& topic_name : options_.topic_names_sub) {
      const auto start_time = get_clock()->now();
      subscribe_start_times_.emplace(topic_name, start_time);
      subscribe_end_times_.emplace(
          topic_name,
          start_time + rclcpp::Duration::from_seconds(options_.eval_time));
      subscribers_.emplace(
          topic_name,
          create_subscription<Message>(
              topic_name, qos,
              [this, topic_name](const Message::SharedPtr message) {
                record_received_message(topic_name, *message);
              }));
    }

    shutdown_timer_ = create_wall_timer(
        std::chrono::seconds(options_.eval_time + 10), []() {
          rclcpp::shutdown();
        });
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
    file << "\nPayloadSize: ";
    write_csv(file, options_.payload_size);
    file << "\nPeriod: ";
    write_csv(file, options_.period_ms);
    file << "\nTopics(Sub): ";
    write_csv(file, options_.topic_names_sub);
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

  void publish_message(const std::string& topic_name, int payload_size) {
    const auto now = get_clock()->now();
    if (now >= publish_end_times_.at(topic_name)) {
      timers_.at(topic_name)->cancel();
      return;
    }
    auto message = std::make_unique<Message>();
    message->data.assign(payload_size, 0);
    message->header.stamp.sec = static_cast<int32_t>(
        (now - publish_start_times_.at(topic_name)).seconds());
    message->header.stamp.nanosec = static_cast<uint32_t>(
        (now - publish_start_times_.at(topic_name)).nanoseconds() %
        1000000000);
    message->header.pub_idx = publish_indices_.at(topic_name);
    message->header.node_name = options_.node_name;
    publish_logs_[topic_name].push_back({message->header.pub_idx, now});
    publishers_.at(topic_name)->publish(std::move(message));
    ++publish_indices_.at(topic_name);
  }

  void record_received_message(const std::string& topic_name,
                               const Message& message) {
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
           << "\nEndTime: "
           << subscribe_end_times_.at(topic_name).nanoseconds() << '\n';
      for (const auto& log : logs) {
        file << "Pub Node_Name: " << log.pub_node_name
             << ", Index: " << log.message_idx
             << ", Timestamp: " << log.time_stamp.nanoseconds() << '\n';
      }
    }
  }

  benchmark_options::Options options_;
  std::string log_dir_;
  std::unordered_map<std::string, rclcpp::Publisher<Message>::SharedPtr>
      publishers_;
  std::unordered_map<std::string, rclcpp::Subscription<Message>::SharedPtr>
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