# bash would be annoying so this just runs the 3 sims and saves pngs

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
SRV = os.path.join(HERE, "tcp_server.py")
CLI = os.path.join(HERE, "tcp_client.py")
INFILE = os.path.join(HERE, "input_1mb.bin")
OUTDIR = os.path.join(HERE, "graphs")

# digits file everyone uses for this hw
INPUT_URL = "https://raw.githubusercontent.com/devfirejedi4/CSC364_Assignment_3/main/gistfile1.txt"
ONE_MB = 1024 * 1024


def pick_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def get_input_file():
    if os.path.isfile(INFILE) and os.path.getsize(INFILE) == ONE_MB:
        return

    data = None
    local = os.path.join(HERE, "gistfile1.txt")
    if os.path.isfile(local):
        print("found gistfile1.txt locally")
        with open(local, "rb") as f:
            data = f.read()
    if data is None:
        print("downloading input...")
        try:
            with urllib.request.urlopen(INPUT_URL, timeout=120) as r:
                data = r.read()
        except OSError as e:
            print("download broke:", e, "using random bytes instead")
            data = os.urandom(ONE_MB)

    if len(data) == ONE_MB - 1:
        data += b"\n"
    if len(data) < ONE_MB:
        data += b"\x00" * (ONE_MB - len(data))
    elif len(data) > ONE_MB:
        data = data[:ONE_MB]

    with open(INFILE, "wb") as f:
        f.write(data)


def one_run(loss, tag, seed):
    port = pick_port()
    mj, mpath = tempfile.mkstemp(suffix=".json")
    os.close(mj)
    oj, opath = tempfile.mkstemp(suffix=".bin")
    os.close(oj)

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
        print("server didnt start?")
        for p in (mpath, opath):
            try:
                os.unlink(p)
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


def make_pngs(mpath, tag, lbl):
    with open(mpath, encoding="utf-8") as f:
        m = json.load(f)["metrics"]

    plt.figure()
    plt.plot(m["rtt_index"], m["cwnd_packets"])
    plt.xlabel("time (in ~RTTs)")
    plt.ylabel("cwnd (pkts)")
    plt.title("cwnd vs time, loss=%s" % lbl)
    plt.grid(True)
    plt.savefig(os.path.join(OUTDIR, "cwnd_%s.png" % tag))
    plt.close()

    plt.figure()
    plt.plot(m["times_sec"], m["retrans_cumulative"])
    plt.xlabel("seconds")
    plt.ylabel("retransmissions (cumulative)")
    plt.title("retrans vs time, loss=%s" % lbl)
    plt.grid(True)
    plt.savefig(os.path.join(OUTDIR, "retrans_%s.png" % tag))
    plt.close()


def same_file(a, b):
    return hashlib.sha256(open(a, "rb").read()).digest() == hashlib.sha256(open(b, "rb").read()).digest()


def main():
    get_input_file()
    os.makedirs(OUTDIR, exist_ok=True)

    for loss, tag, seed in [(0.01, "1pct", 101), (0.10, "10pct", 102), (0.50, "50pct", 103)]:
        if tag == "50pct":
            print("50pct (slow)...")
        else:
            print(tag)
        got = one_run(loss, tag, seed)
        if not got:
            continue
        mp, out = got
        try:
            make_pngs(mp, tag, "%d%%" % int(loss * 100))
            print("  ok" if same_file(INFILE, out) else "  bad hash")
        finally:
            for p in (mp, out):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    print("wrote pngs ->", OUTDIR)


if __name__ == "__main__":
    main()
