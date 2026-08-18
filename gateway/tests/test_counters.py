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
