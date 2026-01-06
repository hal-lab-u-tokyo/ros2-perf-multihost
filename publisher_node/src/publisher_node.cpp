#include <chrono>
#include <cstdio>
#include <memory>
#include <string>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <unordered_map>
#include <sstream>
#include <fstream>
#include <filesystem>
#include <cstdlib>
#include <csignal>

#include "node_options/cli_options.hpp"
#include "publisher_node/msg/performance_header.hpp"
#include "publisher_node/msg/int_message.hpp"

struct MessageLog {
  uint32_t message_idx;
  rclcpp::Time time_stamp;
};

static
node_options::Options
parse_options(int argc, char ** argv)
{
  auto non_ros_args = rclcpp::remove_ros_arguments(argc, argv);
  std::vector<char *> non_ros_args_c_strings;
  for (auto & arg : non_ros_args) {
    non_ros_args_c_strings.push_back(&arg.front());
  }
  int non_ros_argc = static_cast<int>(non_ros_args_c_strings.size());
  auto options = node_options::Options(non_ros_argc, non_ros_args_c_strings.data());

  return options;
}

static
void
create_result_directory(const node_options::Options & options)
{
  std::stringstream ss;
  ss << options.log_dir << "/" << options.node_name << "_log";
  const std::string result_dir_name = ss.str();
  std::filesystem::create_directories(result_dir_name);
  ss.str("");
  ss.clear();

  std::vector<std::string> log_file_paths;
  for (size_t i = 0; i < options.topic_names.size(); ++i) {
    ss << result_dir_name << "/" << options.topic_names[i] << "_log.txt";
    std::string log_file_path = ss.str();
    log_file_paths.push_back(log_file_path);
    ss.str("");
    ss.clear();
  }

  for (const auto& file_path : log_file_paths) {
    std::ofstream ofs(file_path);
    if(ofs){
      std::cout << "Log file created: " << file_path << std::endl;
      ofs.close();
    } else {
      std::cerr << "Failed to create: " << file_path << std::endl;
    }
  }
}

class Publisher : public rclcpp::Node
{
  public:
    explicit Publisher(const node_options::Options & options)
    : Node(options.node_name)
    {
      node_name = options.node_name;
      log_dir = options.log_dir;
      RCLCPP_INFO(this->get_logger(), "Publisher log_dir set to: %s", log_dir.c_str());
      create_metadata_file(options);
      RCLCPP_INFO(this->get_logger(), "Shutdown timer created with duration %d seconds", options.eval_time + 10);

      for (size_t i = 0; i < options.topic_names.size(); ++i) {
        const std::string & topic_name = options.topic_names[i];
        int payload_size = options.payload_size[i];
        int period_ms = options.period_ms[i];

        pub_idx_[topic_name] = 0;
        start_time_[topic_name] = this->get_clock()->now();
        end_time_[topic_name] = start_time_[topic_name] + rclcpp::Duration::from_seconds(options.eval_time) ;

        auto publish_message =
          [this, topic_name, payload_size, eval_time = options.eval_time, self_node = options.node_name]() -> void
          {
            // 購読者がいない間は送信しない
            // if (publishers_[topic_name]->get_subscription_count() == 0) {
            //   return;
            // }

            int current_pub_idx = pub_idx_[topic_name];

            auto message_ = std::make_shared<publisher_node::msg::IntMessage>();
            message_->data.resize(payload_size);
            std::fill(message_->data.begin(), message_->data.end(), 0);

            auto time_stamp = this->get_clock()->now();
            if((time_stamp.seconds() - start_time_[topic_name].seconds()) >= eval_time) {
              // RCLCPP_INFO(this->get_logger(), "Topic %s has reached the evaluation time.", topic_name.c_str());
              timers_[topic_name]->cancel();
              return;
            }

            message_->header.stamp.sec = static_cast<int32_t>(time_stamp.seconds() - start_time_[topic_name].seconds());
            message_->header.stamp.nanosec = static_cast<uint32_t>((time_stamp.nanoseconds() - start_time_[topic_name].nanoseconds()) % 1000000000);
            message_->header.pub_idx = current_pub_idx;
            message_->header.node_name = self_node;
            record_log(topic_name, current_pub_idx, time_stamp);

            std::ostringstream oss;
            for (const auto& byte : message_->data) {
              oss << std::hex << (int)byte << " ";
            }
            oss << std::dec <<"Time: " << std::fixed << std::setprecision(9) << static_cast<double>(time_stamp.nanoseconds() - start_time_[topic_name].nanoseconds()) / 1e9;

            // RCLCPP_INFO(this->get_logger(), "Publish/ Topic: %s, Data: %s, Index: %d", topic_name.c_str(), oss.str().c_str(), current_pub_idx);

            publishers_[topic_name]->publish(*message_);

            pub_idx_[topic_name]++;
        };

        rclcpp::QoS qos = rclcpp::QoS(rclcpp::KeepLast(1));

        if(options.qos_history == "KEEP_LAST") {
          int qos_keep_depth = options.qos_depth;
          qos.keep_last(qos_keep_depth);
        }
        else if (options.qos_history == "KEEP_ALL") {
          qos.keep_all();
        }

        if (options.qos_reliability == "BEST_EFFORT") {
          qos.best_effort();
        }

        print_qos_settings(qos);

        auto publisher = create_publisher<publisher_node::msg::IntMessage>(topic_name, qos);
        publishers_.emplace(topic_name, publisher);

        auto timer = create_wall_timer(std::chrono::milliseconds(period_ms), publish_message);
        timers_.emplace(topic_name, timer);

        auto shutdown_node =
          [this]() -> void
          {
            RCLCPP_INFO(this->get_logger(), "Shutting down node...");
            rclcpp::shutdown();
        };

        auto shutdown_timer = create_wall_timer(std::chrono::seconds(options.eval_time + 10), shutdown_node);
        shutdown_timers_.emplace(topic_name, shutdown_timer);
      }
    }

