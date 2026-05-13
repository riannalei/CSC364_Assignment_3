# a3 server — udp recv, checksum, random drop, delayed acks

import argparse
import random
import socket
import struct
import threading

HDR = 6


def cksum(payload):
    return sum(payload) % 65535


def unpack(buf):
    if len(buf) < HDR:
        return None
    seq, got = struct.unpack("!IH", buf[:HDR])
    body = buf[HDR:]
    if cksum(body) != got:
        return None
    return seq, body


class AckTimer:
    # delayed ack: first pkt starts timer, rest update ack only

    def __init__(self, sock, peer, delay):
        self.sock = sock
        self.peer = peer
        self.delay = delay
        self.lock = threading.Lock()
        self.timer = None
        self.pending = False
        self.ack = 0

    def schedule(self, ack):
        with self.lock:
            self.ack = ack
            if self.pending:
                return
            self.pending = True
            self.timer = threading.Timer(self.delay, self._fire)
            self.timer.daemon = True
            self.timer.start()

    def _fire(self):
        with self.lock:
            a = self.ack
            self.pending = False
            self.timer = None
        self.sock.sendto(struct.pack("!I", a), self.peer)

    def flush(self):
        with self.lock:
            t = self.timer
        if t:
            t.join(self.delay + 0.2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9999)
    ap.add_argument("--loss", type=float, default=0.0)
    ap.add_argument("--output", default="received.txt")
    ap.add_argument("--rtt", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((args.host, args.port))

    nxt = 0
    buf = bytearray()
    peer = None
    acks = None

    print("listening", args.host, args.port, "loss=", args.loss)

    while nxt < 1024 * 1024:
        pkt, addr = s.recvfrom(8192)
        if peer is None:
            peer = addr
            acks = AckTimer(s, peer, args.rtt)
        elif addr != peer:
            continue

        if random.random() < args.loss:
            continue

        got = unpack(pkt)
        if not got:
            continue
        seq, body = got

        if seq < nxt:
            ov = nxt - seq
            if ov >= len(body):
                acks.schedule(nxt)
                continue
            body = body[ov:]
            seq = nxt

        if seq == nxt:
            buf.extend(body)
            nxt += len(body)

        acks.schedule(nxt)

    acks.flush()

    with open(args.output, "wb") as f:
        f.write(buf[: 1024 * 1024])

    s.close()
    print("saved", args.output)


if __name__ == "__main__":
    main()
