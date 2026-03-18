from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import time

from interface.influx.api import get_measurement_data_range


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


def record_sensor_data_to_csv(name, seconds):
    """Record all available sensor data for `seconds` and export to `name`.csv."""
    duration = float(seconds)
    if duration <= 0:
        raise ValueError("seconds must be > 0")

    output_path = _normalize_output_path(name)

    start = datetime.now(timezone.utc)
    end = start + timedelta(seconds=duration)

    # Wait during the measurement window, then fetch exactly that time slice.
    while datetime.now(timezone.utc) < end:
        remaining = (end - datetime.now(timezone.utc)).total_seconds()
        time.sleep(min(0.2, max(remaining, 0.0)))

    df = get_measurement_data_range(start=start, stop=end)
    if not df.empty:
        df = df[_ordered_columns(list(df.columns))]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index_label="timestamp")
    return output_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="CSV file name (extension optional)")
    parser.add_argument("seconds", type=float, help="How long to record data")
    args = parser.parse_args()

    output = record_sensor_data_to_csv(args.name, args.seconds)
    print(f"Saved data to: {output}")


if __name__ == "__main__":
    main()
