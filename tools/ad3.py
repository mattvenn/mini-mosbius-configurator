#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Minimal Digilent WaveForms (AD3/AD2) wrapper for bench measurements.

Only what the measurement scripts in tools/ need: open the device, drive
W1, capture the two scope channels, and set the programmable supplies. No
dependency beyond ctypes and the WaveForms install itself.

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

import contextlib
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
    supply: driving a pin above VAPWR conducts through its ESD diode.

    **This makes levels, not edges.** Changing a DC output's offset is
    slewed over milliseconds, so calling this to step a pin from 0 to 3.3 V
    produces a slow ramp, not a transition -- fine for a static level, and
    useless for anything being timed. It does not announce itself: the
    capture comes back full of a clean, plausible, entirely wrong edge. To
    drive a real edge, configure a waveform (funcSquare/funcPulse/funcCustom)
    and let the generator clock it out; see tools/measure_srlatch_edge_ad3.py.
    """
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


# ---------------------------------------------------------------------------
# Programmable supplies (V+ / V-)
# ---------------------------------------------------------------------------
#
# These are here for `ibias`. The chip's bias input is a *current*, and only
# the later ETR demoboards carry the RP2350-controlled circuit that makes
# one -- on an older board `tt.analog_current_source` is None and the bias
# pin is simply unfed. So a bench measurement of any example that mirrors
# ibias -- diffamp, currentsource, otabuf -- makes the current the crude
# way, by driving V+ through a series resistor into the bias pin. See
# examples/README.md on ibias for what that node is.
#
# **There are two enables, and forgetting the second one is silent.** Each
# supply channel has its own Enable node, *and* the instrument has one
# master switch (FDwfAnalogIOEnableSet). Set the voltage and the channel
# enable but not the master and the rail just sits at 0 V, with every call
# returning success. supply() sets both.
#
# Channel and node numbers are deliberately not hard-coded. The SDK reports
# its own names -- "Positive Supply" labelled "V+", with nodes "Enable",
# "Voltage", "Current" -- and they are not identical across AD2 and AD3, so
# they are looked up per device rather than trusted to a constant.


def _io_map(h):
    """{channel index: (name, label, {node name: (index, units)})}, cached."""
    cache = getattr(_io_map, "cache", {})
    if h.value in cache:
        return cache[h.value]
    count = c_int()
    dwf.FDwfAnalogIOChannelCount(h, byref(count))
    channels = {}
    for idx in range(count.value):
        name, label = ctypes.create_string_buffer(32), ctypes.create_string_buffer(16)
        dwf.FDwfAnalogIOChannelName(h, c_int(idx), name, label)
        nodes_n = c_int()
        dwf.FDwfAnalogIOChannelInfo(h, c_int(idx), byref(nodes_n))
        nodes = {}
        for n in range(nodes_n.value):
            nname = ctypes.create_string_buffer(32)
            nunits = ctypes.create_string_buffer(16)
            dwf.FDwfAnalogIOChannelNodeName(h, c_int(idx), c_int(n), nname, nunits)
            nodes[nname.value.decode().strip().lower()] = (
                n, nunits.value.decode().strip())
        channels[idx] = (name.value.decode().strip(),
                         label.value.decode().strip(), nodes)
    cache[h.value] = channels
    _io_map.cache = cache
    return channels


def _find_supply(h, channel):
    """Match "V+" / "v-" / "positive" against the device's own channel names."""
    wanted = channel.strip().lower()
    for idx, (name, label, nodes) in _io_map(h).items():
        if wanted == label.lower() or wanted in name.lower():
            return idx, name, label, nodes
    listing = "\n".join(
        f"    {label or '(no label)'}  {name}  nodes: "
        + (", ".join(sorted(nodes)) or "(none)")
        for _, (name, label, nodes) in sorted(_io_map(h).items()))
    raise RuntimeError(
        f"this device has no analog IO channel matching {channel!r}.\n"
        f"  What it does report:\n{listing or '    (nothing)'}\n"
        "  Match on the label (V+, V-) or any part of the name.")


