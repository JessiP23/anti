import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-file", required=True)
    parser.add_argument("--gateway-url", default="http://localhost:8000")
    parser.add_argument("--min-suspicious-flag-rate", type=float, default=0.8)
    parser.add_argument("--max-clean-flag-rate", type=float, default=0.2)
    return parser.parse_args()


async def run(
    sample_file: str,
    gateway_url: str,
    min_suspicious_flag_rate: float,
    max_clean_flag_rate: float,
) -> None:
    path = Path(sample_file)
    lines: list[str] = []
    if path.is_dir():
        for file in sorted(path.rglob("*.jsonl")):
            lines.extend(
                [line for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]
            )
    else:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts: Counter[str] = Counter()
    flagged: Counter[str] = Counter()
    failures = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for line in lines:
            record = json.loads(line)
            label = str(record["label"])
            event = record["event"]
            counts[label] += 1
            response = await client.post(f"{gateway_url}/v1/event", json=event)
            if response.status_code >= 400:
                failures += 1
                continue
            decision = response.json().get("decision", "")
            if decision in {"auto_flag", "auto_shadow_ban"}:
                flagged[label] += 1
    suspicious_count = max(1, counts.get("suspicious", 0))
    clean_count = max(1, counts.get("clean", 0))
    suspicious_rate = flagged.get("suspicious", 0) / suspicious_count
    clean_rate = flagged.get("clean", 0) / clean_count
    print(
        json.dumps(
            {
                "total_events": len(lines),
                "counts": counts,
                "flagged": flagged,
                "failures": failures,
                "suspicious_flag_rate": suspicious_rate,
                "clean_flag_rate": clean_rate,
            },
            default=dict,
        )
    )
    assert suspicious_rate >= min_suspicious_flag_rate
    assert clean_rate <= max_clean_flag_rate
    assert failures == 0


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        run(
            sample_file=args.sample_file,
            gateway_url=args.gateway_url,
            min_suspicious_flag_rate=args.min_suspicious_flag_rate,
            max_clean_flag_rate=args.max_clean_flag_rate,
        )
    )
