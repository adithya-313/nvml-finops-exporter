# System Performance Ledger

## V1 MVP Baseline (Local Docker / Python Engine)
*Date: 2026-05-31*

### Methodology
- **Load Multiplier:** 5x (1s intervals)
- **Profiling Tools:** Go `pprof`, Python `tracemalloc`

### Metrics
- **Go Agent Peak Memory:** 2.16 MB (HeapAlloc)
- **Prometheus Scrape Latency:** 4.27 ms (avg)
- **Python Engine Execution Time:** 80 ms (avg, range 48–128 ms)
- **Python Engine Peak Memory:** 508.4 KB

### Bottleneck Analysis
- **Identified Chokepoint:** Python engine loop time (80 ms avg).
- **Root Cause:** ~75% of execution time blocked on sequential, synchronous HTTP I/O (4 Prometheus range queries per cycle).
- **Hardware Footprint:** Go Agent highly efficient (<5ms processing, 2MB heap).
