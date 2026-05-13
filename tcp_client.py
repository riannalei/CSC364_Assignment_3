# CSC364 A3 - send a 1MB file over fake TCP (UDP underneath)
# Reno-ish: slow start, congestion avoidance, fast retransmit, 500ms timeout

import argparse
import json
import select
import socket
import struct
import time

MSS = 1024
FILE_BYTES = 1024 * 1024
TIMEOUT = 0.5  # seconds, spec
RTT_FOR_PLOTS = 0.1  # x axis for cwnd graph = seconds / this (rough RTT ticks)


def cksum(payload):
    # assignment: sum of bytes mod 65535
    return sum(payload) % 65535


def make_pkt(seq, payload):
    c = cksum(payload)
    return struct.pack("!IH", seq, c) + payload


class Client:
    def __init__(self, host, port, file_bytes):
        self.addr = (host, port)
        self.data = file_bytes
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.send_base = 0
        self.next_seq = 0
        self.cwnd = 1.0
        self.ssthresh = 64.0
        self.dupacks = 0
        self.fast_recovery = False

        # seq -> [payload bytes, last_send_time]
        self.outstanding = {}
        self.num_retrans = 0

        # for graphs
        self.t0 = time.monotonic()
        self.log_times = []
        self.log_cwnd = []
        self.log_rtt_units = []
        self.log_retrans = []
        self.last_snap = None

    def window_bytes(self):
        # cwnd is in "packets" in the handout; I treat 1 packet = MSS bytes
        w = int(self.cwnd)
        if w < 1:
            w = 1
        return w * MSS

    def bytes_in_flight(self):
        return self.next_seq - self.send_base

    def can_send_more(self):
        if self.next_seq >= FILE_BYTES:
            return False
        return self.bytes_in_flight() < self.window_bytes()

    def send_chunk(self, seq, payload, retrans):
        self.sock.sendto(make_pkt(seq, payload), self.addr)
        now = time.monotonic()
        self.outstanding[seq] = [payload, now]
        if retrans:
            self.num_retrans += 1

    def pump_new_data(self):
        while self.can_send_more():
            chunk = self.data[self.next_seq : self.next_seq + MSS]
            if len(chunk) == 0:
                break
            self.send_chunk(self.next_seq, chunk, False)
            self.next_seq += len(chunk)

    def rtx_oldest(self):
        if self.send_base >= FILE_BYTES:
            return
        seq = self.send_base
        chunk = self.data[seq : seq + MSS]
        self.send_chunk(seq, chunk, True)

    def on_timeout(self):
        self.ssthresh = max(self.cwnd / 2.0, 2.0)
        self.cwnd = 1.0
        self.dupacks = 0
        self.fast_recovery = False
        self.rtx_oldest()

    def on_ack(self, ack):
        # ack = next byte receiver wants (cumulative)
        if ack < self.send_base:
            return

        if ack > self.send_base:
            self.dupacks = 0
            new_bytes = ack - self.send_base
            segs = new_bytes // MSS
            if segs <= 0:
                segs = 1

            # drop acked segments from outstanding dict
            kill = []
            for s in self.outstanding:
                plen = len(self.outstanding[s][0])
                if s + plen <= ack:
                    kill.append(s)
            for s in kill:
                del self.outstanding[s]
            self.send_base = ack

            if self.fast_recovery:
                self.cwnd = self.ssthresh
                self.fast_recovery = False
            else:
                if self.cwnd < self.ssthresh:
                    # slow start
                    self.cwnd += float(segs)
                else:
                    # AIMD-ish: bump a little per acked segment
                    self.cwnd += float(segs) / self.cwnd
            return

        # duplicate ack (ack == send_base)
        if self.send_base >= self.next_seq:
            return
        self.dupacks += 1
        if self.dupacks < 3:
            return
        if self.dupacks == 3:
            self.ssthresh = max(self.cwnd / 2.0, 2.0)
            if not self.fast_recovery:
                self.cwnd = self.ssthresh + 3.0
                self.fast_recovery = True
                self.rtx_oldest()
        elif self.fast_recovery:
            self.cwnd += 1.0

    def snapshot(self):
        # only log when something actually changed (keeps json smaller)
        key = (self.send_base, self.cwnd, self.num_retrans)
        if key == self.last_snap:
            return
        self.last_snap = key
        elapsed = time.monotonic() - self.t0
        self.log_times.append(elapsed)
        self.log_cwnd.append(self.cwnd)
        self.log_rtt_units.append(elapsed / RTT_FOR_PLOTS)
        self.log_retrans.append(self.num_retrans)

    def drain_acks(self, first_buf):
        bufs = [first_buf]
        self.sock.setblocking(False)
        try:
            while True:
                try:
                    b, _ = self.sock.recvfrom(4096)
                    bufs.append(b)
                except BlockingIOError:
                    break
        finally:
            self.sock.setblocking(True)

        for b in bufs:
            if len(b) < 4:
                continue
            ack = struct.unpack("!I", b[:4])[0]
            self.on_ack(ack)
            self.snapshot()

    def run(self):
        self.pump_new_data()
        self.snapshot()

        while self.send_base < FILE_BYTES:
            oldest = self.send_base
            if oldest in self.outstanding:
                remaining = TIMEOUT - (time.monotonic() - self.outstanding[oldest][1])
            else:
                remaining = TIMEOUT
            if remaining < 0:
                remaining = 0

            r, _, _ = select.select([self.sock], [], [], remaining)
            if r:
                buf, _ = self.sock.recvfrom(4096)
                self.drain_acks(buf)
            else:
                self.on_timeout()
                self.snapshot()

            self.pump_new_data()

        self.sock.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9999)
    ap.add_argument("--file", default="input_1mb.bin")
    ap.add_argument("--metrics", default=None)
    ap.add_argument("--loss-label", default="")
    args = ap.parse_args()

    with open(args.file, "rb") as f:
        blob = f.read()
    if len(blob) != FILE_BYTES:
        print("error: file must be exactly 1MB")
        return

    c = Client(args.host, args.port, blob)
    c.run()
    print("done")

    if args.metrics:
        doc = {
            "meta": {
                "loss_label": args.loss_label or None,
                "host": args.host,
                "port": args.port,
            },
            "metrics": {
                "times_sec": c.log_times,
                "cwnd_packets": c.log_cwnd,
                "rtt_index": c.log_rtt_units,
                "retrans_cumulative": c.log_retrans,
                "retrans_times_sec": c.log_times,
                "retrans_cum_at_event": c.log_retrans,
            },
        }
        with open(args.metrics, "w") as f:
            json.dump(doc, f, indent=2)


if __name__ == "__main__":
    main()
