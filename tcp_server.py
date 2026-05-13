# CSC364 A3 server - receives chunks, checks checksum, drops randomly, delayed ACKs

import argparse
import random
import socket
import struct
import threading

HDR = 6  # 4 seq + 2 checksum
MSS = 1024
TOTAL = 1024 * 1024


def cksum(payload):
    return sum(payload) % 65535


def unpack(buf):
    if len(buf) < HDR:
        return None
    seq, got_c = struct.unpack("!IH", buf[:HDR])
    body = buf[HDR:]
    if cksum(body) != got_c:
        return None
    return seq, body


class AckDelayer:
    # first pkt after idle arms timer; more pkts before fire just update ack value (assignment RTT thing)
    def __init__(self, sock, peer, delay):
        self.sock = sock
        self.peer = peer
        self.delay = delay
        self.lock = threading.Lock()
        self.timer = None
        self.busy = False
        self.ackval = 0

    def push(self, ack):
        with self.lock:
            self.ackval = ack
            if self.busy:
                return
            self.busy = True
            self.timer = threading.Timer(self.delay, self._go)
            self.timer.daemon = True
            self.timer.start()

    def _go(self):
        with self.lock:
            a = self.ackval
            self.busy = False
            self.timer = None
        self.sock.sendto(struct.pack("!I", a), self.peer)

    def wait_done(self):
        # make sure last ack goes out before we exit
        t = None
        with self.lock:
            t = self.timer
        if t:
            t.join(self.delay + 0.2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9999)
    ap.add_argument("--loss", type=float, default=0.0)
    ap.add_argument("--output", default="received.bin")
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
    acker = None

    print("listening", args.host, args.port, "loss=", args.loss)

    while nxt < TOTAL:
        pkt, addr = s.recvfrom(8192)
        if peer is None:
            peer = addr
            acker = AckDelayer(s, peer, args.rtt)
        elif addr != peer:
            continue

        if random.random() < args.loss:
            continue

        got = unpack(pkt)
        if got is None:
            continue
        seq, body = got

        if seq < nxt:
            # already had this part
            overlap = nxt - seq
            if overlap >= len(body):
                acker.push(nxt)
                continue
            body = body[overlap:]
            seq = nxt

        if seq == nxt:
            buf.extend(body)
            nxt += len(body)
        # if seq > nxt: out of order, ignore data but still ack nxt (dup ack)

        acker.push(nxt)

    acker.wait_done()

    with open(args.output, "wb") as f:
        f.write(buf[:TOTAL])

    s.close()
    print("saved", args.output)


if __name__ == "__main__":
    main()
