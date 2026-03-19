"""
Anomaly detection and profiling for actuator telemetry.

Creates baseline profiles for power and torque under normal operating conditions,
then detects deviations that may indicate mechanical issues or failures.
"""

import logging
import sys
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional
import streamlit as st

# Configure logging to stderr
_logger = logging.getLogger("analytics")
if not _logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter(
        "%(asctime)s | ANOMALY | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    _logger.addHandler(handler)
    _logger.setLevel(logging.DEBUG)

# Anomaly detection thresholds
POWER_PERCENTILE_THRESHOLD = 95  # Flag if power > 95th percentile of baseline
TORQUE_PERCENTILE_THRESHOLD = 90  # Flag if torque > 90th percentile
MIN_SAMPLES_FOR_PROFILE = 20  # Need at least 20 samples to build a profile


def _get_profile_key(waveform: str, bias: float, amplitude: float, frequency: float) -> str:
    """Generate a unique key for storing profiles by configuration."""
    return f"{waveform}_{bias:.1f}_{amplitude:.1f}_{frequency:.5f}"


def _init_profile_state():
    """Initialize profile storage in Streamlit session state."""
    if "_waveform_profiles" not in st.session_state:
        st.session_state._waveform_profiles = {}
    if "_anomaly_log" not in st.session_state:
        st.session_state._anomaly_log = []
    if "_profile_stats" not in st.session_state:
        st.session_state._profile_stats = {}


def update_profile(
    waveform: str,
    bias: float,
    amplitude: float,
    frequency: float,
    df: pd.DataFrame,
) -> None:
    """
    Update baseline profile with new measurement data.
    
    Profiles are built incrementally from successful runs.
    Each profile stores: power distribution, torque distribution, typical ranges.
    """
    if df is None or df.empty or "power_W" not in df.columns:
        return

    _init_profile_state()
    profile_key = _get_profile_key(waveform, bias, amplitude, frequency)
    
    power_data = df["power_W"].dropna().values * 1000  # Convert to mW
    torque_data = df["motor_torque_Nmm"].dropna().values if "motor_torque_Nmm" in df.columns else np.array([])
    
    # Initialize or update profile
    if profile_key not in st.session_state._waveform_profiles:
        st.session_state._waveform_profiles[profile_key] = {
            "power_samples": [],
            "torque_samples": [],
            "count": 0,
        }
    
    profile = st.session_state._waveform_profiles[profile_key]
    profile["power_samples"].extend(power_data.tolist())
    profile["torque_samples"].extend(torque_data.tolist())
    profile["count"] += 1
    
    # Update statistics
    _compute_profile_stats(profile_key)
    
    _logger.info(
        f"Profile '{profile_key}' updated with {len(power_data)} power samples "
        f"({profile['count']} runs total)"
    )


def _compute_profile_stats(profile_key: str) -> None:
    """Compute statistical bounds for a profile."""
    profile = st.session_state._waveform_profiles[profile_key]
    
    power_arr = np.array(profile["power_samples"])
    torque_arr = np.array(profile["torque_samples"])
    
    stats = {
        "power": {
            "mean": float(np.mean(power_arr)) if len(power_arr) > 0 else 0,
            "std": float(np.std(power_arr)) if len(power_arr) > 0 else 0,
            "p95": float(np.percentile(power_arr, POWER_PERCENTILE_THRESHOLD)) if len(power_arr) > 0 else 0,
            "min": float(np.min(power_arr)) if len(power_arr) > 0 else 0,
            "max": float(np.max(power_arr)) if len(power_arr) > 0 else 0,
        },
        "torque": {
            "mean": float(np.mean(torque_arr)) if len(torque_arr) > 0 else 0,
            "std": float(np.std(torque_arr)) if len(torque_arr) > 0 else 0,
            "p90": float(np.percentile(torque_arr, TORQUE_PERCENTILE_THRESHOLD)) if len(torque_arr) > 0 else 0,
            "min": float(np.min(torque_arr)) if len(torque_arr) > 0 else 0,
            "max": float(np.max(torque_arr)) if len(torque_arr) > 0 else 0,
        },
        "sample_count": len(power_arr),
    }
    
    st.session_state._profile_stats[profile_key] = stats


def check_anomalies(
    waveform: str,
    bias: float,
    amplitude: float,
    frequency: float,
    df: pd.DataFrame,
) -> Dict[str, any]:
    """
    Check current data against baseline profile for anomalies.
    
    Returns:
        {
            "has_anomalies": bool,
            "power_anomalies": int,  # count of power outliers
            "torque_anomalies": int,  # count of torque outliers
            "power_severity": float,  # max deviation in %
            "torque_severity": float,  # max deviation in %
            "messages": [str],  # human-readable alerts
        }
    """
    _init_profile_state()
    profile_key = _get_profile_key(waveform, bias, amplitude, frequency)
    
    result = {
        "has_anomalies": False,
        "power_anomalies": 0,
        "torque_anomalies": 0,
        "power_severity": 0.0,
        "torque_severity": 0.0,
        "messages": [],
    }
    
    # No profile yet
    if profile_key not in st.session_state._profile_stats:
        return result
    
    stats = st.session_state._profile_stats[profile_key]
    
    # Not enough samples to make meaningful comparisons
    if stats["sample_count"] < MIN_SAMPLES_FOR_PROFILE:
        return result
    
    if df is None or df.empty:
        return result
    
    # Check power anomalies
    if "power_W" in df.columns:
        current_power = df["power_W"].dropna().values * 1000  # Convert to mW
        power_threshold = stats["power"]["p95"]
        
        if power_threshold > 0:
            anomalies = current_power[current_power > power_threshold]
            result["power_anomalies"] = len(anomalies)
            
            if len(anomalies) > 0:
                max_power = np.max(anomalies)
                severity = ((max_power - power_threshold) / power_threshold) * 100
                result["power_severity"] = severity
                result["has_anomalies"] = True
                result["messages"].append(
                    f"⚠️ High power consumption detected: {max_power:.1f} mW "
                    f"(normal: {stats['power']['p95']:.1f} mW, +{severity:.1f}%)"
                )
    
    # Check torque anomalies
    if "motor_torque_Nmm" in df.columns:
        current_torque = df["motor_torque_Nmm"].dropna().values
        torque_threshold = stats["torque"]["p90"]
        
        if torque_threshold > 0 and len(current_torque) > 0:
            anomalies = np.abs(current_torque[np.abs(current_torque) > torque_threshold])
            result["torque_anomalies"] = len(anomalies)
            
            if len(anomalies) > 0:
                max_torque = np.max(anomalies)
                severity = ((max_torque - torque_threshold) / torque_threshold) * 100
                result["torque_severity"] = severity
                result["has_anomalies"] = True
                result["messages"].append(
                    f"⚠️ Unusual torque detected: {max_torque:.2f} Nmm "
                    f"(normal: {torque_threshold:.2f} Nmm, +{severity:.1f}%)"
                )
    
    # Log anomaly with detailed metrics
    if result["has_anomalies"]:
        anomaly_entry = {
            "timestamp": pd.Timestamp.now(),
            "waveform": waveform,
            "bias": bias,
            "amplitude": amplitude,
            "frequency": frequency,
            "power_anomalies": result["power_anomalies"],
            "power_severity_pct": result["power_severity"],
            "torque_anomalies": result["torque_anomalies"],
            "torque_severity_pct": result["torque_severity"],
        }
        st.session_state._anomaly_log.append(anomaly_entry)
        
        # Log to Python logging with full details
        log_msg = (
            f"ANOMALY DETECTED | {waveform} | "
            f"bias={bias:.1f}% amp={amplitude:.1f}% freq={frequency:.5f}Hz | "
            f"Power anomalies: {result['power_anomalies']} (+{result['power_severity']:.1f}%) | "
            f"Torque anomalies: {result['torque_anomalies']} (+{result['torque_severity']:.1f}%)"
        )
        _logger.warning(log_msg)
        
        # Also log detailed messages
        for msg in result["messages"]:
            _logger.warning(f"  {msg}")
    
    return result


def get_profile_summary(waveform: str, bias: float, amplitude: float, frequency: float) -> Optional[Dict]:
    """Get human-readable summary of a profile."""
    _init_profile_state()
    profile_key = _get_profile_key(waveform, bias, amplitude, frequency)
    
    if profile_key not in st.session_state._profile_stats:
        return None
    
    stats = st.session_state._profile_stats[profile_key]
    
    return {
        "profile_key": profile_key,
        "sample_count": stats["sample_count"],
        "power_baseline_mw": stats["power"]["mean"],
        "power_max_mw": stats["power"]["p95"],
        "torque_baseline_nmm": stats["torque"]["mean"],
        "torque_max_nmm": stats["torque"]["p90"],
    }


def export_anomalies_to_csv(filepath: str = "/tmp/anomaly_log.csv") -> Optional[str]:
    """
    Export anomaly log to CSV for persistent storage and analysis.
    
    Returns:
        Path to exported file, or None if no anomalies to export
    """
    _init_profile_state()
    
    if not st.session_state._anomaly_log:
        return None
    
    try:
        df = pd.DataFrame(st.session_state._anomaly_log)
        df.to_csv(filepath, index=False)
        _logger.info(f"Exported {len(df)} anomalies to {filepath}")
        return filepath
    except Exception as e:
        _logger.error(f"Failed to export anomalies: {e}")
        return None


def render_profile_dashboard():
    """Render profiling and anomaly detection dashboard."""
    st.markdown("<div class='section-header'>Performance Profiling & Anomaly Detection</div>", unsafe_allow_html=True)
    
    _init_profile_state()
    
    # Show profiles
    if st.session_state._waveform_profiles:
        st.subheader("📊 Baseline Profiles")
        profile_data = []
        
        for profile_key, stats in st.session_state._profile_stats.items():
            profile_data.append({
                "Config": profile_key,
                "Samples": stats["sample_count"],
                "Avg Power (mW)": f"{stats['power']['mean']:.1f}",
                "Max Power (mW)": f"{stats['power']['p95']:.1f}",
                "Avg Torque (Nmm)": f"{stats['torque']['mean']:.2f}",
                "Max Torque (Nmm)": f"{stats['torque']['p90']:.2f}",
            })
        
        if profile_data:
            profile_df = pd.DataFrame(profile_data)
            st.dataframe(profile_df, use_container_width=True, hide_index=True)
    else:
        st.info("No profiles yet. Run tests to build baseline data.")
    
    # Show recent anomalies
    if st.session_state._anomaly_log:
        st.subheader("🚨 Recent Anomalies")
        anomaly_df = pd.DataFrame(st.session_state._anomaly_log).tail(15)
        
        # Format for display
        display_df = anomaly_df.copy()
        if "timestamp" in display_df.columns:
            display_df["timestamp"] = display_df["timestamp"].dt.strftime("%H:%M:%S")
        if "power_severity_pct" in display_df.columns:
            display_df["power_severity_pct"] = display_df["power_severity_pct"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "-")
        if "torque_severity_pct" in display_df.columns:
            display_df["torque_severity_pct"] = display_df["torque_severity_pct"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "-")
        
        # Rename columns for display
        display_df = display_df.rename(columns={
            "timestamp": "Time",
            "waveform": "Waveform",
            "bias": "Bias",
            "amplitude": "Amp",
            "power_anomalies": "Power #",
            "power_severity_pct": "Power ↑",
            "torque_anomalies": "Torque #",
            "torque_severity_pct": "Torque ↑",
        })
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        st.caption(f"Total anomalies detected: {len(st.session_state._anomaly_log)}")
        
        # Add export button
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("📥 Export CSV"):
                export_path = export_anomalies_to_csv()
                if export_path:
                    st.success(f"Exported to {export_path}")
    else:
        st.info("No anomalies detected yet.")
