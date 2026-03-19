# StartHack 2026 - Unlocking Insights from Belimo Actuator Data for Smart Building Solutions

This project controls a Belimo actuator through InfluxDB and provides real-time monitoring, testing, and diagnostics.

The system is built for real-world deployment conditions and focuses on:
- live visualization of actuator behavior,
- power and torque anomaly detection,
- movement-churn analysis to identify unnecessary oscillation and optimization opportunities.

## What This Project Does

1. Writes actuator setpoint commands to InfluxDB.
2. Reads live telemetry from InfluxDB.
3. Runs waveform-based test patterns (constant, sine, triangle, square) to visualize test behavior and demonstrate how the same analysis approach can be applied to production-like control patterns.
4. Builds baseline performance profiles for power and torque.
5. Detects anomalies when power or torque exceed learned normal behavior.
6. Detects overactive movement/chatter (too many moves or frequent close-state reversals).

## System Architecture

- Raspberry Pi hosts InfluxDB and an actuator logger/bridge.
- Client app (this repository) writes commands to `_process` and reads telemetry from `measurements`.
- Streamlit dashboard shows live metrics, charts, controls, test status, anomaly results, and movement optimization reports.

## Repository Structure

```text
demo/
	app.py                     Streamlit dashboard
	main.py                    CLI runner
	entrypoint.sh              Selects UI vs CLI mode
	Dockerfile                 Container build
	interface/
		influx/
			api.py                 Influx read/write + retry/caching logic
		analytics.py             Profiling, anomaly detection, movement-churn detection
	signal/
		waveform.py              Waveform generation (constant/sine/triangle/square)
```

## Key Features

### 1) Live Control and Visualization
- Set waveform, bias, amplitude, and frequency.
- Start/stop run mode or test mode.
- View live charts for setpoint, feedback, temperature, torque, and power.

### 2) Robust Data Handling
- Retry logic for read/write operations.
- Fast-fail behavior for unstable networks.
- Cached fallback when telemetry fetch fails.

### 3) Power and Torque Anomaly Detection
- Learns baseline profiles from successful runs.
- Flags outliers against percentile-based thresholds.
- Logs detections and supports CSV export.

### 4) Movement Churn Detection (Optimization Feature)
- User-defined thresholds for movement sensitivity.
- Detects high movement rate (moves per minute).
- Detects close-state chatter via direction-change analysis.
- Reports optimization hints (deadband/hysteresis, rate limiting, dwell time).

## Quick Start

## Prerequisites
- Docker
- Access to the Belimo/Raspberry Pi network
- Reachable InfluxDB endpoint configured in `demo/interface/influx/api.py`

## Build

From project root:

```bash
cd demo
docker build -t demo .
```

## Run Streamlit Dashboard

```bash
docker run --rm -it -p 8501:8501 -v ${PWD}:/work demo
```

Open:

- http://localhost:8501

## Run CLI Mode

```bash
docker run --rm -it -v ${PWD}:/work demo --waveform sine --frequency 0.1 --bias 50 --amplitude 30 --test-number 1
```

## Typical Workflow

1. Start dashboard.
2. Verify telemetry is streaming.
3. Run baseline tests to build profile data.
4. Enable/adjust movement detection thresholds.
5. Monitor anomaly and movement reports.
6. Tune control logic to reduce power use and avoid unnecessary oscillation.

## Notes

- If network quality drops, dashboard may use cached data for continuity.
- Movement detection can ignore intentionally oscillating waveforms if enabled.
- Export anomaly logs from the dashboard for offline analysis.
