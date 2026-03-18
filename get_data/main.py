from client import record_sensor_data_to_csv


OUTPUT_NAME = "demo_capture"
RECORD_SECONDS = 10
POLL_INTERVAL_SECONDS = 0.2


def main():
    output = record_sensor_data_to_csv(
        OUTPUT_NAME,
        RECORD_SECONDS,
        poll_interval=POLL_INTERVAL_SECONDS,
    )
    print(f"Saved data to: {output}")


if __name__ == "__main__":
    main()
