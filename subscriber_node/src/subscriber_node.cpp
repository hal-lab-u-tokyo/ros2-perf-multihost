#include <cstdio>
#include <memory>
#include <string>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <sstream>
#include <fstream>
#include <filesystem>

#include "node_options/cli_options.hpp"
#include "publisher_node/msg/performance_header.hpp"
#include "publisher_node/msg/int_message.hpp"

struct MessageLog {
  std::string pub_node_name;
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
  ss << options.node_name << "_log" ;
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
    std::ofstream ofs(file_path); // ファイルを開く（存在しない場合は作成）
    if(ofs){
      std::cout << "Log file created: " << file_path << std::endl;
      ofs.close();
    } else {
      std::cerr << "Failed to create: " << file_path << std::endl;
    }
  }
}

class Subscriber : public rclcpp::Node
{
public:
  explicit Subscriber(const node_options::Options & options)
    : Node(options.node_name)
  {
    node_name = options.node_name;
    create_metadata_file(options);
    
    // 複数のトピック名を扱う場合
    for (size_t i = 0; i < options.topic_names.size(); ++i) {
      const std::string & topic_name = options.topic_names[i];
      start_time_[topic_name] = this->get_clock()->now();
      end_time_[topic_name] = start_time_[topic_name] + rclcpp::Duration::from_seconds(options.eval_time) ;

      auto callback = [this, topic_name, options](const publisher_node::msg::IntMessage::SharedPtr message_) -> void{
        // eval_time秒過ぎてたら受け取らず終了
        auto sub_time = this->get_clock()->now();
        if((sub_time.seconds() - start_time_[topic_name].seconds()) >= options.eval_time) {
          RCLCPP_INFO(this->get_logger(), "Topic %s has reached the evaluation time.", topic_name.c_str());
          return;
        }

        // message_->dataを16進数形式で表示 (0埋めはしない)
        std::ostringstream oss;
        for (const auto& byte : message_->data)
        {
            oss << std::hex << (int)byte << " ";
        }
        // subした時刻などを表示
        oss << std::dec <<"Time: " << std::fixed << std::setprecision(9) << static_cast<double>(sub_time.nanoseconds() - start_time_[topic_name].nanoseconds()) / 1e9;
        int current_pub_idx = message_->header.pub_idx;
        std::string pub_node_name = message_->header.node_name;
        RCLCPP_INFO(this->get_logger(), "Subscribe/ Topic: %s Data: %s Index: %d", topic_name.c_str(), oss.str().c_str(), current_pub_idx);

        // ログに記録
        record_log(topic_name, pub_node_name, current_pub_idx, sub_time);
      };

      // Qos設定
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
      

      // Subscriber作成
      auto subscriber = create_subscription<publisher_node::msg::IntMessage>(topic_name, qos, callback);
      subscribers_.emplace(topic_name, subscriber);

      // shutdownタイマー
      auto shutdown_node = 
        [this, &options]() -> void
        {
          RCLCPP_INFO(this->get_logger(), "Shutting down node...");
          rclcpp::shutdown();
      };

      auto shutdown_timer = create_wall_timer(std::chrono::seconds(options.eval_time + 10), shutdown_node);
      shutdown_timers_.emplace(topic_name, shutdown_timer);
    }
  }

  ~Subscriber() override {
      RCLCPP_INFO(this->get_logger(), "Node is shutting down.");
      write_all_logs(message_logs_);
  }

private:
  // トピックごとのPublisher
  std::unordered_map<std::string, rclcpp::Subscription<publisher_node::msg::IntMessage>::SharedPtr> subscribers_;
  std::unordered_map<std::string, rclcpp::Time> start_time_;
  std::unordered_map<std::string, rclcpp::Time> end_time_;

  std::unordered_map<std::string, rclcpp::TimerBase::SharedPtr> shutdown_timers_;

