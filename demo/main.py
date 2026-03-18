import argparse

from client import record_sensor_data_to_csv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="CSV file name (extension optional)")
    parser.add_argument("seconds", type=float, help="How long to record data")
    args = parser.parse_args()

    output = record_sensor_data_to_csv(args.name, args.seconds)
    print(f"Saved data to: {output}")


if __name__ == "__main__":
    main()
