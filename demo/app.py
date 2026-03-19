import importlib.util
import time
from pathlib import Path

import altair as alt
import streamlit as st

from interface.influx.api import get_measurement_data, set_process_data

PLOT_POINTS = 1000
PLOT_LOOKBACK = "15m"
REFRESH_SECONDS = 0.8

_waveform_path = Path(__file__).resolve().parent / "signal" / "waveform.py"
_waveform_spec = importlib.util.spec_from_file_location("local_waveform", _waveform_path)
if _waveform_spec is None or _waveform_spec.loader is None:
    raise ImportError(f"Cannot load waveform module from {_waveform_path}")
_waveform_module = importlib.util.module_from_spec(_waveform_spec)
_waveform_spec.loader.exec_module(_waveform_module)
compute_setpoint = _waveform_module.compute_setpoint


def _init_state():
    if "test_number" not in st.session_state:
        st.session_state.test_number = -1
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
            padding-bottom: 2rem;
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
            padding: 1.05rem 1.2rem;
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
            margin-top: 1.2rem;
            margin-bottom: 0.7rem;
            color: #dbe9ff;
            font-size: 1.25rem;
            font-family: "Space Grotesk", sans-serif;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header():
    left, right = st.columns([3.5, 1.5], vertical_alignment="center")
    with left:
        st.markdown(
            """
            <div class="glass">
                <p class="hero-title">Belimo Actuator Sensor Dashboard</p>
                <p class="hero-subtitle">Live telemetry, process setpoint generation, and waveform control in one view.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            f"""
            <div class="glass">
                <div class="mini-label">Live Refresh</div>
                <div class="mini-value">{'ON' if st.session_state.live_refresh else 'OFF'}</div>
                <div class="mini-label" style="margin-top:0.5rem;">Lookback</div>
                <div class="mini-value">{PLOT_LOOKBACK}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _write_process_setpoint():
    setpoint_position = compute_setpoint(
        st.session_state.waveform,
        st.session_state.freq,
        st.session_state.bias,
        st.session_state.amp,
    )
    set_process_data(setpoint_position, test_number=st.session_state.test_number)


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
        c1, c2, c3 = st.columns([1.2, 1.5, 1.2])
        with c1:
            st.session_state.test_number = st.number_input(
                "Test Number",
                value=int(st.session_state.test_number),
                step=1,
                format="%d",
            )
            st.session_state.live_refresh = st.toggle(
                "Live updates",
                value=st.session_state.live_refresh,
            )
        with c2:
            st.session_state.waveform = st.radio(
                "Waveform",
                ["constant", "sine", "triangle", "square"],
                horizontal=True,
                index=["constant", "sine", "triangle", "square"].index(st.session_state.waveform),
            )
        with c3:
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


def main():
    st.set_page_config(
        page_title="Belimo Dashboard",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    _init_state()
    _inject_styles()
    _render_header()

    try:
        _write_process_setpoint()
    except Exception as exc:
        st.error(f"Failed to write process data: {exc}")

    try:
        df = get_measurement_data(n=PLOT_POINTS, lookback=PLOT_LOOKBACK)
    except Exception as exc:
        st.error(f"Failed to fetch measurement data: {exc}")
        df = None

    if df is not None and not df.empty:
        plot_df = df.reset_index().sort_values("timestamp")
        _render_metrics(plot_df)
        _render_charts(plot_df)
    else:
        st.info("No measurement data available yet. Waiting for data stream...")

    _render_controls()

    if st.session_state.live_refresh:
        time.sleep(REFRESH_SECONDS)
        st.rerun()


if __name__ == "__main__":
    main()
