#include <chrono>
#include <iostream>
#include <string>
#include <vector>

#include "cxxopts.hpp"
#include "node_options/cli_options.hpp"

namespace node_options
{

// デフォルト値
Options::Options()
{
    eval_time = 60;
    qos_history="KEEP_LAST";
    qos_depth = 1;
    qos_reliability = "RELIABLE";
}

// コンストラクタ
Options::Options(int argc, char ** argv)
: Options()
{
    parse(argc, argv);
}

// 受け取ったコマンドライン引数をもとに、option変数を更新
void Options::parse(int argc, char ** argv)
{
    cxxopts::Options options(argv[0], "ROS2 performance benchmark");

    options.add_options()
        ("node_name", "name for this node", cxxopts::value<std::string>(node_name))
        ("topic_names", "topic_name for this node", cxxopts::value<std::vector<std::string>>(topic_names))
        ("s, size", "payload size", cxxopts::value<std::vector<int>>(payload_size), "bytes")
        ("p, period", "publish frequency", cxxopts::value<std::vector<int>>(period_ms), "ms_sec")
        ("eval_time", "period of publishing", cxxopts::value<int>(eval_time), "sec")
        ("qos_history", "KEEP_LAST or KEEP_ALL", cxxopts::value<std::string>(qos_history))
        ("qos_depth", "KEEP_LAST(n)", cxxopts::value<int>(qos_depth))
        ("qos_reliability", "RELIABLE or BEST_EFFORT", cxxopts::value<std::string>(qos_reliability));

    try {
        auto result = options.parse(argc, argv);

        if(result.count("node_name") == 0){
            std::cout << "Please specify the name for this node" << std::endl;
            exit(1);
        }

        if(result.count("topic_names") == 0){
            std::cout << "Please specify the topic_name for this node" << std::endl;
            exit(1);
        }
    } catch (const cxxopts::exceptions::exception & e) {
        std::cout << "Error parsing options: " << e.what() << std::endl;
        exit(1);
    }
}

// コマンドラインでの表示を見やすくするためのオーバーロード処理
std::ostream & operator<<(std::ostream & os, const Options & options)
{
    os << "Node Name: " << options.node_name << std::endl;
    os << "Evaluation time: " << options.eval_time << "s" << std::endl;

    for (size_t i = 0; i < options.topic_names.size(); ++i) {
        os << "Topic: " << options.topic_names[i] << std::endl;

        if(!options.payload_size.empty()){
            os << "payload_size: " << options.payload_size[i] << " bytes" << std::endl;
        }

        if(!options.period_ms.empty()){
            os << "period_ms: " << options.period_ms[i] << " ms" << std::endl;
        }
    }

    return os;
}

} // ここまでnode_optionsの名前空間