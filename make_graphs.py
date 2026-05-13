# for class: run server+client at 3 loss rates, dump plots into graphs/

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
SRV = os.path.join(HERE, "tcp_server.py")
CLI = os.path.join(HERE, "tcp_client.py")
INFILE = os.path.join(HERE, "input_1mb.bin")
OUTDIR = os.path.join(HERE, "graphs")


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def need_input():
    if os.path.isfile(INFILE) and os.path.getsize(INFILE) == 1024 * 1024:
        return
    print("making 1MB test file...")
    with open(INFILE, "wb") as f:
        f.write(os.urandom(1024 * 1024))


def run_pair(loss, tag, seed):
    port = free_port()
    mfd, mpath = tempfile.mkstemp(suffix=".json")
    os.close(mfd)
    ofd, opath = tempfile.mkstemp(suffix=".bin")
    os.close(ofd)

    srv = subprocess.Popen(
        [
            sys.executable,
            SRV,
            "--port",
            str(port),
            "--loss",
            str(loss),
            "--output",
            opath,
            "--rtt",
            "0.1",
            "--seed",
            str(seed),
        ],
        cwd=HERE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.3)
    if srv.poll() is not None:
        print("server died on startup??")
        try:
            os.unlink(mpath)
            os.unlink(opath)
        except OSError:
            pass
        return None

    try:
        subprocess.run(
            [
                sys.executable,
                CLI,
                "--port",
                str(port),
                "--file",
                INFILE,
                "--metrics",
                mpath,
                "--loss-label",
                "%d%%" % int(loss * 100),
            ],
            cwd=HERE,
            check=True,
        )
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=3)
        except subprocess.TimeoutExpired:
            srv.kill()

    return mpath, opath


def draw_plots(metrics_path, tag, loss_label):
    with open(metrics_path) as f:
        doc = json.load(f)
    m = doc["metrics"]

    x = m["rtt_index"]
    y = m["cwnd_packets"]
    plt.figure()
    plt.plot(x, y)
    plt.xlabel("time (in ~RTTs)")
    plt.ylabel("cwnd (pkts)")
    plt.title("cwnd vs time, loss=%s" % loss_label)
    plt.grid(True)
    plt.savefig(os.path.join(OUTDIR, "cwnd_%s.png" % tag))
    plt.close()

    t = m["times_sec"]
    r = m["retrans_cumulative"]
    plt.figure()
    plt.plot(t, r)
    plt.xlabel("seconds")
    plt.ylabel("retransmissions (cumulative)")
    plt.title("retrans vs time, loss=%s" % loss_label)
    plt.grid(True)
    plt.savefig(os.path.join(OUTDIR, "retrans_%s.png" % tag))
    plt.close()


def sha_ok(a, b):
    ha = hashlib.sha256(open(a, "rb").read()).hexdigest()
    hb = hashlib.sha256(open(b, "rb").read()).hexdigest()
    return ha == hb


def main():
    need_input()
    os.makedirs(OUTDIR, exist_ok=True)

    runs = [
        (0.01, "1pct", 101),
        (0.10, "10pct", 102),
        (0.50, "50pct", 103),
    ]

    for loss, tag, seed in runs:
        if tag == "50pct":
            print("running 50pct (takes a while)...")
        else:
            print("running", tag)
        got = run_pair(loss, tag, seed)
        if not got:
            continue
        mp, out = got
        try:
            lbl = "%d%%" % int(loss * 100)
            draw_plots(mp, tag, lbl)
            if sha_ok(INFILE, out):
                print("  ok")
            else:
                print("  hash mismatch??")
        finally:
            try:
                os.unlink(mp)
            except OSError:
                pass
            try:
                os.unlink(out)
            except OSError:
                pass

    print("saved pngs in", OUTDIR)


if __name__ == "__main__":
    main()
