"""Performance benchmarking script for Aletheia platform."""

import asyncio
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def benchmark_endpoint(url: str, num_requests: int = 100) -> dict:
    """Benchmark a single endpoint."""
    errors = 0

    def request():
        start = time.time()
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
                return (time.time() - start) * 1000
        except Exception:
            nonlocal errors
            errors += 1
            return None

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(request, range(num_requests)))

    valid_times = [r for r in results if r is not None]

    if not valid_times:
        return {"error_rate": 100, "status": "failed"}

    return {
        "avg_ms": statistics.mean(valid_times),
        "p50_ms": statistics.median(valid_times),
        "p95_ms": sorted(valid_times)[int(len(valid_times) * 0.95)],
        "p99_ms": sorted(valid_times)[int(len(valid_times) * 0.99)],
        "min_ms": min(valid_times),
        "max_ms": max(valid_times),
        "error_rate": (errors / num_requests) * 100,
        "requests_per_second": num_requests / sum(valid_times) * 1000,
    }


async def main():
    base_url = "http://localhost:8000"

    print("=" * 50)
    print("Aletheia Platform Benchmark")
    print("=" * 50)

    endpoints = [
        ("/health", "Health Check"),
        ("/api/workbench", "Workbench"),
        ("/api/agent/roles", "Agent Roles"),
    ]

    for path, name in endpoints:
        url = base_url + path
        print(f"\nBenchmarking {name} ({path})...")
        result = benchmark_endpoint(url, num_requests=50)

        if result["error_rate"] > 0:
            print(f"  Error rate: {result['error_rate']:.1f}%")
        else:
            print(f"  Avg: {result['avg_ms']:.2f}ms")
            print(f"  P95: {result['p95_ms']:.2f}ms")
            print(f"  P99: {result['p99_ms']:.2f}ms")
            print(f"  Throughput: {result['requests_per_second']:.1f} req/s")


if __name__ == "__main__":
    asyncio.run(main())
