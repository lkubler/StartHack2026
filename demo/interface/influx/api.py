import logging
from datetime import datetime, timezone
import pandas as pd
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS, WritePrecision

url = "http://192.168.3.14:8086"
token = "pf-OGC6AQFmKy64gOzRM12DZrCuavnWeMgRZ2kDMOk8LYK22evDJnoyKGcmY49EgT8HnMDE9GPQeg30vXeHsRQ=="
verify_ssl = False
org = "belimo"
bucket = "actuator-data"
measurement = "measurements"
process = "_process"


timestamp = datetime.fromtimestamp(0, tz=timezone.utc)


def _init_influx():
    # create client
    influx_client = InfluxDBClient(
        url=url,
        token=token,
        org=org,
        verify_ssl=verify_ssl,
    )
    read_client = influx_client.query_api()
    # synchronous write for near real-time behavior
    write_client = influx_client.write_api(write_options=SYNCHRONOUS)

    return read_client, write_client


read_client, write_client = _init_influx()


def _influx_write(df, measurement_name):
    write_client.write(
        bucket=bucket,
        record=df,
        write_precision=WritePrecision.MS,
        data_frame_measurement_name=measurement_name,
        data_frame_tag_columns=[],
    )


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
        read_client.query_data_frame(query)
        .set_index("_time")
        .drop(columns=["result", "table"])
    )
    df.index.name = "timestamp"
    return df


def _get_last_n(measurement, n):
    query = f"""
        from(bucket:"{bucket}")
        |> range(start: 0)
        |> filter(fn: (r) => r["_measurement"] == "{measurement}")
        |> group(columns: ["_field"])
        |> sort(columns: ["_time"], desc: true)
        |> limit(n:{n})
        |> drop(columns: ["_start", "_stop"])
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    """

    df = (
        read_client.query_data_frame(query)
        .set_index("_time")
        .drop(columns=["result", "table"])
    )
    df.index.name = "timestamp"
    return df


def get_process_data():
    return _get_last(process)


def get_measurement_data(n=1):
    if n > 1:
        return _get_last_n(measurement, n)
    else:
        return _get_last(measurement)


def set_process_data(setpoint_position, test_number=-1):
    # create dataframe to write to influx
    df = pd.DataFrame(
        [
            {
                "timestamp": timestamp,
                "setpoint_position_%": float(setpoint_position),
                "test_number": int(test_number),
            }
        ]
    ).set_index("timestamp")
    _influx_write(df, process)


def set_measurement_data(df):
    _influx_write(df, measurement)
