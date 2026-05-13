# CSC364 assignment 3 — TCP over UDP

This is the writeup for the “TCP over UDP” assignment (Reno-style cwnd, checksums, delayed ACKs to fake 100ms RTT, 500ms timeout, graphs at 1/10/50% loss).

## 1MB input file

The handout says to read the **1MB** file from the course link. That file is the big block of digits (same idea as `gistfile1.txt` people pass around for this class).

- Canonical copy I used: `https://raw.githubusercontent.com/devfirejedi4/CSC364_Assignment_3/main/gistfile1.txt`  
- `make_graphs.py` downloads that into `input_1mb.bin` the first time you run it (or uses `gistfile1.txt` if you drop it in this folder).  
- That mirror is **1048575 bytes** on disk; I pad **one newline** so the client always sees exactly **1048576** bytes like the spec.

If download fails it falls back to random 1MB so the code still runs, but then you’re not grading the real digits file.

## what the code does (maps to the rubric)

**Packets:** client sends 4-byte starting byte index + 2-byte checksum + up to 1024 bytes payload. Checksum = sum of payload bytes mod **65535** like the writeup. Server ACK is 4 bytes = **next expected byte** (cumulative ACK).

**Server:** `--loss` drops whole datagrams before parsing. Wrong checksum → drop. Only accepts in-order data when `seq == next_expected`. Out-of-order: ignore payload but still ACK `next_expected` so the sender sees **duplicate ACKs** (needed for fast retransmit).

**100ms RTT:** first datagram after idle starts a **100ms** timer; more datagrams before it fires only change the pending cumulative ACK value, timer does **not** restart (what the “first packet of the batch” hint was getting at). One ACK per timer fire.

**Client (Reno-ish):** `cwnd` starts at 1 packet, `ssthresh` 64. Slow start while `cwnd < ssthresh`: grow by how many full MSS got acked in that ACK (batched ACKs can ack a lot at once). Congestion avoidance: add `(segments_acked) / cwnd` per new ACK (~1 packet per RTT when one MSS per ACK).

**Fast retransmit:** 3 duplicate ACKs while data is outstanding → set `ssthresh = cwnd/2`, enter fast recovery, set `cwnd = ssthresh + 3`, immediately retransmit the oldest unacked chunk; more dup ACKs in recovery add 1 packet to `cwnd` each (Reno inflation). A **new** ACK that advances `send_base` exits recovery and sets `cwnd = ssthresh`.

**Timeout (500ms)** on oldest outstanding segment → `ssthresh = cwnd/2`, `cwnd = 1`, leave fast recovery, retransmit oldest.

**Retransmissions counted:** each time the oldest segment is sent again (timeout path or fast rtx path).

### lecture slide vs my code

The Reno diagram from lecture (timeouts vs triple dup ACK, slow start shaded vs congestion avoidance) is the **behavioral** picture: timeouts slam you back to `cwnd=1` and slow start; triple dup usually **cuts** the window and stays in congestion avoidance on the slide.

The actual **TCP Reno** fast-recovery rule people implement in textbooks is also the **“cwnd = ssthresh + 3”** inflation after the 3rd dup, not only “cut in half with no +3”. My code follows that **Reno fast recovery** version, which can look a little different from the simplified curve on one slide but matches what we were told to implement for Reno.

## graphs (only the 6 required ones)

The pdf objective text also mentions **RTT** in one sentence, but the required deliverables list is only:

- cwnd vs time in RTTs — 1%, 10%, 50%  
- cumulative retransmissions vs time — 1%, 10%, 50%

So I did **six** pngs under `graphs/` and did **not** add a separate third plot type for RTT.

What I saw: **retrans** curves go up basically linear with time (loss is ~constant so rtx rate is ~constant → cumulative is a line). Steeper at higher loss. **cwnd** often sits in a noisy band near 1–2 packets for long stretches with our loss + delayed ACK batching, so it does not always look like the pretty lecture figure; I still talk about loss keeping the window small and timeouts chopping `cwnd` in the analysis above.

## stuff that tripped me up

Cant buffer out-of-order on the server for this simplified model or you dont get dup ACKs the way we need.

Restarting the ACK timer on every packet changes the effective RTT and wrecks the cwnd plot timing.

## how to run

```bash
cd CSC364_Assignment_3
pip install -r requirements.txt
python3 make_graphs.py
```

`make_graphs.py` builds `input_1mb.bin`, runs three loss levels, checks sha256 of received file vs input, overwrites the six pngs. Server default output name is `received.txt` if you run `tcp_server.py` by hand.
