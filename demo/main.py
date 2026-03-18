import sys
import argparse
from signal.waveform import compute_setpoint
from interface.influx.api import set_process_data, get_measurement_data


def fmt_signed(v, pre=0, dec=1, show_sign=False):
    # sign column + pre-decimal digits + dot + decimals
    width = 1 + pre + 1 + dec
    if show_sign:
        # always show +/-
        return f"{v:+0{width}.{dec}f}"
    # no forced plus; negatives still show -, positives get a leading space
    return f"{v: 0{width}.{dec}f}"


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--test-number", type=int, default=-1, help="Test number to label the data with"
    )

    parser.add_argument(
        "--waveform",
        type=str,
        default="constant",
        help="Type of wave to generate. Options: 'constant', 'sine', 'triangle', 'square'",
    )

    parser.add_argument(
        "--frequency",
        type=float,
        default=0.0125,
        help="Frequency of the wave (applicable for sine, triangle, square)",
    )

    parser.add_argument(
        "--bias",
        type=float,
        default=50.0,
        help="Bias of the wave (applicable for sine, triangle, square)",
    )

    parser.add_argument(
        "--amplitude",
        type=float,
        default=40.0,
        help="Amplitude of the wave (applicable for sine, triangle, square)",
    )

    args = parser.parse_args()

    flag = True
    while flag:
        # write setpoint position and test number to influx
        setpoint_position = compute_setpoint(args.waveform, args.frequency, args.bias, args.amplitude)
        set_process_data(setpoint_position, args.test_number)
        # read measurement data from influx
        df = get_measurement_data()
        # print the latest measurement data
        test_number = df["test_number"].iloc[0]
        setpoint_position = df["setpoint_position_%"].iloc[0]
        feedback_position = df["feedback_position_%"].iloc[0]
        rotation_direction = df["rotation_direction"].iloc[0]
        temperature = df["internal_temperature_deg_C"].iloc[0]
        torque = df["motor_torque_Nmm"].iloc[0]
        power = df["power_W"].iloc[0] * 1000

        lines = [
            f"tag            = {fmt_signed(test_number, dec=0, show_sign=True)}",  # sign + fixed integer width
            f"setpoint       = {fmt_signed(setpoint_position, pre=3)} %",
            f"position       = {fmt_signed(feedback_position, pre=3)} %",
            f"direction      = {rotation_direction}",
            f"temperature    = {fmt_signed(temperature, pre=2)} °C",
            f"torque         = {fmt_signed(torque, pre=2, show_sign=True)} Nmm",
            f"power          = {fmt_signed(power, pre=3, show_sign=True)} mW",
        ]
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.write(f"\033[{len(lines)}A")  # move cursor back up N lines
        sys.stdout.flush()


if __name__ == "__main__":
    main()
