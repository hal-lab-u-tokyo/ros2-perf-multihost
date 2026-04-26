def calc_throughput(total_loss, total_sent, payload_size, eval_time):
    """
    total_loss: total number of lost messages
    total_sent: total number of sent messages
    payload_size: bytes per message
    eval_time: evaluation time in seconds
    """
    received = total_sent - total_loss
    if eval_time <= 0:
        return 0.0
    throughput_bps = received * payload_size / eval_time  # [B/s]
    throughput_mbps = throughput_bps / 1_000_000  # [MB/s]
    return throughput_bps, throughput_mbps
