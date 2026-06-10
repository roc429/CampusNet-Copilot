import csv
from pathlib import Path

AP_ROLES = frozenset({"teaching_ap", "dorm_ap"})
LOAD_THRESHOLD = 0.8
_REPO_ROOT = Path(__file__).resolve().parents[4]
# 队长确认 CSV 在 test_data/；兼容旧路径仓库根目录 telemetry.csv
_DEFAULT_CSV_CANDIDATES = (
    _REPO_ROOT / "test_data" / "telemetry.csv",
    _REPO_ROOT / "telemetry.csv",
)


def resolve_telemetry_csv_path(settings_path: str = "") -> Path:
    if settings_path:
        return Path(settings_path).expanduser().resolve()
    for path in _DEFAULT_CSV_CANDIDATES:
        if path.is_file():
            return path
    return _DEFAULT_CSV_CANDIDATES[0]


def compute_telemetry_kpi(csv_path: Path) -> dict:
    if not csv_path.is_file():
        raise FileNotFoundError(f"找不到 telemetry 文件: {csv_path}")

    latest: dict[tuple[str, str], dict[str, str]] = {}

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "dpid", "port", "role", "throughput_bps", "load", "loss"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            missing = required - set(reader.fieldnames or [])
            raise ValueError(f"telemetry.csv 缺少字段: {', '.join(sorted(missing))}")

        for row in reader:
            key = (row["dpid"], row["port"])
            ts = float(row["timestamp"])
            prev = latest.get(key)
            if prev is None or ts >= float(prev["timestamp"]):
                latest[key] = row

    if not latest:
        return {
            "avgLoadPct": 0.0,
            "peakApLoadPct": 0.0,
            "totalThroughputMbps": 0.0,
            "abnormalPortCount": 0,
            "portCount": 0,
            "updatedAt": None,
            "updatedAtIso": None,
        }

    snapshots = list(latest.values())
    loads = [float(row["load"]) for row in snapshots]
    throughputs = [float(row["throughput_bps"]) for row in snapshots]
    ap_loads = [float(row["load"]) for row in snapshots if row.get("role") in AP_ROLES]

    abnormal = sum(
        1
        for row in snapshots
        if float(row["load"]) >= LOAD_THRESHOLD or float(row["loss"]) > 0
    )

    latest_row = max(snapshots, key=lambda row: float(row["timestamp"]))

    return {
        "avgLoadPct": round(sum(loads) / len(loads) * 100, 2),
        "peakApLoadPct": round(max(ap_loads) * 100, 2) if ap_loads else 0.0,
        "totalThroughputMbps": round(sum(throughputs) / 1_000_000, 2),
        "abnormalPortCount": abnormal,
        "portCount": len(snapshots),
        "updatedAt": float(latest_row["timestamp"]),
        "updatedAtIso": latest_row.get("timestamp_iso"),
    }
