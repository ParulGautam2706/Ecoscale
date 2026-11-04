"""Configurable defaults. Every value is an ASSUMPTION an admin can override in Settings.
Hardware power numbers are illustrative generic values, not vendor measurements."""

DEFAULT_SETTINGS = {
    "thresholds": {
        "alpha_cpu": 0.25,            # paper default: rolling CPU below 25%
        "beta_mem": 0.30,             # paper default: memory below 30%
        "sustained_fraction": 0.90,   # share of window that must satisfy the rule
        "idle_cpu": 0.02,             # paper default: <2% CPU
        "idle_net_mbit_s": 1.0,
        "idle_sustained_fraction": 0.95,
        "max_cpu_p95_after": 0.80,    # peak-protection (latency-sensitive workloads)
        "max_cpu_p95_after_batch": 0.95,  # flexible batch jobs are meant to run hot
        "max_mem_p95_after": 0.85,
        "shift_min_improvement": 0.20,  # paper default: >=20% lower carbon to recommend shifting
        "rolling_window_min": 15,
    },
    "weights": {"carbon": 0.40, "cost": 0.30, "latency": 0.20, "sla": 0.10},
    "limits": {
        "region_capacity_vcpu": 200,
        "data_gb": 50,
        "transfer_usd_per_gb": 0.02,
        "amortize_days": 30,
        "default_latency_limit_ms": 150,
        "max_shift_hours": 24,
        "max_cost_increase_pct": 10,   # recommendations may not raise cost by more than this
    },
    "energy": {
        "ram_w_per_gb": 0.375,        # from the reference paper
        "ram_idle_fraction": 0.5,
        "gpu_idle_w": 25.0,
        "gpu_peak_w": 250.0,
        "disk_max_w": 6.0,
        "disk_ref_mb_s": 500.0,
        "nic_max_w": 8.0,
        "nic_ref_mbit_s": 1000.0,
        "calibrated": False,
    },
    "monitoring": {"interval_s": 300},
}

# Illustrative region assumptions (NOT official figures). Replace with provider/grid data.
REGIONS = [
    # code, name, pue, price_multiplier, base gCO2e/kWh, diurnal amplitude, utc offset (h)
    ("us-east", "US East (N. Virginia)", 1.20, 1.00, 380.0, 0.15, -5.0),
    ("us-west", "US West (Oregon)", 1.20, 1.05, 240.0, 0.25, -8.0),
    ("eu-west", "EU West (Ireland)", 1.15, 1.10, 290.0, 0.20, 0.0),
    ("eu-north", "EU North (Stockholm)", 1.10, 1.00, 40.0, 0.10, 1.0),
    ("ap-south", "Asia Pacific South (Mumbai)", 1.40, 1.05, 680.0, 0.12, 5.5),
]

# Illustrative one-way latency (ms) between user region and serving region.
REGION_LATENCY_MS = {
    ("us-east", "us-west"): 65, ("us-east", "eu-west"): 80, ("us-east", "eu-north"): 105,
    ("us-east", "ap-south"): 190, ("us-west", "eu-west"): 135, ("us-west", "eu-north"): 150,
    ("us-west", "ap-south"): 215, ("eu-west", "eu-north"): 30, ("eu-west", "ap-south"): 120,
    ("eu-north", "ap-south"): 140,
}
SAME_REGION_LATENCY_MS = 5

# name, vcpu, mem_gb, gpu_count, idle_w, peak_w (CPU+platform), hourly_cost_usd
INSTANCE_TYPES = [
    ("gp.small", 2, 8, 0, 45, 120, 0.05),
    ("gp.medium", 4, 16, 0, 70, 200, 0.10),
    ("gp.large", 8, 32, 0, 110, 330, 0.20),
    ("gp.xlarge", 16, 64, 0, 190, 600, 0.40),
    ("gpu.large", 8, 61, 1, 150, 380, 0.90),
]


def region_latency(a: str, b: str) -> float:
    if a == b:
        return SAME_REGION_LATENCY_MS
    return REGION_LATENCY_MS.get((a, b), REGION_LATENCY_MS.get((b, a), 200))