def supply(h, volts, channel="V+", current_limit=None, settle=0.3):
    """Set one programmable rail and turn it on. Returns supply_status().

    `volts` is clamped to nothing -- the device's own limits are read back
    and a value outside them is refused by name, since silently delivering a
    different rail than you asked for is how a bias current goes wrong
    without anyone noticing.

    Driving the chip's `ibias` pin: pick the resistor so most of the rail is
    dropped across it. The bias node is a diode-connected NMOS that sets its
    own gate voltage, so it is the *difference* that makes the current, and
    a large drop makes the current insensitive to what that node happens to
    sit at.

    **V+ does not reach 0 V.** On the AD3 it is settable over +0.5..+5.0 V
    in 4500 steps, and V- over -5.0..-0.5 V in 4000 (read off the device
    2026-08-29). So a rail cannot be brought gently up from zero, and
    "supply off" is supplies_off() or close(), not supply(h, 0).
    """
    idx, name, label, nodes = _find_supply(h, channel)
    if "voltage" not in nodes:
        raise RuntimeError(
            f"{label or name} has no Voltage node, so it is not a settable "
            f"supply.\n  Its nodes are: {', '.join(sorted(nodes)) or '(none)'}")

    node, _units = nodes["voltage"]
    lo, hi, steps = c_double(), c_double(), c_int()
    dwf.FDwfAnalogIOChannelNodeSetInfo(
        h, c_int(idx), c_int(node), byref(lo), byref(hi), byref(steps))
    if not (min(lo.value, hi.value) <= volts <= max(lo.value, hi.value)):
        raise RuntimeError(
            f"{volts:+.3f} V is outside what {label or name} can deliver "
            f"({lo.value:+.3f} to {hi.value:+.3f} V).")

    dwf.FDwfAnalogIOChannelNodeSet(h, c_int(idx), c_int(node), c_double(volts))
    if current_limit is not None and "current" in nodes:
        dwf.FDwfAnalogIOChannelNodeSet(
            h, c_int(idx), c_int(nodes["current"][0]), c_double(current_limit))
    if "enable" in nodes:
        dwf.FDwfAnalogIOChannelNodeSet(
            h, c_int(idx), c_int(nodes["enable"][0]), c_double(1))
    dwf.FDwfAnalogIOEnableSet(h, c_int(1))  # the master switch, see above
    time.sleep(settle)
    return supply_status(h, channel)


def supply_status(h, channel="V+"):
    """{'voltage': V, 'current': A} for one rail, as the instrument reports it.

    **The voltage is measured, not echoed back** -- checked against an AD3
    on 2026-08-29, where asking for 0.500/1.370/2.900/5.000 V read back
    0.504/1.376/2.910/5.010, about +0.3% throughout. So this is the number
    to record for V+, in preference to the value you asked for.

    The current node was 0.000000 A at every one of those settings, with
    nothing connected. That is the right answer for an open circuit and
    therefore no evidence the current monitor works; it has not been read
    under a known load.

    None of this establishes an injected bias current on its own. The rail
    is one end of the resistor and the chip's bias pin is the other, and
    that pin sets its own voltage, so put a scope channel on the pin and
    compute (V_supply - V_pin) / R.
    """
    idx, _name, _label, nodes = _find_supply(h, channel)
    dwf.FDwfAnalogIOStatus(h)
    out = {}
    for key in ("voltage", "current"):
        if key in nodes:
            value = c_double()
            dwf.FDwfAnalogIOChannelNodeStatus(
                h, c_int(idx), c_int(nodes[key][0]), byref(value))
            out[key] = value.value
    return out


def supplies_off(h):
    """Drop both rails via the master switch."""
    dwf.FDwfAnalogIOEnableSet(h, c_int(0))


@contextlib.contextmanager
def device():
    """`with ad3.device() as h:` -- open, and close on the way out either way.

    Worth using once a supply is involved: an exception raised between
    open_device() and close() otherwise leaves V+ still driving the chip.
    """
    handle = open_device()
    try:
        yield handle
    finally:
        close(handle)


def close(h):
    """Stop W1 and drop the supplies before letting go of the device.

    The rails go off here on purpose: a script that exits with V+ still
    feeding the chip's bias pin leaves the chip biased by an instrument
    nobody is watching. Keep the handle open if you want a rail to persist
    across a measurement.
    """
    dwf.FDwfAnalogOutConfigure(h, c_int(0), c_int(0))
    supplies_off(h)
    dwf.FDwfDeviceClose(h)