  void
  create_metadata_file(const node_options::Options & options)
  {
    std::stringstream ss;
    ss << options.node_name << "_log" <<  "/" << "metadata.txt" ;
    std::string metadata_file_path = ss.str();
    ss.str("");
    ss.clear();

    std::ofstream file(metadata_file_path, std::ios::out | std::ios::trunc);
    if (!file.is_open()) {
        RCLCPP_ERROR(this->get_logger(), "Failed to open file: %s", metadata_file_path.c_str());
        return;
    }

    
    file << "Name: " << options.node_name << "\n";
    file << "NodeType: " << "Subscriber" << "\n";
    file << "Topics: ";
    for (const std::string& topic_name : options.topic_names) {
      file << topic_name << ",";
    }

    file.close();
    RCLCPP_INFO(this->get_logger(), "Metadata written to file: %s", metadata_file_path.c_str());

    // ファイルのコピー
    try {
      std::string original_path = metadata_file_path;
      ss << "../../../../src/graduate_research/performance_test/logs_local/" << node_name << "_log" ;
      std::string destination_dir = ss.str();
      if (!std::filesystem::exists(destination_dir)) {
        std::filesystem::create_directories(destination_dir);
        std::cout << "Created directory: " << destination_dir << std::endl;
      }

      ss << "/" << "metadata.txt" ;
      std::string destination_path = ss.str();
      std::filesystem::copy_file(original_path, destination_path, std::filesystem::copy_options::overwrite_existing);
      std::cout << "File copied from " << original_path << " to " << destination_path << std::endl;
    } catch (const std::filesystem::filesystem_error &e) {
        std::cerr << "Error copying file: " << e.what() << std::endl;
    }
  }

  // ログ記録用
  std::string node_name;
  std::map<std::string, std::vector<MessageLog>> message_logs_;

  void record_log(const std::string& topic_name, const std::string& pub_node_name, const uint32_t& message_idx, const rclcpp::Time& time_stamp) {
    MessageLog log = {pub_node_name, message_idx, time_stamp};
    message_logs_[topic_name].emplace_back(log);
  }

  void write_all_logs(const std::map<std::string, std::vector<MessageLog>>& message_logs_) {
      for (const auto &[topic_name, topic_logs] : message_logs_) {
        std::stringstream ss;
        ss << node_name << "_log" <<  "/" << topic_name << "_log.txt" ;
        const std::string log_file_path = ss.str();
        ss.str("");
        ss.clear();

        std::ofstream file(log_file_path, std::ios::out | std::ios::trunc);
        if (!file.is_open()) {
            RCLCPP_ERROR(this->get_logger(), "Failed to open file: %s", log_file_path.c_str());
            return;
        }

        // StartTimeとEndTimeを書き込む
        file << "StartTime: " << start_time_[topic_name].nanoseconds() << "\n" ;
        file << "EndTime: " << end_time_[topic_name].nanoseconds() << "\n" ;

        for (const auto& log : topic_logs) {
            file << "Pub Node_Name: " << log.pub_node_name << ", Index: " << log.message_idx << ", Timestamp: " << log.time_stamp.nanoseconds() << "\n";
        }

        file.close();
        RCLCPP_INFO(this->get_logger(), "MessageLogs written to file: %s", log_file_path.c_str());

        // ファイルのコピー
        try {
          std::string original_path = log_file_path;
          ss << "../../../../src/graduate_research/performance_test/logs_local/" << node_name << "_log" ;
          std::string destination_dir = ss.str();
          if (!std::filesystem::exists(destination_dir)) {
            std::filesystem::create_directories(destination_dir);
            std::cout << "Created directory: " << destination_dir << std::endl;
          }

          ss << "/" << topic_name << "_log.txt" ;
          std::string destination_path = ss.str();
          std::filesystem::copy_file(original_path, destination_path, std::filesystem::copy_options::overwrite_existing);
          std::cout << "File copied from " << original_path << " to " << destination_path << std::endl;
        } catch (const std::filesystem::filesystem_error &e) {
            std::cerr << "Error copying file: " << e.what() << std::endl;
        }
      }
  }

};

int main(int argc, char * argv[])
{
  auto options = parse_options(argc, argv);
  create_result_directory(options) ;
  std::cout << options << "\n" << "Start Subscriber!" << std::endl;

  setvbuf(stdout, NULL, _IONBF, BUFSIZ);
  rclcpp::init(argc, argv);

  auto node = std::make_shared<Subscriber>(options);
  rclcpp::spin(node);
  rclcpp::shutdown();

  return 0;
}