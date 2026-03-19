import altair as alt
import streamlit as st
import time
import pandas as pd
from pathlib import Path
import importlib.util

from interface.influx.api import set_process_data, get_measurement_data

# Configuration
PLOT_POINTS = 1000
PLOT_LOOKBACK = "15m"
REFRESH_INTERVAL = 0.5

# Dark industrial theme
DARK_BG = "#0a0e27"
DARK_CARD = "#141829"
MUTED_TEXT = "#6b7280"
ACCENT = "#4f46e5"
ACCENT_LIGHT = "#6366f1"

# Load waveform module
_waveform_path = Path(__file__).resolve().parent / "signal" / "waveform.py"
_waveform_spec = importlib.util.spec_from_file_location(
    "local_waveform", _waveform_path
)
if _waveform_spec is None or _waveform_spec.loader is None:
    raise ImportError(f"Cannot load waveform module from {_waveform_path}")
_waveform_module = importlib.util.module_from_spec(_waveform_spec)
_waveform_spec.loader.exec_module(_waveform_module)
compute_setpoint = _waveform_module.compute_setpoint

# Initialize session state
if "test_number" not in st.session_state:
    st.session_state.test_number = -1
    st.session_state.waveform = "constant"
    st.session_state.bias = 50
    st.session_state.freq = 0.04
    st.session_state.amp = 40
    st.session_state.x = "timestamp"
    st.session_state.y = "feedback_position_%"

# Apply dark industrial CSS
st.markdown("""
<style>
    [data-testid="stMainBlockContainer"] {
        background-color: #0a0e27;
        color: #e5e7eb;
    }
    .stApp {
        background-color: #0a0e27;
    }
    h1, h2, h3 {
        color: #ffffff;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    .metric-card {
        background: linear-gradient(135deg, #141829 0%, #1a1f3a 100%);
        padding: 20px;
        border-radius: 8px;
        border: 1px solid #2d3448;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .hero-card {
        background: linear-gradient(135deg, #1a1f3a 0%, #141829 100%);
        padding: 40px;
        border-radius: 12px;
        border: 2px solid #4f46e5;
        box-shadow: 0 8px 16px rgba(79, 70, 229, 0.2);
        text-align: center;
    }
    .hero-value {
        font-size: 72px;
        font-weight: 700;
        color: #4f46e5;
        margin: 0;
        font-family: 'Courier New', monospace;
    }
    .hero-label {
        color: #9ca3af;
        font-size: 16px;
        margin-top: 8px;
        letter-spacing: 1px;
        text-transform: uppercase;
    }
    .metric-label {
        color: #9ca3af;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }
    .metric-value {
        color: #f3f4f6;
        font-size: 28px;
        font-weight: 600;
        font-family: 'Courier New', monospace;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        background-color: #141829;
        border-bottom: 1px solid #2d3448;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        color: #9ca3af;
        border-radius: 0;
        padding: 12px 24px;
        font-weight: 500;
        border-bottom: 2px solid transparent;
    }
    .stTabs [aria-selected="true"] {
        background-color: transparent;
        color: #ffffff;
        border-bottom-color: #4f46e5 !important;
    }
</style>
""", unsafe_allow_html=True)

