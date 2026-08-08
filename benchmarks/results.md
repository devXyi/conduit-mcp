Conduit benchmark results
Machine: Linux x86_64, Python 3.12.3
Warmup: 3 discarded iterations where applicable. Timed iterations: 30 (stdio: 10, given each spawns a process). Concurrent scenarios: 20 simultaneous sessions.
All calls are list_directory(".") against the same near-empty workspace, so every scenario is measuring transport/protocol/auth overhead, not tool work.
Scenario
n
mean (ms)
median (ms)
p95 (ms)
min (ms)
max (ms)
in-process (no I/O)
30
0.69
0.67
0.86
0.60
0.91
stdio (fresh session/call)
10
1036.66
1031.43
1101.65
999.16
1101.65
HTTP, sequential, no auth
30
5.59
5.43
6.85
4.69
6.94
HTTP, 20 concurrent, no auth
20
262.16
274.53
301.71
146.95
301.79
HTTP, sequential, WITH auth
30
8.72
5.88
46.34
5.11
69.02
HTTP, 20 concurrent, WITH auth
20
346.38
375.40
386.37
211.43
386.42