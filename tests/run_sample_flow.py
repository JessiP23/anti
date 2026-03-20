import argparse
import asyncio
import json
import random
import sys
from importlib import import_module
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-file", default="data/game_samples.jsonl")
    parser.add_argument("--gateway-url", default="http://localhost:8000")
    parser.add_argument("--clean-events", type=int, default=80)
    parser.add_argument("--suspicious-events", type=int, default=40)
    parser.add_argument("--min-suspicious-flag-rate", type=float, default=0.8)
    parser.add_argument("--max-clean-flag-rate", type=float, default=0.2)
    parser.add_argument("--use-live-sampler", action="store_true")
    parser.add_argument("--game-id", default="sample-game")
    parser.add_argument("--server-id", default="sample-server")
    parser.add_argument("--player-id", default="sample-player")
    parser.add_argument("--session-id", default="sample-session")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--sleep-ms", type=int, default=150)
    parser.add_argument("--sampler-output-dir", default="data/live_samples")
    return parser.parse_args()


def _build_raw_events(
    clean_events: int,
    suspicious_events: int,
    player_id: str,
    session_id: str,
) -> list[dict]:
    events: list[dict] = []
    for _ in range(clean_events):
        events.append(
            {
                "player_id": player_id,
                "session_id": session_id,
                "event_type": "player_moved",
                "payload": {"speed": random.uniform(250, 500), "position": [1, 2, 3]},
                "label": "clean",
                "sdk_version": "0.1.0",
            }
        )
        events.append(
            {
                "player_id": player_id,
                "session_id": session_id,
                "event_type": "hit_registered",
                "payload": {
                    "hit_zone": "body",
                    "distance_m": random.uniform(8, 35),
                    "server_validated": True,
                },
                "label": "clean",
                "sdk_version": "0.1.0",
            }
        )
    for _ in range(suspicious_events):
        events.append(
            {
                "player_id": player_id,
                "session_id": session_id,
                "event_type": "hit_registered",
                "payload": {
                    "hit_zone": "head",
                    "distance_m": random.uniform(95, 130),
                    "server_validated": True,
                },
                "label": "suspicious",
                "sdk_version": "0.1.0",
            }
        )
        events.append(
            {
                "player_id": player_id,
                "session_id": session_id,
                "event_type": "player_moved",
                "payload": {"speed": random.uniform(920, 1200), "position": [1, 2, 3]},
                "label": "suspicious",
                "sdk_version": "0.1.0",
            }
        )
    return events


async def _capture_via_live_sampler(args: argparse.Namespace) -> str:
    output_dir = Path(args.sampler_output_dir) / args.game_id / args.server_id
    if output_dir.exists():
        for file in output_dir.rglob("*.jsonl"):
            file.unlink()
    events = _build_raw_events(
        clean_events=args.clean_events,
        suspicious_events=args.suspicious_events,
        player_id=args.player_id,
        session_id=args.session_id,
    )
    batch_url = f"{args.gateway_url}/v1/live-sampler/{args.game_id}/{args.server_id}/batch"
    flush_url = f"{args.gateway_url}/v1/live-sampler/{args.game_id}/{args.server_id}/flush"
    status_url = f"{args.gateway_url}/v1/live-sampler/{args.game_id}/{args.server_id}/status"
    async with httpx.AsyncClient(timeout=15.0) as client:
        for index in range(0, len(events), args.batch_size):
            batch = events[index : index + args.batch_size]
            response = await client.post(batch_url, json={"events": batch})
            response.raise_for_status()
            if args.sleep_ms > 0:
                await asyncio.sleep(args.sleep_ms / 1000)
        flush_res = await client.post(flush_url)
        flush_res.raise_for_status()
        status_res = await client.get(status_url)
        status_res.raise_for_status()
        print(json.dumps(status_res.json()))
    return str(output_dir)


def main() -> None:
    generate_samples = import_module("tests.generate_game_samples").run
    validate_samples = import_module("tests.validate_game_samples").run
    args = parse_args()

    if args.use_live_sampler:
        sample_target = asyncio.run(_capture_via_live_sampler(args))
    else:
        path = Path(args.sample_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        generate_samples(
            output=args.sample_file,
            clean_events=args.clean_events,
            suspicious_events=args.suspicious_events,
        )
        sample_target = args.sample_file
    asyncio.run(
        validate_samples(
            sample_file=sample_target,
            gateway_url=args.gateway_url,
            min_suspicious_flag_rate=args.min_suspicious_flag_rate,
            max_clean_flag_rate=args.max_clean_flag_rate,
        )
    )


if __name__ == "__main__":
    main()
