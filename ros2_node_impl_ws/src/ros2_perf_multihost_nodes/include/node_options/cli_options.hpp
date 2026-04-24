// 二重インクルード防止
#ifndef ROS2_PERF_MULTIHOST_NODES__NODE_OPTIONS__CLI_OPTIONS_HPP_
#define ROS2_PERF_MULTIHOST_NODES__NODE_OPTIONS__CLI_OPTIONS_HPP_

#include <iosfwd>
#include <string>
#include <vector>

namespace node_options {

class Options {
 public:
  Options();

  Options(int argc, char** argv);

  void parse(int argc, char** argv);

  std::string node_name;
  std::vector<std::string> topic_names;
  std::vector<int> payload_size;
  std::vector<int> period_ms;
  int eval_time;
  std::string log_dir;
  std::string qos_reliability;
  std::string qos_history;
  int qos_depth;
};

std::ostream& operator<<(std::ostream& os, const Options& options);

}  // namespace node_options

#endif
