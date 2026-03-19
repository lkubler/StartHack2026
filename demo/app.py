import altair as alt
import streamlit as st
import time

# from signal.waveform import compute_setpoint
from pathlib import Path
import importlib.util

from interface.influx.api import set_process_data, get_measurement_data

PLOT_POINTS = 100
PLOT_LOOKBACK = "15m"

_waveform_path = Path(__file__).resolve().parent / "signal" / "waveform.py"
_waveform_spec = importlib.util.spec_from_file_location(
    "local_waveform", _waveform_path
)
if _waveform_spec is None or _waveform_spec.loader is None:
    raise ImportError(f"Cannot load waveform module from {_waveform_path}")
_waveform_module = importlib.util.module_from_spec(_waveform_spec)
_waveform_spec.loader.exec_module(_waveform_module)
compute_setpoint = _waveform_module.compute_setpoint

# Experiment controls
if "test_number" not in st.session_state:
    # an identifier for the test you are running; will be stored in the influx
    st.session_state.test_number = -1
    # the type of waveform you wish to have for the setpoint position; options: "constant", "sine", "triangular", "square"
    st.session_state.waveform = "constant"
    # in %; the bias of the waveform for the setpoint position
    st.session_state.bias = 50
    # in Hz; the frequency of the waveform for the setpoint position
    st.session_state.freq = 0.04
    # in %; the amplitude of the waveform for the setpoint position
    st.session_state.amp = 40
    st.session_state.x = "timestamp"  # in seconds; the time interval you wish to have between sending consecutive commands (wave functions)
    st.session_state.y = "position_feedback_%"  # in seconds; the time interval you wish to have between sending consecutive commands (wave functions)


st.title("Belimo Actuator Demo")


st.session_state.test_number = st.number_input(
    "Test Number", value=st.session_state.test_number
)
st.session_state.waveform = st.radio(
    "Choose actuator position waveform:", ["constant", "sine", "triangle", "square"]
)

st.session_state.bias = st.number_input("Bias", value=st.session_state.bias)
st.session_state.freq = st.number_input(
    "Frequency of the wave (Hz)", value=st.session_state.freq
)
st.session_state.amp = st.number_input("Amplitude", value=st.session_state.amp)

st.title("Real-Time Actuator Plot")
# Define display name - column name mapping
options = {
    "timestamp",
    "feedback_position_%",
    "setpoint_position_%",
    "rotation_direction",
    "internal_temperature_deg_C",
    "motor_torque_Nmm",
    "power_W",
}
# Create two columns: left for X, right for Y
col1, col2 = st.columns(2)
with col1:
    st.session_state.x = st.selectbox("Select X-axis variable", options)
with col2:
    st.session_state.y = st.selectbox("Select Y-axis variable", options)


container_0 = st.container(border=True)
with container_0:
    chart_placeholder = st.empty()

while True:
    setpoint_position = compute_setpoint(
        st.session_state.waveform,
        st.session_state.freq,
        st.session_state.bias,
        st.session_state.amp,
    )
    # write setpoint position
    set_process_data(setpoint_position, test_number=st.session_state.test_number)
    df = get_measurement_data(n=PLOT_POINTS, lookback=PLOT_LOOKBACK)
    # update chart
    chart = (
        alt.Chart(df.reset_index())
        .mark_point(color="steelblue")
        .encode(x=st.session_state.x, y=st.session_state.y)
    )
    chart_placeholder.altair_chart(chart, width="stretch")
    time.sleep(0.5)
