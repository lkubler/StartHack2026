import importlib.util
import random
import time
import logging
from pathlib import Path

import altair as alt
import streamlit as st

from interface.influx.api import get_measurement_data, set_process_data
from interface.analytics import update_profile, check_anomalies, render_profile_dashboard

PLOT_POINTS = 1500
PLOT_LOOKBACK = "15m"
REFRESH_SECONDS = 3.0  # Increased from 2.0s to`` give network time to recover on unstable connections
ARMING_SECONDS = 2.5
TEST_TIMEOUT_SECONDS = 8.0
TEST_TOLERANCE_PERCENT = 7.0
SHUFFLE_INTERVAL_SECONDS = 6.0
WAVE_OPTIONS = ["constant", "sine", "triangle", "square"]

_waveform_path = Path(__file__).resolve().parent / "signal" / "waveform.py"
_waveform_spec = importlib.util.spec_from_file_location("local_waveform", _waveform_path)
if _waveform_spec is None or _waveform_spec.loader is None:
    raise ImportError(f"Cannot load waveform module from {_waveform_path}")
_waveform_module = importlib.util.module_from_spec(_waveform_spec)
_waveform_spec.loader.exec_module(_waveform_module)
compute_setpoint = _waveform_module.compute_setpoint


def _init_state():
    if "waveform" not in st.session_state:
        st.session_state.waveform = "constant"
    if "bias" not in st.session_state:
        st.session_state.bias = 50.0
    if "freq" not in st.session_state:
        st.session_state.freq = 0.04
    if "amp" not in st.session_state:
        st.session_state.amp = 40.0
    if "live_refresh" not in st.session_state:
        st.session_state.live_refresh = True
    if "run_mode" not in st.session_state:
        st.session_state.run_mode = "run"
    if "shuffle_enabled" not in st.session_state:
        st.session_state.shuffle_enabled = False
    if "controller_active" not in st.session_state:
        st.session_state.controller_active = False
    if "controller_phase" not in st.session_state:
        st.session_state.controller_phase = "idle"
    if "active_waveform" not in st.session_state:
        st.session_state.active_waveform = st.session_state.waveform
    if "arming_setpoint" not in st.session_state:
        st.session_state.arming_setpoint = float(st.session_state.bias)
    if "arming_until_ts" not in st.session_state:
        st.session_state.arming_until_ts = 0.0
    if "last_wave_change_ts" not in st.session_state:
        st.session_state.last_wave_change_ts = 0.0
    if "test_deadline_ts" not in st.session_state:
        st.session_state.test_deadline_ts = 0.0
    if "test_status" not in st.session_state:
        st.session_state.test_status = "idle"
    if "test_message" not in st.session_state:
        st.session_state.test_message = "No test started yet."
    if "last_command_setpoint" not in st.session_state:
        st.session_state.last_command_setpoint = None
    if "last_test_delta" not in st.session_state:
        st.session_state.last_test_delta = None
    if "last_measurement_df" not in st.session_state:
        st.session_state.last_measurement_df = None
    if "run_complete" not in st.session_state:
        st.session_state.run_complete = False


