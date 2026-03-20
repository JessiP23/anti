import argparse
import asyncio
import sys
from importlib import import_module
from pathlib import Path

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
    return parser.parse_args()


def main() -> None:
    generate_samples = import_module("tests.generate_game_samples").run
    validate_samples = import_module("tests.validate_game_samples").run
    args = parse_args()
    path = Path(args.sample_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    generate_samples(
        output=args.sample_file,
        clean_events=args.clean_events,
        suspicious_events=args.suspicious_events,
    )
    asyncio.run(
        validate_samples(
            sample_file=args.sample_file,
            gateway_url=args.gateway_url,
            min_suspicious_flag_rate=args.min_suspicious_flag_rate,
            max_clean_flag_rate=args.max_clean_flag_rate,
        )
    )


if __name__ == "__main__":
    main()
