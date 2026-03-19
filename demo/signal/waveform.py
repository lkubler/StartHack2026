import math
import time
import numpy as np
from scipy.signal import sawtooth, square


def _sine_wave(t, freq, bias, amp):
    new_sp = bias + amp * math.sin(2 * math.pi * freq * t)
    return np.clip(new_sp, a_min=0, a_max=100)


def _triangle_wave(t, freq, bias, amp):
    tri = sawtooth(2 * math.pi * freq * t, width=0.5)
    new_sp = bias + amp * tri
    return np.clip(new_sp, a_min=0, a_max=100)


def _square_wave(t, freq, bias, amp):
    sq = square(2 * math.pi * freq * t)
    new_sp = bias + amp * sq
    return np.clip(new_sp, a_min=0, a_max=100)


def compute_setpoint(waveform, freq, bias, amp):
    t = time.time()
    if waveform == "sine":
        return _sine_wave(t, freq, bias, amp)
    elif waveform in ("triangle", "triangular"):
        return _triangle_wave(t, freq, bias, amp)
    elif waveform == "square":
        return _square_wave(t, freq, bias, amp)
    else:
        return _sine_wave(t, 0, bias, 0)

