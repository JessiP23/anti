import math
from collections import deque
from dataclasses import dataclass, field


@dataclass
class LocalScorer:
    max_speed: float = 800.0
    shot_intervals: deque[float] = field(default_factory=lambda: deque(maxlen=100))
    aim_deltas: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=200))
    speeds: deque[float] = field(default_factory=lambda: deque(maxlen=100))
    last_shot_ms: float = 0.0

    def on_shot_fired(self, timestamp_ms: float) -> None:
        if self.last_shot_ms > 0:
            self.shot_intervals.append(timestamp_ms - self.last_shot_ms)
        self.last_shot_ms = timestamp_ms

    def on_mouse_move(self, dx: float, dy: float) -> None:
        self.aim_deltas.append((dx, dy))

    def on_move(self, speed: float) -> None:
        self.speeds.append(speed)

    def compute_risk_score(self) -> float:
        signals: list[float] = []
        if len(self.shot_intervals) >= 10:
            mean = sum(self.shot_intervals) / len(self.shot_intervals)
            variance = sum((x - mean) ** 2 for x in self.shot_intervals) / len(self.shot_intervals)
            std = math.sqrt(variance)
            cv = std / mean if mean > 0 else 0.0
            signals.append(max(0.0, 1.0 - (cv / 0.05)))
        if len(self.aim_deltas) >= 20:
            max_snap = max(math.sqrt(dx**2 + dy**2) for dx, dy in self.aim_deltas)
            if max_snap > 3000:
                signals.append(min(1.0, max_snap / 5000))
        if len(self.speeds) >= 10:
            max_speed = max(self.speeds)
            if max_speed > self.max_speed * 1.05:
                signals.append(min(1.0, (max_speed - self.max_speed) / self.max_speed))
        return max(signals) if signals else 0.0
