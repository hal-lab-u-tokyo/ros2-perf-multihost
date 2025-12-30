"""
irobot_benchmark -> latency_all.txt

input: logs folder
output: latency_all.txt, latency_total.txt
"""

import os
import numpy as np
import argparse


# all_node_info = [{"name": lyon, "type": Publisher, "pub_topics": ["amazon", "inazuma", ...], "sub_topics": [] }, {}]
def get_node_and_topics(logs_folder_path):
    all_node_info = []

    # metadata Subscriber or Intermediate
    for node_folder in os.listdir(logs_folder_path):
        node_folder_path = os.path.join(logs_folder_path, node_folder)  # ./logs/node1
        if not os.path.isdir(node_folder_path):
            continue  # ファイルはスキップ
        metadata_path = os.path.join(node_folder_path, "metadata.txt")  # ./logs/node1/metadata.txt
        node_info = {}

        with open(metadata_path, "r") as metadata:
            lines = metadata.readlines()
            node_name = ""
            node_type = ""
            pub_topic_list = []
            sub_topic_list = []

            for line in lines:
                if line.startswith("Name:"):
                    node_name = line.split(":", 1)[1].strip()  # node1
                if line.startswith("NodeType:"):
                    node_type = line.split(":", 1)[1].strip()  # ”Publisher", "Intermediate"

            if node_type == "Publisher":
                for line in lines:
                    if line.startswith("Topics:"):
                        topics = line.split(":", 1)[1].strip().split(",")
                        pub_topic_list = [topic for topic in topics if topic]

            elif node_type == "Subscriber":
                for line in lines:
                    if line.startswith("Topics:"):
                        topics = line.split(":", 1)[1].strip().split(",")
                        sub_topic_list = [topic for topic in topics if topic]

            elif node_type == "Intermediate":
                for line in lines:
                    if line.startswith("Topics(Pub):"):
                        pub_topics = line.split(":", 1)[1].strip().split(",")
                        pub_topic_list = [topic for topic in pub_topics if topic]
                    if line.startswith("Topics(Sub):"):
                        sub_topics = line.split(":", 1)[1].strip().split(",")
                        sub_topic_list = [topic for topic in sub_topics if topic]

            node_info["name"] = node_name
            node_info["type"] = node_type
            node_info["pub_topics"] = pub_topic_list
            node_info["sub_topics"] = sub_topic_list

            all_node_info.append(node_info)

    return all_node_info