# Page configuration
st.set_page_config(
    page_title="Belimo Actuator Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Navigation tabs
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📈 Views", "⚙️ Controls"])

# ==================== DASHBOARD TAB ====================
with tab1:
    # Top-level control: auto-update toggle
    col_refresh, col_test = st.columns([1, 1])
    with col_refresh:
        auto_update = st.checkbox("Auto-update", value=True, key="auto_update")
    with col_test:
        st.session_state.test_number = st.number_input(
            "Test Number", value=st.session_state.test_number
        )
    
    dashboard_placeholder = st.empty()
    
    while True:
        if auto_update:
            setpoint_position = compute_setpoint(
                st.session_state.waveform,
                st.session_state.freq,
                st.session_state.bias,
                st.session_state.amp,
            )
            set_process_data(setpoint_position, test_number=st.session_state.test_number)
            
            try:
                df = get_measurement_data(n=PLOT_POINTS, lookback=PLOT_LOOKBACK)
                
                with dashboard_placeholder.container():
                    # Get latest values
                    latest = df.iloc[-1] if len(df) > 0 else None
                    
                    if latest is not None:
                        # HERO CARD - Current Rotation
                        st.markdown("<div class='hero-card'>", unsafe_allow_html=True)
                        rotation_val = latest.get("feedback_position_%", 0)
                        st.markdown(f"<p class='hero-value'>{rotation_val:.1f}%</p>", unsafe_allow_html=True)
                        st.markdown("<p class='hero-label'>Current Rotation</p>", unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                        # METRICS GRID
                        st.markdown("---")
                        
                        metrics_cols = st.columns(3)
                        
                        metric_data = [
                            ("Setpoint Position", "setpoint_position_%", "%"),
                            ("Direction", "rotation_direction", ""),
                            ("Temperature", "internal_temperature_deg_C", "°C"),
                            ("Motor Torque", "motor_torque_Nmm", "Nmm"),
                            ("Power", "power_W", "W"),
                        ]
                        
                        for idx, (label, key, unit) in enumerate(metric_data):
                            with metrics_cols[idx % 3]:
                                st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
                                st.markdown(f"<p class='metric-label'>{label}</p>", unsafe_allow_html=True)
                                value = latest.get(key, 0)
                                st.markdown(
                                    f"<p class='metric-value'>{value:.2f}{unit}</p>",
                                    unsafe_allow_html=True
                                )
                                st.markdown("</div>", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error fetching data: {e}")
        
        time.sleep(REFRESH_INTERVAL)

# ==================== VIEWS TAB ====================
with tab2:
    st.markdown("### Time Series Data")
    
    col_x, col_y = st.columns(2)
    with col_x:
        x_option = st.selectbox(
            "X-axis",
            ["timestamp", "feedback_position_%", "setpoint_position_%", "rotation_direction", 
             "internal_temperature_deg_C", "motor_torque_Nmm", "power_W"],
            index=0,
            key="view_x"
        )
    with col_y:
        y_option = st.selectbox(
            "Y-axis",
            ["timestamp", "feedback_position_%", "setpoint_position_%", "rotation_direction",
             "internal_temperature_deg_C", "motor_torque_Nmm", "power_W"],
            index=1,
            key="view_y"
        )
    
    views_placeholder = st.empty()
    
    while True:
        setpoint_position = compute_setpoint(
            st.session_state.waveform,
            st.session_state.freq,
            st.session_state.bias,
            st.session_state.amp,
        )
        set_process_data(setpoint_position, test_number=st.session_state.test_number)
        
        try:
            df = get_measurement_data(n=PLOT_POINTS, lookback=PLOT_LOOKBACK)
            
            with views_placeholder.container():
                chart = (
                    alt.Chart(df.reset_index())
                    .mark_line(color=ACCENT, point=True)
                    .encode(
                        x=alt.X(x_option, title=x_option),
                        y=alt.Y(y_option, title=y_option),
                        tooltip=[x_option, y_option]
                    )
                    .properties(height=500)
                    .interactive()
                )
                st.altair_chart(chart, use_container_width=True)
        except Exception as e:
            st.error(f"Error fetching data: {e}")
        
        time.sleep(REFRESH_INTERVAL)

# ==================== CONTROLS TAB ====================
with tab3:
    st.markdown("### Experiment Controls")
    st.info("Configure waveform parameters for the actuator setpoint.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.session_state.waveform = st.radio(
            "Waveform Type",
            ["constant", "sine", "triangle", "square"],
            index=["constant", "sine", "triangle", "square"].index(st.session_state.waveform)
        )
        st.session_state.bias = st.slider(
            "Bias (%)",
            min_value=0,
            max_value=100,
            value=st.session_state.bias,
            step=1
        )
    
    with col2:
        st.session_state.freq = st.number_input(
            "Frequency (Hz)",
            value=st.session_state.freq,
            min_value=0.01,
            step=0.01
        )
        st.session_state.amp = st.slider(
            "Amplitude (%)",
            min_value=0,
            max_value=100,
            value=st.session_state.amp,
            step=1
        )
    
    st.markdown("---")
    st.markdown("**Current Configuration:**")
    config_col1, config_col2, config_col3, config_col4 = st.columns(4)
    with config_col1:
        st.metric("Waveform", st.session_state.waveform)
    with config_col2:
        st.metric("Frequency", f"{st.session_state.freq:.3f} Hz")
    with config_col3:
        st.metric("Bias", f"{st.session_state.bias}%")
    with config_col4:
        st.metric("Amplitude", f"{st.session_state.amp}%")
