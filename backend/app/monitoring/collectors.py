"""Collectors. Local collector returns MEASURED utilization (psutil); energy is still ESTIMATED.
Kubernetes / cloud collectors would implement the same `collect()` contract later."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

import numpy as np
import psutil


class Collector(Protocol):
    def collect(self) -> dict: ...


class LocalCollector:
    origin = "measured"

    def __init__(self):
        self._net = psutil.net_io_counters()
        self._disk = psutil.disk_io_counters()
        self._t = datetime.now(timezone.utc).replace(tzinfo=None)

    def collect(self) -> dict:
        cpu = psutil.cpu_percent(interval=0.5) / 100.0
        mem = psutil.virtual_memory().percent / 100.0
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        dt = max((now - self._t).total_seconds(), 1e-3)
        net, disk = psutil.net_io_counters(), psutil.disk_io_counters()
        net_mbit = ((net.bytes_sent + net.bytes_recv) - (self._net.bytes_sent + self._net.bytes_recv)) * 8 / 1e6 / dt
        disk_mb = (((disk.read_bytes + disk.write_bytes) - (self._disk.read_bytes + self._disk.write_bytes)) / 1e6 / dt
                   if disk else 0.0)
        self._net, self._disk, self._t = net, disk, now
        return {"ts": now, "cpu": float(cpu), "mem": float(mem), "net_mbit_s": float(max(net_mbit, 0)),
                "disk_mb_s": float(max(disk_mb, 0)), "interval_s": 60.0}


def local_hardware() -> dict:
    return {"vcpu": psutil.cpu_count(logical=True) or 4,
            "mem_gb": round(psutil.virtual_memory().total / 1e9, 1)}