def cal_all_latency(all_node_info, logs_base_path):
    # make log.txt -> [("StartTime, 1111"), ("EndTime, 2222"), (0, 1120), (1, 1125)...]
    def get_log(logdata_path, type):
        logdata_list = []
        with open(logdata_path, "r") as log_file:
            lines = log_file.readlines()
            for line in lines:
                line = line.strip()
                if "StartTime:" in line:
                    start_time = line.split(":", 1)[1].strip().split(",")[0]
                    logdata_list.append(("StartTime", start_time))
                if "EndTime:" in line:
                    end_time = line.split(":", 1)[1].strip().split(",")[0]
                    logdata_list.append(("EndTime", end_time))

                if "Index:" in line and "Timestamp:" in line:
                    # "Index:" と "Timestamp:" を分割して値を取得
                    parts = line.split(", ")
                    if type == "Publisher":  # Publisher log / Index: Timestamp:
                        index = int(parts[0].split(":")[1].strip())
                        timestamp = int(parts[1].split(":")[1].strip())
                        logdata_list.append((index, timestamp))
                    else:  # Other log / Pub_Node_name: Index: Timestamp:
                        index = int(parts[1].split(":")[1].strip())
                        timestamp = int(parts[2].split(":")[1].strip())
                        logdata_list.append((index, timestamp))

        return logdata_list

    warmup_ns = 1_000_000_000
    all_latency_results = []
    sub_all_node_statics = []
    for sub_node_info in all_node_info:
        if sub_node_info["type"] == "Publisher":
            continue

        else:
            sub_node_statics = {}  # {"node": lyon, "topics": [{"topic": amazon, "loss": 0, "latency": [0.110, 0.223, ...]}, {"topic": inazuma, }...] }
            sub_node_name = sub_node_info["name"]
            sub_node_type = sub_node_info["type"]
            sub_topic_list = sub_node_info["sub_topics"]
            sub_node_statics["node"] = sub_node_name
            sub_node_statics["topics"] = []

            for sub_topic in sub_topic_list:
                sub_topic_statics = {}
                sub_topic_statics["topic"] = sub_topic
                loss = 0
                latency_results = []

                for pub_node_info in all_node_info:
                    pub_node_name = pub_node_info["name"]
                    pub_node_type = pub_node_info["type"]
                    pub_topic_list = pub_node_info["pub_topics"]

                    if sub_topic in pub_topic_list:
                        pub_logdata_path = ""
                        if pub_node_type == "Publisher":
                            pub_logdata_path = os.path.join(logs_base_path, f"{pub_node_name}_log", f"{sub_topic}_log.txt")
                        elif pub_node_type == "Intermediate":
                            pub_logdata_path = os.path.join(logs_base_path, f"{pub_node_name}_log", f"{sub_topic}_pub_log.txt")
                        sub_logdata_path = ""
                        if sub_node_type == "Subscriber":
                            sub_logdata_path = os.path.join(logs_base_path, f"{sub_node_name}_log", f"{sub_topic}_log.txt")
                        elif sub_node_type == "Intermediate":
                            sub_logdata_path = os.path.join(logs_base_path, f"{sub_node_name}_log", f"{sub_topic}_sub_log.txt")

                        pub_logdata_list = get_log(
                            pub_logdata_path, pub_node_type
                        )  # [("StartTime, 1111"), ("EndTime, 2222"), (0, 1120), (1, 1125)...]
                        sub_logdata_list = get_log(
                            sub_logdata_path, sub_node_type
                        )  # [("StartTime, 1112"), ("EndTime, 2232"), (0, 1121), (1, 1128)...]

                        pub_start_time = next(item[1] for item in pub_logdata_list if item[0] == "StartTime")
                        pub_end_time = next(item[1] for item in pub_logdata_list if item[0] == "EndTime")
                        sub_start_time = next(item[1] for item in sub_logdata_list if item[0] == "StartTime")
                        sub_end_time = next(item[1] for item in sub_logdata_list if item[0] == "EndTime")
                        # StartTimeとEndTimeは用済なので消す
                        pub_logdata_list = [
                            item for item in pub_logdata_list if item[0] != "StartTime" and item[0] != "EndTime"
                        ]
                        sub_logdata_list = [
                            item for item in sub_logdata_list if item[0] != "StartTime" and item[0] != "EndTime"
                        ]

                        # この共通集合に入る時間帯が計測対象
                        common_start_time = int(max(pub_start_time, sub_start_time)) + warmup_ns
                        common_end_time = int(min(pub_end_time, sub_end_time))

                        # 共通時間帯が成立しない場合は警告してスキップ
                        if common_start_time >= common_end_time:
                            print(
                                f"[WARN] No common time window: node={sub_node_name}, topic={sub_topic} "
                                f"pub_node={pub_node_name}, pub_path={pub_logdata_path}, sub_path={sub_logdata_path} "
                                f"(pub:[{pub_start_time},{pub_end_time}] sub:[{sub_start_time},{sub_end_time}] warmup={warmup_ns})"
                            )
                            continue

                        # Start~Endの共通集合に入らないindexを除く
                        pub_indices = {
                            item[0]
                            for item in pub_logdata_list
                            if int(item[1]) >= common_start_time and int(item[1]) <= common_end_time
                        }
                        sub_indices = {
                            item[0]
                            for item in sub_logdata_list
                            if int(item[1]) >= common_start_time and int(item[1]) <= common_end_time
                        }

                        # pubまたはsubの片方にしか入っていないindexをlossとしてlossをcount
                        loss_index_count = len(set(pub_indices) - set(sub_indices)) + len(set(sub_indices) - set(pub_indices))
                        loss += loss_index_count
                        common_indices = pub_indices.intersection(sub_indices)  # [0, 1, 3, ...]

                        pub_dict = dict(pub_logdata_list)  # {index: timestamp}
                        sub_dict = dict(sub_logdata_list)

                        for index in common_indices:
                            latency_results.append((sub_dict[index] - pub_dict[index]) / 1_000_000)
                        # for index in common_indices:
                        #     timestamp_pub = next(timestamp for idx, timestamp in pub_logdata_list if idx == index)
                        #     timestamp_sub = next(timestamp for idx, timestamp in sub_logdata_list if idx == index)

                        #     latency_results.append((timestamp_sub - timestamp_pub) / 1_000_000)  # [0.120, 0.321, ...]

                sub_topic_statics["loss"] = loss
                sub_topic_statics["mean"] = round(np.mean(latency_results), 6)
                sub_topic_statics["sd"] = round(np.std(latency_results), 6)
                sub_topic_statics["min"] = round(np.min(latency_results), 6)
                sub_topic_statics["max"] = round(np.max(latency_results), 6)
                sub_topic_statics["q1"] = round(np.percentile(latency_results, 25), 6)
                sub_topic_statics["mid"] = round(np.percentile(latency_results, 50), 6)
                sub_topic_statics["q3"] = round(np.percentile(latency_results, 75), 6)

                sub_node_statics["topics"].append(
                    sub_topic_statics
                )  # {"node": lyon, "topics": [{"topic": amazon, "loss": 0, "mean": 0.220, ...}, {"topic": inazuma, }...] }

                all_latency_results.append(latency_results)
        sub_all_node_statics.append(sub_node_statics)

    return sub_all_node_statics, all_latency_results


