from datetime import datetime, timezone
from pathlib import Path
import time
import pandas as pd

from interface.influx.api import get_measurement_data


def _normalize_output_path(name):
    output = Path(name)
    if output.suffix.lower() != ".csv":
        output = output.with_suffix(".csv")
    return output


def _ordered_columns(columns):
    preferred_order = [
        "setpoint_position_%",
        "feedback_position_%",
        "rotation_direction",
        "internal_temperature_deg_C",
        "motor_torque_Nmm",
        "power_W",
        "test_number",
    ]
    preferred = [col for col in preferred_order if col in columns]
    remaining = [col for col in columns if col not in preferred]
    return preferred + remaining


def record_sensor_data_to_csv(name, seconds, poll_interval=0.2):
    """Record all available sensor data for `seconds` and export to `name`.csv."""
    duration = float(seconds)
    if duration <= 0:
        raise ValueError("seconds must be > 0")
    sample_every = float(poll_interval)
    if sample_every <= 0:
        raise ValueError("poll_interval must be > 0")

    output_path = _normalize_output_path(name)

    # Poll repeatedly during the window so we do not depend on exact time-range queries.
    end_monotonic = time.monotonic() + duration
    collected_frames = []

    while time.monotonic() < end_monotonic:
        latest = get_measurement_data(n=1)
        if not latest.empty:
            collected_frames.append(latest)

        remaining = end_monotonic - time.monotonic()
        if remaining > 0:
            time.sleep(min(sample_every, remaining))

    if collected_frames:
        df = pd.concat(collected_frames).sort_index()
        # Keep only one row per timestamp if the same sample was read multiple times.
        df = df[~df.index.duplicated(keep="last")]
    else:
        df = pd.DataFrame()

    if not df.empty:
        df = df[_ordered_columns(list(df.columns))]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index_label="timestamp")
    return output_path
