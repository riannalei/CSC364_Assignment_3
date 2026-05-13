# a3 client — udp send with reno-ish cwnd + checksums

import argparse
import json
import select
import socket
import struct
import time

MSS = 1024
FILE_BYTES = 1024 * 1024
TIMEOUT = 0.5
RTT_SCALE = 0.1  # for graph x axis (we pretend 100ms rtt)


def cksum(payload):
    return sum(payload) % 65535


def make_pkt(seq, payload):
    return struct.pack("!IH", seq, cksum(payload)) + payload


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

        self.outstanding = {}  # seq -> [bytes, time sent]
        self.num_retrans = 0

        self.t0 = time.monotonic()
        self.log_times = []
        self.log_cwnd = []
        self.log_rtt_units = []
        self.log_retrans = []
        self.last_snap = None

    def window_bytes(self):
        w = int(self.cwnd)
        if w < 1:
            w = 1
        return w * MSS

    def in_flight(self):
        return self.next_seq - self.send_base

    def can_send(self):
        if self.next_seq >= FILE_BYTES:
            return False
        return self.in_flight() < self.window_bytes()

    def send_chunk(self, seq, payload, retrans):
        self.sock.sendto(make_pkt(seq, payload), self.addr)
        t = time.monotonic()
        self.outstanding[seq] = [payload, t]
        if retrans:
            self.num_retrans += 1

    def send_new(self):
        while self.can_send():
            chunk = self.data[self.next_seq : self.next_seq + MSS]
            if not chunk:
                break
            self.send_chunk(self.next_seq, chunk, False)
            self.next_seq += len(chunk)

    def resend_oldest(self):
        if self.send_base >= FILE_BYTES:
            return
        seq = self.send_base
        self.send_chunk(seq, self.data[seq : seq + MSS], True)

    def on_timeout(self):
        self.ssthresh = max(self.cwnd / 2.0, 2.0)
        self.cwnd = 1.0
        self.dupacks = 0
        self.fast_recovery = False
        self.resend_oldest()

    def on_ack(self, ack):
        if ack < self.send_base:
            return

        if ack > self.send_base:
            self.dupacks = 0
            segs = (ack - self.send_base) // MSS
            if segs < 1:
                segs = 1

            gone = []
            for s in self.outstanding:
                ln = len(self.outstanding[s][0])
                if s + ln <= ack:
                    gone.append(s)
            for s in gone:
                del self.outstanding[s]
            self.send_base = ack

            if self.fast_recovery:
                self.cwnd = self.ssthresh
                self.fast_recovery = False
            else:
                if self.cwnd < self.ssthresh:
                    self.cwnd += float(segs)
                else:
                    self.cwnd += float(segs) / self.cwnd
            return

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
                self.resend_oldest()
        elif self.fast_recovery:
            self.cwnd += 1.0

    def snapshot(self):
        k = (self.send_base, self.cwnd, self.num_retrans)
        if k == self.last_snap:
            return
        self.last_snap = k
        elapsed = time.monotonic() - self.t0
        self.log_times.append(elapsed)
        self.log_cwnd.append(self.cwnd)
        self.log_rtt_units.append(elapsed / RTT_SCALE)
        self.log_retrans.append(self.num_retrans)

    def drain(self, first):
        chunks = [first]
        self.sock.setblocking(False)
        try:
            while True:
                try:
                    b, _ = self.sock.recvfrom(4096)
                    chunks.append(b)
                except BlockingIOError:
                    break
        finally:
            self.sock.setblocking(True)
        for b in chunks:
            if len(b) >= 4:
                ack = struct.unpack("!I", b[:4])[0]
                self.on_ack(ack)
                self.snapshot()

    def run(self):
        self.send_new()
        self.snapshot()

        while self.send_base < FILE_BYTES:
            ob = self.send_base
            if ob in self.outstanding:
                left = TIMEOUT - (time.monotonic() - self.outstanding[ob][1])
            else:
                left = TIMEOUT
            if left < 0:
                left = 0

            r, _, _ = select.select([self.sock], [], [], left)
            if r:
                buf, _ = self.sock.recvfrom(4096)
                self.drain(buf)
            else:
                self.on_timeout()
                self.snapshot()

            self.send_new()

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
        print("need exactly 1MB file")
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