def write_all_latency(sub_all_node_statics, results_dir):
    data = []
    data.append(["node", "topic", "lost[#]", "mean[ms]", "sd[ms]", "min[ms]", "q1[ms]", "mid[ms]", "q3[ms]", "max[ms]"])
    with open(f"{results_dir}/all_latency.txt", "w") as f:
        for node_statics in sub_all_node_statics:
            node_name = node_statics["node"]
            for topic_statics in node_statics["topics"]:
                topic_name = topic_statics["topic"]
                topic_loss = topic_statics["loss"]
                topic_mean = topic_statics["mean"]
                topic_sd = topic_statics["sd"]
                topic_min = topic_statics["min"]
                topic_q1 = topic_statics["q1"]
                topic_mid = topic_statics["mid"]
                topic_q3 = topic_statics["q3"]
                topic_max = topic_statics["max"]
                data.append(
                    [
                        node_name,
                        topic_name,
                        topic_loss,
                        topic_mean,
                        topic_sd,
                        topic_min,
                        topic_q1,
                        topic_mid,
                        topic_q3,
                        topic_max,
                    ]
                )

        col_widths = [12, 12, 12, 12, 12, 12, 12, 12, 12, 12]
        header = "".join(f"{data[0][i]:<{col_widths[i]}}" for i in range(len(data[0])))
        f.write(f"{header}\n")
        f.write("-" * len(header))
        f.write("\n")

        for row in data[1:]:
            row = "".join(f"{row[i]:<{col_widths[i]}}" for i in range(len(row)))
            f.write(f"{row}\n")


