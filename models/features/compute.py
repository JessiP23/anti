from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from .schema import PlayerEvent, SummaryFeatures


def compute_timing_features(events: Sequence[PlayerEvent]) -> dict[str, float]:
    shots = [event for event in events if event.event_type == "shot_fired"]
    if len(shots) < 2:
        return {"trigger_interval_cv": 0.0, "burst_autocorr": 0.0}
    timestamps = np.array([shot.timestamp_ms for shot in shots], dtype=np.float64)
    intervals = np.diff(timestamps)
    interval_mean = float(intervals.mean()) if intervals.size else 0.0
    interval_std = float(intervals.std()) if intervals.size else 0.0
    cv = interval_std / interval_mean if interval_mean > 0 else 0.0
    if intervals.size < 3:
        autocorr = 0.0
    else:
        left = intervals[:-1]
        right = intervals[1:]
        left_std = float(left.std())
        right_std = float(right.std())
        if left_std == 0 or right_std == 0:
            autocorr = 0.0
        else:
            autocorr = float(np.corrcoef(left, right)[0, 1])
    return {"trigger_interval_cv": cv, "burst_autocorr": autocorr}


def compute_movement_features(events: Sequence[PlayerEvent]) -> dict[str, float]:
    moved = [event for event in events if event.event_type == "player_moved"]
    if not moved:
        return {
            "avg_speed": 0.0,
            "max_speed": 0.0,
            "movement_entropy": 0.0,
            "path_curvature_var": 0.0,
            "strafe_period_detected": 0.0,
        }
    speeds = np.array([float(event.payload.get("speed", 0.0)) for event in moved], dtype=np.float64)
    bins = np.histogram(speeds, bins=8)[0]
    total = float(bins.sum())
    entropy = 0.0
    if total > 0:
        probabilities = bins / total
        entropy = float(-np.sum([p * math.log(p) for p in probabilities if p > 0]))
    return {
        "avg_speed": float(np.mean(speeds)),
        "max_speed": float(np.max(speeds)),
        "movement_entropy": entropy,
        "path_curvature_var": float(np.var(speeds)),
        "strafe_period_detected": 0.0,
    }


def compute_aim_features(events: Sequence[PlayerEvent]) -> dict[str, float]:
    frames = [event for event in events if event.event_type == "input_frame"]
    hits = [event for event in events if event.event_type == "hit_registered"]
    if not frames:
        base = {
            "snap_velocity_p95": 0.0,
            "aim_jitter_variance": 0.0,
            "pre_shot_correction_avg": 0.0,
            "recoil_entropy": 0.0,
        }
    else:
        deltas = np.array(
            [event.payload.get("mouse_delta", [0.0, 0.0]) for event in frames],
            dtype=np.float64,
        )
        frame_ms = np.array([max(1, int(event.payload.get("frame_ms", 16))) for event in frames])
        magnitude = np.linalg.norm(deltas, axis=1)
        velocity = magnitude / frame_ms * 1000
        base = {
            "snap_velocity_p95": float(np.percentile(velocity, 95)),
            "aim_jitter_variance": float(np.var(magnitude)),
            "pre_shot_correction_avg": float(np.mean(magnitude)),
            "recoil_entropy": float(np.var(velocity)),
        }
    headshots = [hit for hit in hits if hit.payload.get("hit_zone") == "head"]
    total_hits = len(hits) if hits else 1
    base["headshot_rate"] = float(len(headshots) / total_hits)
    return base


def build_feature_vector(
    events: Sequence[PlayerEvent],
    summary: SummaryFeatures | None = None,
) -> np.ndarray:
    if summary is not None:
        values = [
            summary.headshot_rate,
            summary.avg_reaction_time_ms,
            summary.snap_velocity_p95,
            summary.aim_jitter_variance,
            summary.pre_shot_correction_avg,
            summary.recoil_entropy,
            summary.trigger_interval_cv,
            summary.burst_autocorr,
            float(summary.shots_fired),
            float(summary.hits_registered),
            summary.avg_speed,
            summary.max_speed,
            summary.movement_entropy,
            summary.strafe_period_detected,
            summary.path_curvature_var,
            float(summary.kills),
            float(summary.deaths),
            float(summary.assists),
            float(summary.playtime_seconds),
        ]
    else:
        merged: dict[str, float] = {}
        merged.update(compute_aim_features(events))
        merged.update(compute_timing_features(events))
        merged.update(compute_movement_features(events))
        values = [
            merged.get("headshot_rate", 0.0),
            0.0,
            merged.get("snap_velocity_p95", 0.0),
            merged.get("aim_jitter_variance", 0.0),
            merged.get("pre_shot_correction_avg", 0.0),
            merged.get("recoil_entropy", 0.0),
            merged.get("trigger_interval_cv", 0.0),
            merged.get("burst_autocorr", 0.0),
            float(len([event for event in events if event.event_type == "shot_fired"])),
            float(len([event for event in events if event.event_type == "hit_registered"])),
            merged.get("avg_speed", 0.0),
            merged.get("max_speed", 0.0),
            merged.get("movement_entropy", 0.0),
            merged.get("strafe_period_detected", 0.0),
            merged.get("path_curvature_var", 0.0),
            0.0,
            0.0,
            0.0,
            0.0,
        ]
    values.extend([0.0] * (48 - len(values)))
    return np.array(values, dtype=np.float32)
