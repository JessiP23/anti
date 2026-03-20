import argparse
import random
from pathlib import Path

from anticheat_sdk import AntiCheatClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--clean-events", type=int, default=80)
    parser.add_argument("--suspicious-events", type=int, default=40)
    return parser.parse_args()


def run(output: str, clean_events: int, suspicious_events: int) -> None:
    path = Path(output)
    if path.exists():
        path.unlink()
    client = AntiCheatClient(
        game_id="sample-game",
        server_id="sample-server",
        player_id="sample-player",
        session_id="sample-session",
        gateway_url="http://localhost:8000",
    )
    session = client.new_session()
    for _ in range(clean_events):
        speed = random.uniform(250, 500)
        session.capture_sample(
            event_type="player_moved",
            payload={"speed": speed, "position": [1, 2, 3], "velocity": [1, 0, 0]},
            sample_path=output,
            label="clean",
        )
        session.capture_sample(
            event_type="hit_registered",
            payload={
                "hit_zone": "body",
                "distance_m": random.uniform(8, 35),
                "server_validated": True,
            },
            sample_path=output,
            label="clean",
        )
    for _ in range(suspicious_events):
        session.capture_sample(
            event_type="hit_registered",
            payload={
                "hit_zone": "head",
                "distance_m": random.uniform(95, 130),
                "server_validated": True,
            },
            sample_path=output,
            label="suspicious",
        )
        session.capture_sample(
            event_type="player_moved",
            payload={
                "speed": random.uniform(920, 1200),
                "position": [1, 2, 3],
                "velocity": [8, 0, 0],
            },
            sample_path=output,
            label="suspicious",
        )
    print(path.resolve())
    print(path.stat().st_size)


if __name__ == "__main__":
    args = parse_args()
    run(
        output=args.output,
        clean_events=args.clean_events,
        suspicious_events=args.suspicious_events,
    )
