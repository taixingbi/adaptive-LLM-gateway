from app.counters import MemoryCounters, QuotaCounters


def test_minute_snapshot_and_admit() -> None:
    counters = QuotaCounters(MemoryCounters())
    snap = counters.snapshot("tenant-007")
    assert snap["tenant_tpm"] == 0
    counters.record_admit("tenant-007", 500)
    snap = counters.snapshot("tenant-007")
    assert snap["tenant_tpm"] == 500
    assert snap["tenant_rpm"] == 1
    assert snap["tenant_concurrency"] == 1
    assert snap["platform_tpm"] == 500
    counters.release_concurrency("tenant-007")
    assert counters.snapshot("tenant-007")["tenant_concurrency"] == 0


def test_token_bucket_refills_instead_of_minute_reset() -> None:
    import time

    counters = QuotaCounters(MemoryCounters())
    assert counters.snapshot("tenant-007", tenant_tpm_limit=6000)["tenant_bucket"] == 6000
    counters.record_admit("tenant-007", 5500, tenant_tpm_limit=6000)
    after = counters.snapshot("tenant-007", tenant_tpm_limit=6000)["tenant_bucket"]
    assert 0 < after < 600
    tokens, _ = counters._mem_buckets["bucket:tenant:007"]
    counters._mem_buckets["bucket:tenant:007"] = (tokens, time.time() - 30)
    refilled = counters.snapshot("tenant-007", tenant_tpm_limit=6000)["tenant_bucket"]
    assert refilled > tokens + 2000
