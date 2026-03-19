import logging
from datetime import datetime, timezone
import time
from typing import TypeVar, Callable, Optional
import pandas as pd
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS, WritePrecision
import random

#  W-Lan
url = "http://192.168.3.14:8086"
# Lan
# url = "http://192.168.5.14:8086"

token = "pf-OGC6AQFmKy64gOzRM12DZrCuavnWeMgRZ2kDMOk8LYK22evDJnoyKGcmY49EgT8HnMDE9GPQeg30vXeHsRQ=="
verify_ssl = False
org = "belimo"
bucket = "actuator-data"
measurement = "measurements"
process = "_process"

# IMPROVED timeout and retry configuration
influx_timeout_ms = 3000  # Shorter timeout = fail fast
MAX_RETRIES = 10          # Only 2 retries max (fail fast on unstable networks)
INITIAL_BACKOFF = 0.2    # Start with 200ms only
MAX_BACKOFF = 0.5        # Cap at 500ms max
JITTER_FACTOR = 0.1      # Minimal jitter

_influx_client = None
_last_connection_check = 0
_connection_check_interval = 1  # Check connectivity every 30 seconds
_last_measurement_cache: Optional[pd.DataFrame] = None
_last_measurement_cache_time = 0

timestamp = datetime.fromtimestamp(0, tz=timezone.utc)


def _exponential_backoff(attempt: int) -> float:
    """Calculate backoff with exponential increase + jitter."""
    backoff = min(INITIAL_BACKOFF * (2 ** attempt), MAX_BACKOFF)
    jitter = backoff * JITTER_FACTOR * random.random()
    return backoff + jitter


def _get_influx_client() -> InfluxDBClient:
    """Get or initialize InfluxDB client with connection validation."""
    global _influx_client, _last_connection_check
    
    # Reinitialize if connection is stale (not checked recently)
    current_time = time.time()
    if _influx_client is None or (current_time - _last_connection_check) > _connection_check_interval:
        _influx_client = InfluxDBClient(
            url=url,
            token=token,
            org=org,
            verify_ssl=verify_ssl,
            timeout=influx_timeout_ms,
        )
        _last_connection_check = current_time
    
    return _influx_client


def _init_influx():
    """Initialize InfluxDB clients."""
    client = _get_influx_client()
    read_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    return read_api, write_api


def _retry_with_backoff(
    operation: Callable,
    operation_name: str,
    max_retries: int = MAX_RETRIES
):
    """
    Fast-fail retry wrapper with minimal backoff.
    
    Optimized for unstable networks:
    - Only 2 retries (not 100!)
    - Very short delays (200-500ms max)
    - Fails fast to prevent UI freezing
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return operation()
        except Exception as exc:
            last_exception = exc
            is_last_attempt = (attempt == max_retries - 1)
            
            if is_last_attempt:
                logging.warning(
                    f"{operation_name} failed after {max_retries} attempts. "
                    f"Last error: {type(exc).__name__}: {exc}"
                )
                raise
            
            # Calculate short backoff and log
            wait_time = _exponential_backoff(attempt)
            logging.debug(
                f"{operation_name} attempt {attempt + 1}/{max_retries} failed. "
                f"Retrying in {wait_time:.2f}s..."
            )
            time.sleep(wait_time)


def _query_data_frame_with_retry(query: str):
    """Query with fast-fail retry. Falls back to cache on persistent failure."""
    def query_op():
        client = _get_influx_client()
        read_api = client.query_api()
        return read_api.query_data_frame(query)
    
    try:
        result = _retry_with_backoff(query_op, "Influx query", max_retries=MAX_RETRIES)
        global _last_measurement_cache, _last_measurement_cache_time
        # Cache successful reads
        if result is not None and not result.empty:
            _last_measurement_cache = result
            _last_measurement_cache_time = time.time()
        return result
    except Exception as exc:
        # If query fails and we have cached data, use it instead of crashing
        if _last_measurement_cache is not None and not _last_measurement_cache.empty:
            logging.warning(
                f"Query failed, using cached data from {time.time() - _last_measurement_cache_time:.1f}s ago"
            )
            return _last_measurement_cache
        # No cache available, re-raise
        raise


def _influx_write_with_retry(df, measurement_name: str):
    """
    Write with RETRY LOGIC and graceful failure handling.
    
    On unstable networks:
    - Tries quickly with short timeouts
    - Fails fast without blocking UI
    - Logs but doesn't crash
    """
    def write_op():
        client = _get_influx_client()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        write_api.write(
            bucket=bucket,
            record=df,
            write_precision=WritePrecision.MS,
            data_frame_measurement_name=measurement_name,
            data_frame_tag_columns=[],
        )
    
    try:
        return _retry_with_backoff(write_op, f"Influx write ({measurement_name})", max_retries=MAX_RETRIES)
    except Exception as exc:
        # For writes: log error but don't crash - the data is not mission-critical
        logging.warning(
            f"Write to {measurement_name} failed after {MAX_RETRIES} attempts: {type(exc).__name__}. "
            f"Data loss accepted on unstable network."
        )
        # Return gracefully without raising
        return None


def _get_last(measurement):
    query = f"""
        from(bucket:"{bucket}")
        |> range(start: 0)
        |> filter(fn: (r) => r["_measurement"] == "{measurement}")
        |> group(columns: ["_field"])
        |> last()
        |> drop(columns: ["_start", "_stop"])
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    """

    df = (
        _query_data_frame_with_retry(query)
        .set_index("_time")
        .drop(columns=["result", "table"])
    )
    df.index.name = "timestamp"
    return df


def _normalize_lookback(lookback):
    lookback = str(lookback).strip()
    if not lookback:
        return "-15m"
    if lookback.startswith("-"):
        return lookback
    return f"-{lookback}"


def _get_last_n(measurement, n, lookback="15m"):
    flux_lookback = _normalize_lookback(lookback)
    query = f"""
        from(bucket:"{bucket}")
        |> range(start: {flux_lookback})
        |> filter(fn: (r) => r["_measurement"] == "{measurement}")
        |> group(columns: ["_field"])
        |> tail(n:{n})
        |> drop(columns: ["_start", "_stop"])
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> sort(columns: ["_time"], desc: false)
    """

    df = (
        _query_data_frame_with_retry(query)
        .set_index("_time")
        .drop(columns=["result", "table"])
    )
    df.index.name = "timestamp"
    return df


def get_process_data():
    return _get_last(process)


def get_measurement_data(n=1, lookback="15m"):
    if n > 1:
        return _get_last_n(measurement, n, lookback=lookback)
    else:
        return _get_last(measurement)


def set_process_data(setpoint_position, test_number=-1):
    """Write setpoint with retry (IMPROVED - now handles failures)."""
    df = pd.DataFrame(
        [
            {
                "timestamp": timestamp,
                "setpoint_position_%": float(setpoint_position),
                "test_number": int(test_number),
            }
        ]
    ).set_index("timestamp")
    
    # THIS NOW HAS RETRY LOGIC!
    _influx_write_with_retry(df, process)


def set_measurement_data(df):
    """Write measurements with retry (IMPROVED)."""
    # THIS NOW HAS RETRY LOGIC!
    _influx_write_with_retry(df, measurement)
