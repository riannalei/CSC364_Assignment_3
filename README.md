# CSC364 — Assignment 3

TCP-ish congestion control over UDP: `tcp_client.py`, `tcp_server.py`.

**writeup:** [REPORT.md](REPORT.md)

**input:** `make_graphs.py` downloads the class digits file from  
https://raw.githubusercontent.com/devfirejedi4/CSC364_Assignment_3/main/gistfile1.txt  
(or uses local `gistfile1.txt` if you put it here). Saves as `input_1mb.bin` (gitignored).

**Plots:**

```bash
pip install -r requirements.txt
python3 make_graphs.py
```

PNG output: `graphs/` (six files: cwnd + retrans at 1%, 10%, 50% loss).