def write_total_latency(sub_all_node_statics, all_latency_results, result_dir):
    total_loss = 0
    total_topics = 0
    for node_statics in sub_all_node_statics:
        for topic_statics in node_statics["topics"]:
            total_loss += topic_statics["loss"]
            total_topics += 1

    final_latency_results = [item for node_latency in all_latency_results for item in node_latency]  # [[], [],,,,] -> []
    total_mean = round(np.mean(final_latency_results), 6)
    total_sd = round(np.std(final_latency_results), 6)
    total_min = round(np.min(final_latency_results), 6)
    total_q1 = round(np.percentile(final_latency_results, 25), 6)
    total_mid = round(np.percentile(final_latency_results, 50), 6)
    total_q3 = round(np.percentile(final_latency_results, 75), 6)
    total_max = round(np.max(final_latency_results), 6)

    data = []
    data.append(["lost[#]", "topics[#]", "mean[ms]", "sd[ms]", "min[ms]", "q1[ms]", "mid[ms]", "q3[ms]", "max[ms]"])
    with open(f"{result_dir}/total_latency.txt", "w") as f:
        data.append([total_loss, total_topics, total_mean, total_sd, total_min, total_q1, total_mid, total_q3, total_max])

        col_widths = [12] * len(data[0])
        header = "".join(f"{data[0][i]:<{col_widths[i]}}" for i in range(len(data[0])))
        f.write(f"{header}\n")
        f.write("-" * len(header))
        f.write("\n")

        for row in data[1:]:
            row = "".join(f"{row[i]:<{col_widths[i]}}" for i in range(len(row)))
            f.write(f"{row}\n")


def process_log_directory(log_dir_name, logs_base_path, results_base_path):
    """指定されたログディレクトリを解析し、結果を保存する"""
    logs_folder_path = os.path.join(logs_base_path, log_dir_name)
    result_dir = os.path.join(results_base_path, log_dir_name)

    print(f"Processing: {log_dir_name}")
    print(f"  Logs path: {logs_folder_path}")
    print(f"  Results path: {result_dir}")

    # 結果ディレクトリを作成
    os.makedirs(result_dir, exist_ok=True)

    # 解析実行
    all_node_info = get_node_and_topics(logs_folder_path)
    print(f"  Nodes found: {[n['name'] for n in all_node_info]}")

    sub_all_node_statics, all_latency_results = cal_all_latency(all_node_info, logs_folder_path)
    write_all_latency(sub_all_node_statics, result_dir)
    write_total_latency(sub_all_node_statics, all_latency_results, result_dir)

    print(f"  Done: Results saved to {result_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process log directories and save latency results.")
    parser.add_argument("--logs", type=str, default="./logs", help="Base path for logs")
    parser.add_argument("--results", type=str, default="./results", help="Base path for results")
    args = parser.parse_args()

    logs_base_path = args.logs
    results_base_path = args.results

    # resultsディレクトリがなければ作成
    os.makedirs(results_base_path, exist_ok=True)

    # logsディレクトリが存在しない場合は終了
    if not os.path.exists(logs_base_path):
        print(f"Error: Logs directory '{logs_base_path}' does not exist.")
        exit(1)

    # logsディレクトリ内のディレクトリを取得
    log_dirs = [d for d in os.listdir(logs_base_path) if os.path.isdir(os.path.join(logs_base_path, d))]

    if not log_dirs:
        print(f"No directories found in '{logs_base_path}'.")
        exit(0)

    # 既に解析済みの結果ディレクトリを取得
    existing_results = set()
    if os.path.exists(results_base_path):
        existing_results = set(os.listdir(results_base_path))

    # 未解析のログディレクトリを処理（ディレクトリのみ取得）
    pending_dirs = [d for d in log_dirs if d not in existing_results and os.path.isdir(os.path.join(logs_base_path, d))]

    if not pending_dirs:
        print("All log directories have already been processed.")
        print(f"  Existing results: {sorted(existing_results)}")
        exit(0)

    print(f"Found {len(pending_dirs)} new log directory(ies) to process:")
    for d in sorted(pending_dirs):
        print(f"  - {d}")
    print()

    # 各ログディレクトリを処理
    for log_dir_name in sorted(pending_dirs):
        try:
            process_log_directory(log_dir_name, logs_base_path, results_base_path)
        except Exception as e:
            print(f"  Error processing {log_dir_name}: {e}")
        print()

    print("All processing complete.")