    ~Publisher() override {
      RCLCPP_INFO(this->get_logger(), "Node is shutting down.");
      write_all_logs(message_logs_);
    }

  private:
    std::unordered_map<std::string, rclcpp::Publisher<publisher_node::msg::IntMessage>::SharedPtr> publishers_;
    std::unordered_map<std::string, rclcpp::TimerBase::SharedPtr> timers_;
    std::unordered_map<std::string, rclcpp::TimerBase::SharedPtr> shutdown_timers_;
    std::unordered_map<std::string, uint32_t> pub_idx_;
    std::unordered_map<std::string, rclcpp::Time> start_time_;
    std::unordered_map<std::string, rclcpp::Time> end_time_;

    void
    create_metadata_file(const node_options::Options & options)
    {
      std::stringstream ss;
      ss << options.log_dir << "/" << options.node_name << "_log" <<  "/" << "metadata.txt" ;
      std::string metadata_file_path = ss.str();
      ss.str("");
      ss.clear();

      std::ofstream file(metadata_file_path, std::ios::out | std::ios::trunc);
      if (!file.is_open()) {
          RCLCPP_ERROR(this->get_logger(), "Failed to open file: %s", metadata_file_path.c_str());
          return;
      }

      file << "Name: " << options.node_name << "\n";
      file << "NodeType: " << "Publisher" << "\n";
      file << "Topics: ";
      for (const std::string& topic_name : options.topic_names) {
        file << topic_name << ",";
      }
      file << "\n";
      file << "PayloadSize: ";
      for (const int& payload_size : options.payload_size) {
        file << payload_size << ",";
      }
      file << "\n";
      file << "Period: ";
      for (const int& period_ms : options.period_ms) {
        file << period_ms << ",";
      }
      file << "\n";

      file.close();
      // RCLCPP_INFO(this->get_logger(), "Metadata written to file: %s", metadata_file_path.c_str());
    }

    std::string node_name;
    std::string log_dir;
    std::map<std::string, std::vector<MessageLog>> message_logs_;

    void record_log(const std::string& topic_name, const uint32_t& message_idx, const rclcpp::Time& time_stamp) {
      MessageLog log = {message_idx, time_stamp};
      message_logs_[topic_name].emplace_back(log);
    }

    void write_all_logs(const std::map<std::string, std::vector<MessageLog>>& message_logs_) {
      for (const auto &[topic_name, topic_logs] : message_logs_) {
        std::stringstream ss;
        ss << log_dir << "/" << node_name << "_log" <<  "/" << topic_name << "_log.txt" ;
        const std::string log_file_path = ss.str();
        ss.str("");
        ss.clear();

        std::ofstream file(log_file_path, std::ios::out | std::ios::trunc);
        if (!file.is_open()) {
            RCLCPP_ERROR(this->get_logger(), "Failed to open file: %s", log_file_path.c_str());
            return;
        }

        file << "StartTime: " << start_time_[topic_name].nanoseconds() << "\n" ;
        file << "EndTime: " << end_time_[topic_name].nanoseconds() << "\n" ;

        for (const auto& log : topic_logs) {
            file << "Index: " << log.message_idx << ", Timestamp: " << log.time_stamp.nanoseconds() << "\n";
        }

        file.close();
        RCLCPP_INFO(this->get_logger(), "MessageLogs written to file: %s", log_file_path.c_str());
      }
    }

    void print_qos_settings(const rclcpp::QoS &qos) {
      auto qos_profile = qos.get_rmw_qos_profile();

      std::string reliability = (qos_profile.reliability == rmw_qos_reliability_policy_t::RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT) ? "Best Effort" : "Reliable";
      std::string durability = (qos_profile.durability == rmw_qos_durability_policy_t::RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL) ? "Transient Local" : "Volatile";
      std::string history = (qos_profile.history == rmw_qos_history_policy_t::RMW_QOS_POLICY_HISTORY_KEEP_LAST) ? "Keep Last" : "Keep All";
      std::string depth = std::to_string(qos_profile.depth);

      std::cout << "QoS Settings" << std::endl;
      std::cout << "Reliability: " << reliability << std::endl;
      std::cout << "Durability: " << durability << std::endl;
      std::cout << "History: " << history << std::endl;
      std::cout << "Depth: " << depth << std::endl;
    }
};

void sigint_handler (int signum)
{
  rclcpp::shutdown();
}

int main(int argc, char * argv[])
{
  auto options = parse_options(argc, argv);
  create_result_directory(options);
  std::cout << options << "\n" << "Start Publisher!" << std::endl;

  setvbuf(stdout, NULL, _IONBF, BUFSIZ);
  rclcpp::init(argc, argv);

  std::signal(SIGINT, sigint_handler);
  std::signal(SIGTERM, sigint_handler);

  auto node = std::make_shared<Publisher>(options);
  rclcpp::spin(node);
  rclcpp::shutdown();

  return 0;
}