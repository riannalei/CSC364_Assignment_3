# CSC364 assignment 3 — TCP-ish stuff over UDP

## what the code does

Packets from the client are 4 byte seq number + 2 byte checksum + up to 1024 bytes data. Checksum is sum of all data bytes mod 65535 (what the pdf said). Server sends back a 4 byte cumulative ack = next byte index it still needs.

Server drops packets randomly with `--loss` before it even looks at them. Bad checksum = drop too. It only writes bytes in order when `seq` matches what its waiting for. If something shows up ahead of that it throws away the payload but still acks the old `next` value so the client gets duplicate acks (needed for fast retransmit).

For the fake 100ms RTT I used a timer on the server side. First packet after idle starts a 100ms timer, more packets before it fires just update which ack youre gonna send, timer doesnt restart. Then one ack goes out. Thats kinda like delayed acks + fixed delay.

Client is supposed to be Reno-ish. cwnd starts at 1, ssthresh 64. New acks: slow start while cwnd < ssthresh (I add per MSS acked in one go bc acks can cover a lot at once). After that I add (segments_acked)/cwnd per ack for congestion avoidance.

3 dup acks -> cut ssthresh in half, cwnd = ssthresh+3, retransmit oldest segment, extra dup acks bump cwnd a bit in recovery. New ack that advances send_base ends recovery and cwnd goes to ssthresh.

500ms timeout on oldest outstanding -> ssthresh half, cwnd=1, rtx oldest. Retrans count = every time I resend that oldest chunk (timeout or fast rtx).

## what the graphs actually look like

I ran `make_graphs.py` and got the 6 pngs in `graphs/`.

The retrans plots are basically straight lines going up. That made sense to me bc loss rate is roughly constant the whole run so youre doing retransmissions at a kinda steady rate → cumulative count goes up linearly. Steeper slope at 10% than 1%, and 50% is way steeper / takes forever wall clock wise.

The cwnd plots are kinda ugly tbh — mostly a thick band between like 1 and 2 packets for a long time especially at 10% and 50%. At 1% theres a spike at the start then it drops and stays low. I think its bc theres a lot of loss + timeouts relative to how fast cwnd can grow, and the delayed ack batching means youre not getting nice smooth ack clocking like the textbook pictures. Also I only log when send_base/cwnd/retrans changes so when cwnd bounces between 1 and 2 a ton it fills in solid blue.

So yeah not perfect pretty sawteeth but it still shows the idea: more loss = window stays small and retransmissions pile up.

## bugs / things that annoyed me

Had to not buffer out of order on the server or you never get dup acks the right way.

Resetting the ack timer on every packet was wrong and messed up the RTT behavior.

## how to run graphs again

```bash
cd CSC364_Assignment_3
pip install -r requirements.txt
python3 make_graphs.py
```

If `input_1mb.bin` isnt there the script makes a random 1MB file. It checks sha at the end that received file matches.

If prof linked a specific 1MB file download that and replace `input_1mb.bin` (still has to be exactly 1048576 bytes).
