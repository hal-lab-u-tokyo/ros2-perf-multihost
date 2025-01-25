/* 目的: あるDockerコンテナに対し、このプロジェクトがクローン&ビルドされると、そのコンテナには指定されたトピック名を持つpublisherノードが存在することになる */

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

#include "node_options/cli_options.hpp"
#include "publisher_node/msg/performance_header.hpp"
#include "publisher_node/msg/int_message.hpp"

struct MessageLog {
  uint32_t message_idx;
  rclcpp::Time time_stamp;
};

// コマンドラインオプション
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
  std::filesystem::create_directories(result_dir_name); // install/publisher_node/lib/publisher_node/my_node_log みたいな感じ
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


class Publisher : public rclcpp::Node
{
  public:
    explicit Publisher(const node_options::Options & options)
    : Node(options.node_name)
    {
      node_name = options.node_name;
      create_metadata_file(options);

      // シャットダウン予告
      RCLCPP_INFO(this->get_logger(), "Shutdown timer created with duration %d seconds", options.eval_time + 10);

      // 複数のトピック名を扱う場合
      for (size_t i = 0; i < options.topic_names.size(); ++i) {
        const std::string & topic_name = options.topic_names[i];
        int payload_size = options.payload_size[i];
        int period_ms = options.period_ms[i];

        pub_idx_[topic_name] = 0;
        start_time_[topic_name] = this->get_clock()->now();
        end_time_[topic_name] = start_time_[topic_name] + rclcpp::Duration::from_seconds(options.eval_time) ;

        // タイマー実行されるイベントハンドラー関数を生成
        auto publish_message =
          [this, topic_name, payload_size, &options]() -> void
          {
            int current_pub_idx = pub_idx_[topic_name];
            
            // 送信するメッセージの作成
            auto message_ = std::make_shared<publisher_node::msg::IntMessage>();
            message_->data.resize(payload_size);
            std::fill(message_->data.begin(), message_->data.end(), 0);

            auto time_stamp = this->get_clock()->now();
            if((time_stamp.seconds() - start_time_[topic_name].seconds()) >= options.eval_time) {
              RCLCPP_INFO(this->get_logger(), "Topic %s has reached the evaluation time.", topic_name.c_str());
              timers_[topic_name]->cancel();
              return;
            }

            message_->header.stamp.sec = static_cast<int32_t>(time_stamp.seconds() - start_time_[topic_name].seconds());
            message_->header.stamp.nanosec = static_cast<uint32_t>((time_stamp.nanoseconds() - start_time_[topic_name].nanoseconds()) % 1000000000);
            message_->header.pub_idx = current_pub_idx;
            message_->header.node_name = options.node_name;
            record_log(topic_name, current_pub_idx, time_stamp);

            // message->dataを16進数形式で表示 (0埋めはしない)
            std::ostringstream oss;
            for (const auto& byte : message_->data) {
              oss << std::hex << (int)byte << " ";
            }
            oss << std::dec <<"Time: " << std::fixed << std::setprecision(9) << static_cast<double>(time_stamp.nanoseconds() - start_time_[topic_name].nanoseconds()) / 1e9;

            RCLCPP_INFO(this->get_logger(), "Publish/ Topic: %s, Data: %s, Index: %d", topic_name.c_str(), oss.str().c_str(), current_pub_idx);

            // 該当トピックのPublisherでメッセージ送信
            publishers_[topic_name]->publish(*message_);

            pub_idx_[topic_name]++;
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

        print_qos_settings(qos);

        // Publisher作成
        auto publisher = create_publisher<publisher_node::msg::IntMessage>(topic_name, qos);
        publishers_.emplace(topic_name, publisher);

        // Timer作成
        auto timer = create_wall_timer(std::chrono::milliseconds(period_ms), publish_message);
        timers_.emplace(topic_name, timer);

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

    ~Publisher() override {
      RCLCPP_INFO(this->get_logger(), "Node is shutting down.");
      write_all_logs(message_logs_);
    }


  private:
    // トピックごとのPublisher,Timer,
    std::unordered_map<std::string, rclcpp::Publisher<publisher_node::msg::IntMessage>::SharedPtr> publishers_;

    // タイマーを保持
    std::unordered_map<std::string, rclcpp::TimerBase::SharedPtr> timers_;
    std::unordered_map<std::string, rclcpp::TimerBase::SharedPtr> shutdown_timers_;

    std::unordered_map<std::string, uint32_t> pub_idx_;
    std::unordered_map<std::string, rclcpp::Time> start_time_;
    std::unordered_map<std::string, rclcpp::Time> end_time_;

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

    void record_log(const std::string& topic_name, const uint32_t& message_idx, const rclcpp::Time& time_stamp) {
      MessageLog log = {message_idx, time_stamp};
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
            file << "Index: " << log.message_idx << ", Timestamp: " << log.time_stamp.nanoseconds() << "\n";
        }

        file.close();
        RCLCPP_INFO(this->get_logger(), "MessageLogs written to file: %s", log_file_path.c_str());

        // ファイルのコピー (ローカルで実行するとき用)
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

    void print_qos_settings(const rclcpp::QoS &qos) {
      auto qos_profile = qos.get_rmw_qos_profile();

      // QoSの列挙型を文字列に変換する関数
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
  // シグナルを受け取ったときにrclcpp::shutdown()を呼ぶ。Dockerコンテナ用
  rclcpp::shutdown();
  exit(0);
}


int main(int argc, char * argv[])
{
  auto options = parse_options(argc, argv);
  create_result_directory(options) ;
  std::cout << options << "\n" << "Start Publisher!" << std::endl;

  // クライアントライブラリの初期化
  setvbuf(stdout, NULL, _IONBF, BUFSIZ);
  rclcpp::init(argc, argv);

  std::signal(SIGINT, sigint_handler);
  std::signal(SIGTERM, sigint_handler);

  // Publisherノードの生成とスピン開始
  auto node = std::make_shared<Publisher>(options);
  rclcpp::spin(node);
  rclcpp::shutdown();

  return 0;
}