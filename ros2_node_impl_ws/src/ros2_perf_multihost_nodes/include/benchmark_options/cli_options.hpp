#ifndef ROS2_PERF_MULTIHOST_NODES__BENCHMARK_OPTIONS__CLI_OPTIONS_HPP_
#define ROS2_PERF_MULTIHOST_NODES__BENCHMARK_OPTIONS__CLI_OPTIONS_HPP_

#include <iosfwd>
#include <string>
#include <vector>

namespace benchmark_options {

class Options {
 public:
  Options();
  Options(int argc, char** argv);

  void parse(int argc, char** argv);

  std::string node_name;
  std::vector<std::string> topic_names_pub;
  std::vector<std::string> topic_names_sub;
  std::vector<std::string> msg_types_pub;
  std::vector<std::string> msg_types_sub;
  std::vector<int> msg_sizes_pub;
  std::vector<std::string> msg_pass_by_pub;
  std::vector<std::string> msg_pass_by_sub;
  std::vector<int> period_ms;
  int eval_time;
  std::string log_dir;
  std::vector<std::string> qos_history_pub;
  std::vector<std::string> qos_history_sub;
  std::vector<int> qos_depth_pub;
  std::vector<int> qos_depth_sub;
  std::vector<std::string> qos_reliability_pub;
  std::vector<std::string> qos_reliability_sub;
  std::vector<std::string> qos_source_pub;
  std::vector<std::string> qos_source_sub;
  std::string qos_history;
  int qos_depth;
  std::string qos_reliability;
  bool qos_override;
};

std::ostream& operator<<(std::ostream& os, const Options& options);

}  // namespace benchmark_options

#endif
