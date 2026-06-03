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

## V2 Async Refactor (Local Docker / AsyncIO + aiohttp)
*Date: 2026-05-31*

### Methodology
- **Same load profile:** 1s intervals, 4 Prometheus range queries per cycle
- **Change:** `asyncio.gather` fires all 4 queries concurrently; `aiohttp.ClientSession` for connection pooling
- **Profiling:** `time.perf_counter` loop timing

### Metrics
- **Async Loop Execution Time:** 5.6 ms (avg, range 3.5–9.9 ms, excl. cold-start)
- **Reduction vs Sync:** 93% (80 ms → 5.6 ms)

### Analysis
- `asyncio.gather` eliminated the sequential HTTP I/O bottleneck—queries now overlap in wall-clock time
- Persistent `aiohttp.ClientSession` avoided per-request TCP handshake overhead
- Circuit breaker remains stable across async boundary (OPEN→HALF_OPEN→OPEN transitions verified)

## V2 Enterprise Baseline (Docker / gRPC / Mahalanobis ML)
*Date: 2026-06-03*

### Methodology
- **Transport:** gRPC (Unary)
- **Math Payload:** Multi-Variate Covariance Matrix & Pseudo-Inverse (4D feature vectors)
- **NTP Drift Check:** Active (Mutex Locked)

### Metrics
- **Python Engine Execution Time:** 6.57 ms (avg steady-state post-calibration, 5 consecutive loops)
- **V1 to V2 Delta:** 91.8% reduction (80 ms → 6.57 ms)
- **First post-calibration loop (numpy cold-start):** 18.65 ms

### Bottleneck Analysis
- **System State:** The network I/O bottleneck was eradicated by gRPC. The primary time cost is now the CPU calculating the pseudo-inverse of the covariance matrix (`np.linalg.pinv`), which remains highly efficient and well under the 1-second system threshold.
