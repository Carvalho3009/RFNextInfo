"""Registra e avalia o Working Set do RF QOL em um ensaio prolongado."""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MIB = 1024 * 1024
DEFAULT_TARGET_BYTES = 768 * MIB
DEFAULT_HARD_LIMIT_BYTES = 1024 * MIB
DEFAULT_MAX_SLOPE_BYTES_PER_HOUR = 10 * MIB
MIN_BUDGET_MIB = 256
MAX_BUDGET_MIB = 2048
BUDGET_STEP_MIB = 128


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = (
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    )


@dataclass(frozen=True)
class MemorySample:
    elapsed_seconds: float
    working_set_bytes: int


def _working_set_bytes(pid: int) -> int:
    if os.name != "nt":
        raise RuntimeError("o ensaio de Working Set exige Windows")
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    kernel32.OpenProcess.argtypes = (
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_ulong,
    )
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    psapi.GetProcessMemoryInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_ProcessMemoryCounters),
        ctypes.c_ulong,
    )
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    handle = kernel32.OpenProcess(0x0400 | 0x0010, 0, int(pid))
    if not handle:
        raise RuntimeError(f"não foi possível abrir o processo {pid}")
    try:
        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        ):
            raise RuntimeError(f"não foi possível ler a memória do processo {pid}")
        return int(counters.WorkingSetSize)
    finally:
        kernel32.CloseHandle(handle)


def _linear_slope_bytes_per_hour(samples: list[MemorySample]) -> float:
    if len(samples) < 2:
        return 0.0
    average_x = sum(item.elapsed_seconds for item in samples) / len(samples)
    average_y = sum(item.working_set_bytes for item in samples) / len(samples)
    denominator = sum(
        (item.elapsed_seconds - average_x) ** 2 for item in samples
    )
    if denominator <= 0:
        return 0.0
    slope_per_second = sum(
        (item.elapsed_seconds - average_x)
        * (item.working_set_bytes - average_y)
        for item in samples
    ) / denominator
    return slope_per_second * 3600


def analyze_samples(
    samples: list[MemorySample],
    *,
    warmup_seconds: float = 30 * 60,
    tail_seconds: float = 4 * 60 * 60,
    target_bytes: int = DEFAULT_TARGET_BYTES,
    hard_limit_bytes: int = DEFAULT_HARD_LIMIT_BYTES,
    max_slope_bytes_per_hour: int = DEFAULT_MAX_SLOPE_BYTES_PER_HOUR,
) -> dict[str, object]:
    if not samples:
        raise ValueError("o ensaio não possui amostras")
    ordered = sorted(samples, key=lambda item: item.elapsed_seconds)
    after_warmup = [
        item for item in ordered if item.elapsed_seconds >= warmup_seconds
    ] or ordered
    final_elapsed = ordered[-1].elapsed_seconds
    tail_start = max(warmup_seconds, final_elapsed - tail_seconds)
    tail = [item for item in ordered if item.elapsed_seconds >= tail_start]
    peak = max(item.working_set_bytes for item in after_warmup)
    final = ordered[-1].working_set_bytes
    slope = _linear_slope_bytes_per_hour(tail)
    hard_limit_ok = peak <= hard_limit_bytes
    slope_ok = slope <= max_slope_bytes_per_hour
    return {
        "samples": len(ordered),
        "duration_seconds": round(final_elapsed, 3),
        "warmup_seconds": warmup_seconds,
        "tail_seconds": tail_seconds,
        "peak_working_set_bytes": peak,
        "final_working_set_bytes": final,
        "tail_slope_bytes_per_hour": round(slope, 3),
        "target_bytes": target_bytes,
        "hard_limit_bytes": hard_limit_bytes,
        "max_slope_bytes_per_hour": max_slope_bytes_per_hour,
        "target_exceeded": peak > target_bytes,
        "hard_limit_ok": hard_limit_ok,
        "slope_ok": slope_ok,
        "passed": hard_limit_ok and slope_ok,
    }


def run_monitor(
    pid: int,
    *,
    duration_seconds: float,
    interval_seconds: float,
    output: Path,
) -> list[MemorySample]:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    samples: list[MemorySample] = []
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("observed_at", "elapsed_seconds", "working_set_bytes"))
        while True:
            elapsed = time.monotonic() - started
            working_set = _working_set_bytes(pid)
            sample = MemorySample(elapsed, working_set)
            samples.append(sample)
            writer.writerow((
                datetime.now(timezone.utc).isoformat(),
                f"{elapsed:.3f}",
                working_set,
            ))
            handle.flush()
            if elapsed >= duration_seconds:
                return samples
            time.sleep(min(interval_seconds, duration_seconds - elapsed))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Monitora a memória do RF QOL sem controlar sua interface."
    )
    parser.add_argument("--pid", type=int, required=True, help="PID do RF QOL")
    parser.add_argument("--hours", type=float, default=10.0)
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument(
        "--budget-mib",
        type=int,
        default=DEFAULT_TARGET_BYTES // MIB,
        help="Mesmo orçamento de RAM escolhido nas Configurações",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("memory-soak.csv")
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.pid <= 0 or args.hours <= 0 or args.interval <= 0:
        raise SystemExit("PID, duração e intervalo devem ser positivos")
    if (
        not MIN_BUDGET_MIB <= args.budget_mib <= MAX_BUDGET_MIB
        or (args.budget_mib - MIN_BUDGET_MIB) % BUDGET_STEP_MIB
    ):
        raise SystemExit(
            f"O orçamento deve ficar entre {MIN_BUDGET_MIB} e "
            f"{MAX_BUDGET_MIB} MiB, em passos de {BUDGET_STEP_MIB} MiB"
        )
    samples = run_monitor(
        args.pid,
        duration_seconds=args.hours * 3600,
        interval_seconds=args.interval,
        output=args.output,
    )
    budget_bytes = args.budget_mib * MIB
    result = analyze_samples(
        samples,
        target_bytes=budget_bytes,
        hard_limit_bytes=budget_bytes,
    )
    result.update({
        "pid": args.pid,
        "budget_mib": args.budget_mib,
        "requested_hours": args.hours,
        "complete": samples[-1].elapsed_seconds >= args.hours * 3600,
        "sample_file": str(args.output.resolve()),
    })
    summary = args.output.with_suffix(".summary.json")
    summary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] and result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
