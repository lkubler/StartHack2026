import math
import time
import numpy as np


def _sine_wave(t, freq, bias, amp):
    new_sp = bias + amp * math.sin(2 * math.pi * freq * t)
    return np.clip(new_sp, a_min=0, a_max=100)


def compute_setpoint(waveform, freq, bias, amp):
    # Keep the same signature, but always use a sine waveform.
    t = time.time()
    return _sine_wave(t, freq, bias, amp)

