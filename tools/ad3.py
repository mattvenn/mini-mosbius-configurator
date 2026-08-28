#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Minimal Digilent WaveForms (AD3/AD2) wrapper for bench measurements.

Only what the measurement scripts in tools/ need: open the device, drive
W1, capture the two scope channels. No dependency beyond ctypes and the
WaveForms install itself.

**Installing the SDK on macOS is two steps, not one.** `brew install
--cask waveforms` puts the *application* in /Applications, and the app
carries its own private copy of the framework -- so the GUI finds your
AD3 while any script you write reports 0 devices and 'Adept NOK'. The
DMG contains a second, standalone `dwf.framework` meant for
/Library/Frameworks, and the SDK only works once it is there:

    hdiutil attach ~/Library/Caches/Homebrew/downloads/*waveforms*.dmg
    sudo cp -R /Volumes/WaveForms/dwf.framework /Library/Frameworks/

**The scope range is a peak-to-peak span, not a maximum.** This is the
trap that cost an afternoon: `FDwfAnalogInChannelRangeSet(h, ch, 5.0)`
means +/-2.5 V around the channel offset, so a 3.3 V rail measured with
range 5.0 and offset 0 reads back a confident, stable 2.59 V -- the
clipping ceiling -- with no error anywhere. The tell is that the samples
go *perfectly* flat: standard deviation exactly 0.000 mV over thousands
of points is a railed ADC, never a quiet signal. The AD3 offers two spans
only, 5 V and 50 V, so a 0..3.3 V chip signal wants the 5 V span with the
offset at mid-rail (0.3 mV per LSB), and every capture here goes through
check_clipping().
"""

from __future__ import annotations

import ctypes
import time
from ctypes import byref, c_double, c_int, c_ubyte

DWF_PATH = "/Library/Frameworks/dwf.framework/dwf"

try:
    dwf = ctypes.cdll.LoadLibrary(DWF_PATH)
except OSError as exc:  # pragma: no cover - depends on the host install
    raise SystemExit(
        f"can't load the WaveForms SDK from {DWF_PATH}\n\n"
        "  Installing the WaveForms app alone is not enough: the app keeps a\n"
        "  private copy of the framework, so the GUI sees your Analog Discovery\n"
        "  while scripts report no devices. Copy the standalone framework from\n"
        "  the DMG into /Library/Frameworks -- see the note at the top of\n"
        "  tools/ad3.py for the two commands."
    ) from exc

funcDC, funcSine, funcSquare, funcTriangle, funcRampUp = 0, 1, 2, 3, 4
_STATE_DONE = 2

# A 0..3.3 V chip signal on the AD3's 5 V span, centred so both rails fit.
CHIP_RANGE, CHIP_OFFSET = 5.0, 1.65


def err() -> str:
    buf = ctypes.create_string_buffer(512)
    dwf.FDwfGetLastErrorMsg(buf)
    return buf.value.decode().strip()


def open_device():
    handle = c_int()
    if dwf.FDwfDeviceOpen(c_int(-1), byref(handle)) == 0 or handle.value == 0:
        raise SystemExit(
            "no Analog Discovery found: " + (err() or "(no error reported)") + "\n\n"
            "  Check it is plugged in, and that the WaveForms application is not\n"
            "  holding it -- one process owns the device at a time."
        )
    return handle


def wavegen(h, ch=0, func=funcDC, freq=1000.0, amp=0.0, offset=0.0, enable=True):
    """Drive W1 (ch=0) / W2 (ch=1). Keep `offset + amp` inside the chip's
    supply: driving a pin above VAPWR conducts through its ESD diode."""
    dwf.FDwfAnalogOutNodeEnableSet(h, c_int(ch), c_int(0), c_int(1 if enable else 0))
    dwf.FDwfAnalogOutNodeFunctionSet(h, c_int(ch), c_int(0), c_ubyte(func))
    dwf.FDwfAnalogOutNodeFrequencySet(h, c_int(ch), c_int(0), c_double(freq))
    dwf.FDwfAnalogOutNodeAmplitudeSet(h, c_int(ch), c_int(0), c_double(amp))
    dwf.FDwfAnalogOutNodeOffsetSet(h, c_int(ch), c_int(0), c_double(offset))
    dwf.FDwfAnalogOutConfigure(h, c_int(ch), c_int(1 if enable else 0))


def scope_setup(h, rate=1e5, nsamples=4000, rng=CHIP_RANGE, offset=CHIP_OFFSET,
                channels=(0, 1), settle=2.0):
    for ch in channels:
        dwf.FDwfAnalogInChannelEnableSet(h, c_int(ch), c_int(1))
        dwf.FDwfAnalogInChannelRangeSet(h, c_int(ch), c_double(rng))
        dwf.FDwfAnalogInChannelOffsetSet(h, c_int(ch), c_double(offset))
    dwf.FDwfAnalogInFrequencySet(h, c_double(rate))
    dwf.FDwfAnalogInBufferSizeSet(h, c_int(nsamples))
    dwf.FDwfAnalogInConfigure(h, c_int(1), c_int(0))
    scope_setup.window = (offset - rng / 2, offset + rng / 2)
    time.sleep(settle)


def acquire(h, nsamples=4000, channels=(0, 1), tag=""):
    dwf.FDwfAnalogInConfigure(h, c_int(0), c_int(1))
    status = c_ubyte()
    while True:
        dwf.FDwfAnalogInStatus(h, c_int(1), byref(status))
        if status.value == _STATE_DONE:
            break
        time.sleep(0.005)
    out = {}
    for ch in channels:
        buf = (c_double * nsamples)()
        dwf.FDwfAnalogInStatusData(h, c_int(ch), buf, c_int(nsamples))
        out[ch] = list(buf)
    return check_clipping(out, tag)


def check_clipping(samples, tag=""):
    """Refuse a capture that ran into the range edge, or came back flat."""
    lo, hi = getattr(scope_setup, "window", (-2.5, 2.5))
    edge = 0.02 * (hi - lo)
    for ch, values in samples.items():
        if max(values) > hi - edge or min(values) < lo + edge:
            raise RuntimeError(
                f"{tag}channel {ch + 1} reached {min(values):+.3f}..{max(values):+.3f} V, "
                f"at the edge of its {lo:+.2f}..{hi:+.2f} V window.\n"
                "  Widen the range or move the offset: past the edge the AD3 keeps\n"
                "  reporting numbers, they are just the ceiling rather than the signal."
            )
        if max(values) == min(values):
            raise RuntimeError(
                f"{tag}channel {ch + 1} is dead flat at {values[0]:+.4f} V over "
                f"{len(values)} samples.\n"
                "  That is a railed ADC, not a quiet signal -- check the range."
            )
    return samples


def mean(samples, ch):
    return sum(samples[ch]) / len(samples[ch])


def close(h):
    dwf.FDwfAnalogOutConfigure(h, c_int(0), c_int(0))
    dwf.FDwfDeviceClose(h)
