def calc_throughput(total_loss, total_sent, payload_size, eval_time):
    """
    total_loss: 総ロス数
    total_sent: 総送信数
    payload_size: 1メッセージのバイト数
    eval_time: 計測時間（秒）
    """
    received = total_sent - total_loss
    if eval_time <= 0:
        return 0.0
    throughput_bps = received * payload_size / eval_time  # [B/s]
    throughput_mbps = throughput_bps / 1_000_000  # [MB/s]
    return throughput_bps, throughput_mbps