def _inject_styles():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&family=Space+Grotesk:wght@500;700&display=swap');

        :root {
            --bg-0: #05070d;
            --bg-1: #0d1422;
            --bg-2: #121a2a;
            --glass: rgba(255, 255, 255, 0.08);
            --glass-border: rgba(255, 255, 255, 0.2);
            --text: #e8efff;
            --muted: #9fb0cf;
            --accent-a: #1dd5d2;
            --accent-b: #5ac2ff;
            --accent-c: #7df7a6;
            --danger: #ff6b8a;
        }

        .stApp {
            background:
                radial-gradient(1100px 500px at 8% 5%, rgba(29, 213, 210, 0.16), transparent 60%),
                radial-gradient(900px 600px at 95% 0%, rgba(90, 194, 255, 0.18), transparent 65%),
                linear-gradient(145deg, var(--bg-0), var(--bg-1) 40%, var(--bg-2));
            color: var(--text);
            font-family: "Manrope", sans-serif;
        }

        .block-container {
            max-width: 1320px;
            padding-top: 1.5rem;
            padding-bottom: 2.4rem;
            padding-left: clamp(1.05rem, 2.6vw, 2rem);
            padding-right: clamp(1.05rem, 2.6vw, 2rem);
        }

        h1, h2, h3 {
            font-family: "Space Grotesk", sans-serif;
            color: var(--text);
            letter-spacing: 0.01em;
        }

        .glass {
            border: 1px solid var(--glass-border);
            background: linear-gradient(145deg, rgba(255, 255, 255, 0.13), rgba(255, 255, 255, 0.04));
            border-radius: 20px;
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            box-shadow: 0 10px 34px rgba(0, 0, 0, 0.35);
            padding: 1.15rem 1.3rem;
        }

        .top-row-card {
            height: 100%;
            min-height: 126px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }

        .header-row {
            margin-bottom: 0.8rem;
        }

        .hero-title {
            font-size: 2.15rem;
            line-height: 1.1;
            margin: 0;
            color: #f4f8ff;
        }

        .hero-subtitle {
            margin: 0.45rem 0 0;
            color: var(--muted);
            font-size: 0.97rem;
        }

        .mini-label {
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.72rem;
            margin-bottom: 0.3rem;
        }

        .mini-value {
            color: #f7fbff;
            font-size: 1.25rem;
            font-weight: 700;
        }

        .compact-status-card {
            gap: 0.2rem;
        }

        .compact-status-card .mini-label {
            margin-bottom: 0.15rem;
        }

        .compact-status-card .mini-value {
            font-size: 1.05rem;
            line-height: 1.2;
        }

        [data-testid="stMetric"] {
            border: 1px solid var(--glass-border);
            background: linear-gradient(150deg, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0.04));
            border-radius: 16px;
            padding: 0.8rem 1rem;
        }

        [data-testid="stMetricLabel"] {
            color: var(--muted);
        }

        [data-testid="stMetricValue"] {
            color: #eef6ff;
        }

        [data-baseweb="input"], [data-baseweb="select"], [data-baseweb="base-input"], [data-testid="stNumberInput"] input {
            background: rgba(8, 15, 27, 0.65) !important;
            color: var(--text) !important;
            border-radius: 12px !important;
        }

        .section-header {
            margin-top: 1.45rem;
            margin-bottom: 0.85rem;
            color: #dbe9ff;
            font-size: 1.25rem;
            font-family: "Space Grotesk", sans-serif;
        }

        div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stMetric"]) {
            margin-top: 0.3rem;
            margin-bottom: 0.35rem;
        }

        @media (max-width: 900px) {
            .block-container {
                padding-top: 1.1rem;
                padding-bottom: 1.7rem;
                padding-left: 1rem;
                padding-right: 1rem;
            }

            div[data-testid="stColumn"] {
                margin-bottom: 0.95rem;
            }

            .glass {
                padding: 1.05rem 1.05rem;
                border-radius: 16px;
            }

            .header-row {
                margin-bottom: 1rem;
            }

            .section-header {
                margin-top: 1.2rem;
                margin-bottom: 0.75rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header():
    st.markdown('<div class="header-row">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="glass top-row-card">
            <p class="hero-title">Belimo Actuator Sensor Dashboard</p>
            <p class="hero-subtitle">Live telemetry, process setpoint generation, and waveform control in one view.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _feedback_from_df(df):
    if df is None or df.empty or "feedback_position_%" not in df.columns:
        return None
    value = df.iloc[-1]["feedback_position_%"]
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_next_waveform(current_waveform):
    if not st.session_state.shuffle_enabled:
        return st.session_state.waveform
    candidates = [wave for wave in WAVE_OPTIONS if wave != current_waveform]
    if not candidates:
        return st.session_state.waveform
    return random.choice(candidates)


def _start_controller(mode, latest_feedback):
    now = time.time()
    st.session_state.controller_active = True
    st.session_state.controller_phase = "arming"
    st.session_state.run_mode = mode
    st.session_state.arming_until_ts = now + ARMING_SECONDS
    st.session_state.arming_setpoint = (
        float(latest_feedback) if latest_feedback is not None else float(st.session_state.bias)
    )
    st.session_state.active_waveform = st.session_state.waveform
    st.session_state.last_wave_change_ts = now
    st.session_state.last_command_setpoint = None
    st.session_state.last_test_delta = None

    if mode == "test":
        st.session_state.test_status = "running"
        st.session_state.test_message = "Test started. Arming actuator before verification."
        st.session_state.test_deadline_ts = 0.0
    else:
        st.session_state.test_status = "idle"
        st.session_state.test_message = "Run mode active."
        st.session_state.test_deadline_ts = 0.0


def _stop_controller(message="Controller stopped."):
    st.session_state.controller_active = False
    st.session_state.controller_phase = "idle"
    if st.session_state.run_mode == "test":
        st.session_state.test_message = message


def _finish_test(success, message):
    st.session_state.test_status = "passed" if success else "failed"
    st.session_state.test_message = message
    
    # Update profile on successful test completion
    if success and "last_measurement_df" in st.session_state and st.session_state.last_measurement_df is not None:
        try:
            update_profile(
                st.session_state.active_waveform,
                st.session_state.bias,
                st.session_state.amp,
                st.session_state.freq,
                st.session_state.last_measurement_df,
            )
        except Exception as e:
            logging.warning(f"Failed to update profile: {e}")
    
    if st.session_state.shuffle_enabled:
        # Repeat test cycles when shuffle is enabled.
        st.session_state.controller_phase = "arming"
        st.session_state.arming_until_ts = time.time() + ARMING_SECONDS
        st.session_state.arming_setpoint = float(st.session_state.bias)
        st.session_state.active_waveform = _pick_next_waveform(st.session_state.active_waveform)
        st.session_state.test_status = "running"
        st.session_state.test_message = "Starting next shuffled test cycle."
        st.session_state.test_deadline_ts = 0.0
    else:
        _stop_controller(message)


def _control_step(latest_feedback):
    if not st.session_state.controller_active:
        return

    now = time.time()

    if st.session_state.controller_phase == "arming":
        set_process_data(float(st.session_state.arming_setpoint))
        st.session_state.last_command_setpoint = float(st.session_state.arming_setpoint)
        if now >= st.session_state.arming_until_ts:
            st.session_state.controller_phase = "active"
            st.session_state.last_wave_change_ts = now
            if st.session_state.shuffle_enabled:
                st.session_state.active_waveform = _pick_next_waveform(st.session_state.active_waveform)
            else:
                st.session_state.active_waveform = st.session_state.waveform
            if st.session_state.run_mode == "test":
                st.session_state.test_deadline_ts = now + TEST_TIMEOUT_SECONDS
                st.session_state.test_status = "running"
                st.session_state.test_message = "Testing waveform response..."
        return

    if st.session_state.shuffle_enabled and (now - st.session_state.last_wave_change_ts) >= SHUFFLE_INTERVAL_SECONDS:
        st.session_state.active_waveform = _pick_next_waveform(st.session_state.active_waveform)
        st.session_state.last_wave_change_ts = now

    setpoint_position = compute_setpoint(
        st.session_state.active_waveform,
        st.session_state.freq,
        st.session_state.bias,
        st.session_state.amp,
    )
    st.session_state.last_command_setpoint = float(setpoint_position)
    set_process_data(setpoint_position)

    if st.session_state.run_mode != "test":
        return

    if latest_feedback is None:
        if now >= st.session_state.test_deadline_ts > 0:
            _finish_test(False, "Test failed: no feedback available before timeout.")
        return

    delta = abs(float(latest_feedback) - float(setpoint_position))
    st.session_state.last_test_delta = delta
    if delta <= TEST_TOLERANCE_PERCENT:
        _finish_test(
            True,
            f"Test passed: |feedback - setpoint| = {delta:.2f} <= {TEST_TOLERANCE_PERCENT:.1f}",
        )
    elif now >= st.session_state.test_deadline_ts > 0:
        _finish_test(
            False,
            f"Test failed: delta {delta:.2f} > {TEST_TOLERANCE_PERCENT:.1f} at timeout.",
        )


def _render_metrics(df):
    latest = df.iloc[-1]
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Setpoint (%)", f"{latest.get('setpoint_position_%', float('nan')):,.2f}")
    c2.metric("Feedback (%)", f"{latest.get('feedback_position_%', float('nan')):,.2f}")
    c3.metric("Direction", str(latest.get("rotation_direction", "-")))
    c4.metric("Temp (deg C)", f"{latest.get('internal_temperature_deg_C', float('nan')):,.2f}")
    c5.metric("Torque (Nmm)", f"{latest.get('motor_torque_Nmm', float('nan')):,.2f}")
    c6.metric("Power (W)", f"{latest.get('power_W', float('nan')):,.2f}")


def _build_chart(df, column_name, title, color):
    base = alt.Chart(df).encode(
        x=alt.X("timestamp:T", title="Time"),
        y=alt.Y(f"{column_name}:Q", title=title),
        tooltip=[
            alt.Tooltip("timestamp:T", title="Time"),
            alt.Tooltip(f"{column_name}:Q", title=title, format=".4f"),
        ],
    )
    area = base.mark_area(color=color, opacity=0.16)
    line = base.mark_line(color=color, strokeWidth=2.2)
    return (area + line).properties(height=250)


def _render_charts(df):
    st.markdown("<div class='section-header'>Sensor Graphs</div>", unsafe_allow_html=True)

    chart_specs = [
        ("setpoint_position_%", "Setpoint Position (%)", "#1dd5d2"),
        ("feedback_position_%", "Feedback Position (%)", "#5ac2ff"),
        ("internal_temperature_deg_C", "Internal Temperature (deg C)", "#7df7a6"),
        ("motor_torque_Nmm", "Motor Torque (Nmm)", "#ffd27f"),
        ("power_W", "Power (W)", "#ff8aa5"),
    ]

    left, right = st.columns(2)
    for i, (column_name, title, color) in enumerate(chart_specs):
        target = left if i % 2 == 0 else right
        with target:
            with st.container(border=True):
                if column_name in df.columns:
                    chart = _build_chart(df, column_name, title, color)
                    st.altair_chart(chart, width="stretch")
                else:
                    st.warning(f"Column '{column_name}' not found in measurement data.")


def _render_controls():
    st.markdown("<div class='section-header'>Waveform Controls</div>", unsafe_allow_html=True)
    with st.container(border=True):
        c1, c2 = st.columns([1.45, 1.0])
        with c1:
            st.session_state.waveform = st.radio(
                "Waveform type",
                WAVE_OPTIONS,
                horizontal=True,
                index=WAVE_OPTIONS.index(st.session_state.waveform),
            )
        with c2:
            st.session_state.freq = st.number_input(
                "Frequency (Hz)",
                value=float(st.session_state.freq),
                min_value=0.0,
                step=0.005,
                format="%.5f",
            )

        r1, r2 = st.columns(2)
        with r1:
            st.session_state.bias = st.slider(
                "Bias (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(st.session_state.bias),
                step=0.5,
            )
        with r2:
            st.session_state.amp = st.slider(
                "Amplitude (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(st.session_state.amp),
                step=0.5,
            )

        u1, u2 = st.columns([1.0, 1.0])
        with u1:
            st.session_state.live_refresh = st.toggle(
                "Live updates",
                value=st.session_state.live_refresh,
            )
        with u2:
            st.session_state.shuffle_enabled = st.toggle(
                "Repeat with shuffled waveforms",
                value=st.session_state.shuffle_enabled,
                help="When enabled, waveform type rotates automatically.",
            )

        is_active = st.session_state.controller_active
        action_cols = st.columns(3)
        if action_cols[0].button(
            "Start Run",
            use_container_width=True,
            type="secondary" if is_active else "primary",
            help="Continuous waveform control until you press Stop.",
        ):
            st.session_state._control_action = "start_run"
        if action_cols[1].button(
            "Run Test",
            use_container_width=True,
            help="Single verification run with simple pass/fail check.",
        ):
            st.session_state._control_action = "start_test"
        if action_cols[2].button(
            "Stop",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state._control_action = "stop"

        if is_active:
            if st.session_state.controller_phase == "arming":
                st.info("Preparing actuator to a safe starting point before execution.")
            else:
                st.success(f"Running: {st.session_state.active_waveform} waveform")
        else:
            st.info("Controller is stopped. Set values and press Start Run or Run Test.")

        if st.session_state.last_command_setpoint is not None:
            st.caption(f"Last command setpoint: {st.session_state.last_command_setpoint:.2f} %")

        if st.session_state.test_status == "passed":
            st.success(st.session_state.test_message)
        elif st.session_state.test_status == "failed":
            st.error(st.session_state.test_message)
        elif st.session_state.test_status == "running":
            st.info(st.session_state.test_message)


def main():
    st.set_page_config(
        page_title="Belimo Dashboard",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    _init_state()
    _inject_styles()
    _render_header()

    # Try to fetch fresh data, but use cached version if network fails
    try:
        df = get_measurement_data(n=PLOT_POINTS, lookback=PLOT_LOOKBACK)
        if df is not None and not df.empty:
            st.session_state.last_measurement_df = df
    except Exception as exc:
        logging.warning(f"Failed to fetch measurement data: {exc}")
        # Use cached data if available
        if "last_measurement_df" in st.session_state and st.session_state.last_measurement_df is not None:
            st.warning("⚠️ Network unstable - using cached data")
            df = st.session_state.last_measurement_df
        else:
            st.error(f"Cannot fetch data and no cache available: {exc}")
            df = None

    if df is not None and not df.empty:
        plot_df = df.reset_index().sort_values("timestamp")
        _render_metrics(plot_df)
        _render_charts(plot_df)
        
        # Check for anomalies
        anomaly_result = check_anomalies(
            st.session_state.active_waveform,
            st.session_state.bias,
            st.session_state.amp,
            st.session_state.freq,
            plot_df,
        )
        
        if anomaly_result["has_anomalies"]:
            with st.container(border=True):
                st.error("🚨 Anomalies Detected")
                for msg in anomaly_result["messages"]:
                    st.write(msg)
    else:
        st.info("No measurement data available yet. Waiting for data stream...")

    latest_feedback = _feedback_from_df(plot_df) if df is not None and not df.empty else None

    _render_controls()

    control_action = st.session_state.pop("_control_action", None)
    if control_action == "start_run":
        _start_controller("run", latest_feedback)
    elif control_action == "start_test":
        _start_controller("test", latest_feedback)
    elif control_action == "stop":
        _stop_controller("Stopped by user.")

    try:
        _control_step(latest_feedback)
    except Exception as exc:
        logging.warning(f"Controller step failed (non-critical): {exc}")
        # Don't crash on write failures - just log and continue

    # Show profiling dashboard
    render_profile_dashboard()

    if st.session_state.live_refresh:
        time.sleep(REFRESH_SECONDS)
        st.rerun()


if __name__ == "__main__":
    main()
