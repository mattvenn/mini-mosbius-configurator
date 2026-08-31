#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Minimal Digilent WaveForms (AD3/AD2) wrapper for bench measurements.

Only what the measurement scripts in tools/ need: open the device, drive
W1, capture the two scope channels (untriggered for levels, triggered for
timing), and set the programmable supplies. No dependency beyond ctypes and
the WaveForms install itself.

**Installing the SDK on macOS is two steps, not one.** `brew install
--cask waveforms` puts the *application* in /Applications, and the app
carries its own private copy of the framework -- so the GUI finds your
AD3 while any script you write reports 0 devices and 'Adept NOK'. The
DMG contains a second, standalone `dwf.framework` meant for
/Library/Frameworks, and the SDK only works once it is there:

    hdiutil attach ~/Library/Caches/Homebrew/downloads/*waveforms*.dmg
    sudo cp -R /Volumes/WaveForms/dwf.framework /Library/Frameworks/

**Linux has no such trap -- the WaveForms .deb/.rpm installs a plain
shared library, not a framework with a private copy.** `_dwf_candidates()`
tries the handful of names/locations that install has used, then falls
back to `ctypes.util.find_library("dwf")`. If none of those match your
install, set `AD3_DWF_PATH` to the library's path directly rather than
editing this file -- `ldconfig -p | grep -i dwf` finds it.

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
import ctypes.util
import os
import platform
import time
from ctypes import byref, c_double, c_int, c_ubyte


def _dwf_candidates() -> list[str]:
    """Library names/paths worth trying, in order, for the current OS.

    Every WaveForms install puts the library somewhere different: a
    macOS framework bundle, a Linux shared library the package manager
    already knows about, or a Windows DLL on PATH. None of these is
    "the" path -- they are guesses ordered by how each platform's
    installer has actually placed it.
    """
    system = platform.system()
    if system == "Darwin":
        return ["/Library/Frameworks/dwf.framework/dwf"]
    if system == "Windows":
        return ["dwf.dll"]
    return [  # Linux: the .deb/.rpm installs a plain shared library.
        "libdwf.so",
        "libdwf.so.3",
        "/usr/lib/libdwf.so",
        "/usr/lib/x86_64-linux-gnu/libdwf.so",
        "/usr/local/lib/libdwf.so",
    ]


DWF_PATH = os.environ.get("AD3_DWF_PATH")
_candidates = [DWF_PATH] if DWF_PATH else _dwf_candidates()
_found = ctypes.util.find_library("dwf")
if _found and _found not in _candidates:
    _candidates.append(_found)

dwf = None
for _candidate in _candidates:
    try:
        dwf = ctypes.cdll.LoadLibrary(_candidate)
        DWF_PATH = _candidate
        break
    except OSError:
        continue

if dwf is None:  # pragma: no cover - depends on the host install
    tried = "\n".join(f"    {c}" for c in _candidates)
    if platform.system() == "Darwin":
        hint = (
            "  Installing the WaveForms app alone is not enough: the app keeps a\n"
            "  private copy of the framework, so the GUI sees your Analog Discovery\n"
            "  while scripts report no devices. Copy the standalone framework from\n"
            "  the DMG into /Library/Frameworks -- see the note at the top of\n"
            "  tools/ad3/ad3.py for the two commands."
        )
    else:
        hint = (
            "  Check the WaveForms runtime is actually installed (not just the\n"
            "  GUI app), then find where it put the library:\n\n"
            "      ldconfig -p | grep -i dwf\n\n"
            "  and set AD3_DWF_PATH to that path -- no need to edit this file."
        )
    raise SystemExit(
        f"can't load the WaveForms SDK. Tried:\n{tried}\n\n{hint}"
    )

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
    # Fail here, not with a confusing bench result later: an underpowered
    # AD3 can still open and report samples, they are just not
    # trustworthy. See check_power()'s docstring for the real numbers this
    # was verified against.
    #
    # **iusb ramps up for a moment after FDwfDeviceOpen, and reading it
    # immediately can catch it still rising** -- seen on a known-good cable
    # 2026-08-31, where the very first check_power() failed and a second
    # run moments later passed with nothing else changed. So this polls for
    # up to 1.5 s and only fails if the reading is still low at the end of
    # it, the same shape as wait_supply_stable() below.
    warning = None
    deadline = time.time() + 1.5
    while time.time() < deadline:
        warning = check_power(handle)
        if warning is None:
            break
        time.sleep(0.2)
    if warning:
        dwf.FDwfDeviceClose(handle)
        raise SystemExit(warning)
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
    and let the generator clock it out; see tools/ad3/measure_srlatch_edge_ad3.py.
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
    scope_setup.windows = {ch: scope_setup.window for ch in channels}
    time.sleep(settle)


def scope_setup_channels(h, specs, rate=1e5, nsamples=4000, settle=2.0):
    """Like scope_setup(), but give each channel its own window.

    `specs` maps channel index to (range, offset) in volts, where range is
    the peak-to-peak SPAN -- see this module's docstring for the trap in
    that word. The AD3 offers 5 V and 50 V and nothing in between, so the
    span is barely a choice; the offset is, and it is what centres a
    channel on the thing it is actually looking at.

    scope_setup() puts both channels on one window, which is right when
    both are watching chip pins. It is wrong for a current measurement,
    where the two channels look at quantities that do not overlap: one
    sits differentially across a sense resistor and sees a few hundred
    millivolts about zero, while the other watches a pad swinging across
    the whole supply. On the chip window the shunt channel would spend its
    whole range on a signal that never leaves the bottom eighth of it, and
    on the shunt's window the pad channel would clip immediately.
    """
    for ch, (rng, offset) in specs.items():
        dwf.FDwfAnalogInChannelEnableSet(h, c_int(ch), c_int(1))
        dwf.FDwfAnalogInChannelRangeSet(h, c_int(ch), c_double(rng))
        dwf.FDwfAnalogInChannelOffsetSet(h, c_int(ch), c_double(offset))
    dwf.FDwfAnalogInFrequencySet(h, c_double(rate))
    dwf.FDwfAnalogInBufferSizeSet(h, c_int(nsamples))
    dwf.FDwfAnalogInConfigure(h, c_int(1), c_int(0))
    scope_setup.windows = {ch: (offset - rng / 2, offset + rng / 2)
                           for ch, (rng, offset) in specs.items()}
    # Kept for check_clipping()'s fallback and for anything that reads it:
    # the widest of the per-channel windows, so it can only be pessimistic.
    scope_setup.window = (min(lo for lo, _ in scope_setup.windows.values()),
                          max(hi for _, hi in scope_setup.windows.values()))
    time.sleep(settle)


def acquire(h, nsamples=4000, channels=(0, 1), tag="", allow_flat=False):
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
    return check_clipping(out, tag, allow_flat=allow_flat)


def check_clipping(samples, tag="", allow_flat=False):
    """Refuse a capture that ran into the range edge, or came back flat.

    `allow_flat` waives only the second test, and exists for the one
    reading that is legitimately allowed to be a dead constant: a
    deliberate zero, taken with the signal path disconnected, to measure a
    channel's own offset. Everywhere else a perfectly flat capture is a
    railed ADC and has to stay an error.
    """
    windows = getattr(scope_setup, "windows", {})
    fallback = getattr(scope_setup, "window", (-2.5, 2.5))
    for ch, values in samples.items():
        lo, hi = windows.get(ch, fallback)
        edge = 0.02 * (hi - lo)
        if max(values) > hi - edge or min(values) < lo + edge:
            raise RuntimeError(
                f"{tag}channel {ch + 1} reached {min(values):+.3f}..{max(values):+.3f} V, "
                f"at the edge of its {lo:+.2f}..{hi:+.2f} V window.\n"
                "  Widen the range or move the offset: past the edge the AD3 keeps\n"
                "  reporting numbers, they are just the ceiling rather than the signal."
            )
        if max(values) == min(values) and not allow_flat:
            raise RuntimeError(
                f"{tag}channel {ch + 1} is dead flat at {values[0]:+.4f} V over "
                f"{len(values)} samples.\n"
                "  That is a railed ADC, not a quiet signal -- check the range."
            )
    return samples


def mean(samples, ch):
    return sum(samples[ch]) / len(samples[ch])


# ---------------------------------------------------------------------------
# Triggered capture
# ---------------------------------------------------------------------------
#
# For timing anything: a slew rate, a settling time constant, a propagation
# delay. The untriggered acquire() above is for levels, and it cannot do
# these -- an event tens or hundreds of nanoseconds long inside a stimulus
# period of tens of microseconds lands inside one or two samples of a
# capture slow enough to span the period. Triggered at the device's full
# rate, the same event is hundreds of samples wide.
#
# **Drive the edge as a waveform, never by moving a DC offset.** See
# wavegen()'s docstring: an offset change is slewed over milliseconds and
# produces a clean, plausible, entirely wrong ramp. square_wave() below
# configures the generator to clock the edge out itself.
#
# **The generator is not infinitely fast either, and on these circuits that
# matters.** An Analog Discovery's output amplifier takes tens of
# nanoseconds to move volts, so a measurement of something comparably fast
# is partly a measurement of the stimulus. Always capture the driving
# channel too and report its own edge beside the result, so the margin is
# visible rather than assumed. tools/ad3/measure_srlatch_edge_ad3.py learned
# this the expensive way.

TRIGSRC_DETECTOR_ANALOG_IN = 2
TRIGTYPE_EDGE = 0
SLOPE_RISE, SLOPE_FALL = 0, 1


def max_rate(h) -> float:
    lo, hi = c_double(), c_double()
    dwf.FDwfAnalogInFrequencyInfo(h, byref(lo), byref(hi))
    return hi.value


def scope_setup_triggered(h, rate, nsamples, trigger_channel, trigger_level,
                          rising=True, position=0.0, channels=(0, 1),
                          rng=CHIP_RANGE, offset=CHIP_OFFSET):
    """Arm both channels to capture around an edge on `trigger_channel`.

    `position` is where the trigger sits in the buffer, in seconds relative
    to its centre -- 0.0 centres it, so half the buffer is pre-trigger,
    which is what you want for measuring an edge you also need the baseline
    of. Auto-timeout is disabled: a capture that never triggers should hang
    visibly rather than quietly return a buffer of untriggered noise that
    looks like a measurement.
    """
    for ch in channels:
        dwf.FDwfAnalogInChannelEnableSet(h, c_int(ch), c_int(1))
        dwf.FDwfAnalogInChannelRangeSet(h, c_int(ch), c_double(rng))
        dwf.FDwfAnalogInChannelOffsetSet(h, c_int(ch), c_double(offset))
    dwf.FDwfAnalogInFrequencySet(h, c_double(rate))
    dwf.FDwfAnalogInBufferSizeSet(h, c_int(nsamples))
    dwf.FDwfAnalogInTriggerAutoTimeoutSet(h, c_double(0.0))
    dwf.FDwfAnalogInTriggerSourceSet(h, c_ubyte(TRIGSRC_DETECTOR_ANALOG_IN))
    dwf.FDwfAnalogInTriggerTypeSet(h, c_int(TRIGTYPE_EDGE))
    dwf.FDwfAnalogInTriggerChannelSet(h, c_int(trigger_channel))
    dwf.FDwfAnalogInTriggerLevelSet(h, c_double(trigger_level))
    dwf.FDwfAnalogInTriggerConditionSet(
        h, c_int(SLOPE_RISE if rising else SLOPE_FALL))
    dwf.FDwfAnalogInTriggerPositionSet(h, c_double(position))
    dwf.FDwfAnalogInConfigure(h, c_int(1), c_int(1))
    scope_setup.window = (offset - rng / 2, offset + rng / 2)
    # Both, not just the first: check_clipping() prefers the per-channel
    # dict, so leaving a stale one behind from an earlier
    # scope_setup_channels() would let it check this capture against a
    # window that is no longer set on the hardware.
    scope_setup.windows = {ch: scope_setup.window for ch in channels}


def square_wave(h, ch, low, high, freq, symmetry=50.0, phase=0.0):
    """A real edge: the generator clocks it out at its own full speed."""
    amp, offset = (high - low) / 2.0, (high + low) / 2.0
    dwf.FDwfAnalogOutNodeEnableSet(h, c_int(ch), c_int(0), c_int(1))
    dwf.FDwfAnalogOutNodeFunctionSet(h, c_int(ch), c_int(0), c_ubyte(funcSquare))
    dwf.FDwfAnalogOutNodeFrequencySet(h, c_int(ch), c_int(0), c_double(freq))
    dwf.FDwfAnalogOutNodeAmplitudeSet(h, c_int(ch), c_int(0), c_double(amp))
    dwf.FDwfAnalogOutNodeOffsetSet(h, c_int(ch), c_int(0), c_double(offset))
    dwf.FDwfAnalogOutNodeSymmetrySet(h, c_int(ch), c_int(0), c_double(symmetry))
    dwf.FDwfAnalogOutNodePhaseSet(h, c_int(ch), c_int(0), c_double(phase))


def capture_triggered(h, nsamples, channels=(0, 1), timeout=5.0, tag=""):
    """Wait for one trigger and return {channel: samples}. None on timeout."""
    dwf.FDwfAnalogInConfigure(h, c_int(0), c_int(1))
    status = c_ubyte()
    deadline = time.time() + timeout
    while True:
        dwf.FDwfAnalogInStatus(h, c_int(1), byref(status))
        if status.value == _STATE_DONE:
            break
        if time.time() > deadline:
            return None
        time.sleep(0.001)
    out = {}
    for ch in channels:
        buf = (c_double * nsamples)()
        dwf.FDwfAnalogInStatusData(h, c_int(ch), buf, c_int(nsamples))
        out[ch] = list(buf)
    return check_clipping(out, tag)


def crossing(values, level, rising=True, dt=1.0):
    """Time of the first crossing of `level`, interpolated between samples.

    Interpolation is the point: it makes the resolution finer than the
    sample interval, which is what lets a handful of samples across an edge
    still time it usefully.
    """
    for i in range(1, len(values)):
        a, b = values[i - 1], values[i]
        if (rising and a < level <= b) or (not rising and a > level >= b):
            span = b - a
            frac = 0.0 if span == 0 else (level - a) / span
            return (i - 1 + frac) * dt
    return None


# ---------------------------------------------------------------------------
# Digital output (DIO) -- a stimulus edge that isn't W1's DAC+amplifier
# ---------------------------------------------------------------------------
#
# tools/ad3/measure_inverter_edge_ad3.py measured square_wave()'s own edge at
# 74 ns (10%-90%) on ua1, only a 1.3x margin over the 95 ns it measured on
# the inverter's output -- too close to trust, since W1 drives through a DAC
# and an output amplifier that takes tens of nanoseconds to move volts. A
# DIO pin switches through a plain logic buffer instead, a different circuit
# that may have a real edge fast enough to matter here. Untested before
# 2026-08-31.
#
# **It stayed untested in the sense that matters.** DIO0 measured 82 ns
# here, close to W1's 74 ns -- but per the AD3 datasheet (files.digilent.com/
# datasheets/Analog-Discovery-3-Datasheet.pdf, sec. 6.1) the analog input
# channels (1+/2+, whatever this is observed through) are bandwidth-limited
# to 9 MHz @ -3dB without a BNC adapter, the same ~9 MHz the AWG output is
# spec'd at (sec. 6.2). DIO pins are explicitly NOT BNC-adapter pins ("all
# other pins pass through... to a 100 mil 2x15 MTE header") and have no
# published bandwidth of their own. So W1's and DIO0's edges landing in the
# same ballpark is consistent with both being observed through the same
# 9 MHz-limited scope channel, not with both sources actually being equally
# slow -- DIO0's true edge speed is still unmeasured. A BNC adapter would
# raise the scope's own bandwidth to 30+ MHz without touching DIO0 at all,
# which is the one upgrade that could actually separate these two
# possibilities.
#
# **These wrap the SDK's Digital Out (pattern generator) API for the first
# time in this codebase.** Every other function in this file was checked
# against real hardware before being trusted (see this file's docstring and
# CLAUDE.md); these have not been yet. If a call raises `AttributeError`,
# the function name is wrong -- check the actual declaration in dwf.h
# (`/Library/Frameworks/dwf.framework/Headers/dwf.h` on macOS, wherever the
# Linux package put it otherwise) rather than assuming the concept is wrong.
#
# **DIO pins are a separate physical connector from W1/W2/1+/2+.** Those are
# flying leads off the analog front end; the digital channels are on their
# own pin header (DIO0..DIO15 plus grounds). Bring the pin you use to an
# analog scope channel with a jumper wire if you want to see what it
# actually delivers, same as every stimulus in this file.

DIGITAL_OUT_TYPE_PULSE = 0


def digital_out_square(h, channel, freq, symmetry=50.0):
    """Free-running square wave on one DIO pin, at whatever logic level the
    device's digital bank runs at (not settable here the way an AnalogOut
    amplitude is -- this device's `power_status()` shows no separate DIO/VIO
    channel, which suggests it is fixed, presumably at 3.3 V to match this
    chip's rail, but that has not been confirmed against a scope).

    Frequency is set as clock-divider-and-counter, not a direct Hz value,
    because that is how the SDK's pulse generator works: an internal clock
    (read back, never assumed) divided down, then held low for
    `low_ticks` of that divided clock and high for `high_ticks`.
    """
    clock = c_double()
    dwf.FDwfDigitalOutInternalClockInfo(h, byref(clock))
    period_ticks = clock.value / freq
    high_ticks = max(1, round(period_ticks * symmetry / 100.0))
    low_ticks = max(1, round(period_ticks - high_ticks))
    dwf.FDwfDigitalOutReset(h)
    dwf.FDwfDigitalOutEnableSet(h, c_int(channel), c_int(1))
    dwf.FDwfDigitalOutTypeSet(h, c_int(channel), c_int(DIGITAL_OUT_TYPE_PULSE))
    dwf.FDwfDigitalOutDividerSet(h, c_int(channel), c_int(1))
    dwf.FDwfDigitalOutCounterSet(h, c_int(channel), c_int(low_ticks), c_int(high_ticks))
    dwf.FDwfDigitalOutConfigure(h, c_int(1))


def digital_out_stop(h):
    """Stop the digital pattern generator -- one engine for all DIO
    channels, unlike AnalogOut's per-channel Configure. `close()` does not
    call this, so a script using digital_out_square() must call it itself.
    """
    dwf.FDwfDigitalOutConfigure(h, c_int(0))


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


def power_status(h) -> dict[str, dict[str, float]]:
    """{channel label or name: {node name: value}} for every AnalogIO
    channel the device reports -- not just the settable V+/V- supplies
    `supply()` covers.

    WaveForms' own app can refuse to arm the analog front end at all --
    "the analog circuit of the device is turned off ... PLL Not Locked" --
    when the USB port cannot deliver the current the AD3 wants, and that
    condition is invisible to a script that only ever reads back the
    channels it explicitly asked to set. The AD3 exposes its own input
    power (and on some units, temperature) as ordinary AnalogIO channels
    alongside V+/V-, read the same way `supply_status()` reads a rail.

    **Which channel/node names actually carry that information is not
    hard-coded here, deliberately** -- see `_io_map()`'s docstring for why:
    a name guessed instead of read from the device is how a check ends up
    silently never firing. Call this once and look at what comes back
    before trusting `check_power()`'s pattern match on it.

    On an AD3 (verified 2026-08-31, `tools/ad3/check_ad3_power.py`) that
    information sits in one channel labelled "System", not one labelled
    "USB": nodes `vusb`/`iusb` (and `vaux`/`iaux`), reading 4.91 V / 656 mA
    on a good cable and 4.73 V / 105 mA on the cable/port that triggered
    WaveForms' "analog circuit is turned off" warning. The *current*
    collapsed 6x while the voltage barely moved -- the port was current-
    limiting rather than sagging -- which is why `check_power()` gates on
    `iusb`, not on a voltage threshold.
    """
    dwf.FDwfAnalogIOStatus(h)
    out = {}
    for idx, (name, label, nodes) in _io_map(h).items():
        values = {}
        for nname, (nidx, _units) in nodes.items():
            value = c_double()
            dwf.FDwfAnalogIOChannelNodeStatus(h, c_int(idx), c_int(nidx), byref(value))
            values[nname] = value.value
        out[label or name] = values
    return out


def check_power(h, min_iusb_amps=0.5, min_vusb_volts=4.5) -> str | None:
    """None if the device's own USB input power looks healthy, else a
    warning naming which reading does not.

    Matches on the *node* name (`vusb`/`iusb`, or `vaux`/`iaux`) rather
    than the channel label -- on the one AD3 this has been checked against
    the channel is called "System", not "USB", so a label match never
    fires at all. Any channel/node absent is silently skipped rather than
    treated as a failure, since a device or SDK version that does not
    expose it says nothing about whether the underlying problem exists.

    **`iusb` is the one to trust, not `vusb`.** Verified 2026-08-31
    (`tools/ad3/check_ad3_power.py`, both dumps recorded in
    `power_status()`'s docstring): the cable/port that made WaveForms'
    own app report "the analog circuit of the device is turned off" moved
    vusb from 4.91 to 4.73 V -- barely past `min_vusb_volts` -- while iusb
    fell from 656 to 105 mA, well past `min_iusb_amps`. The port was
    current-limiting rather than sagging, so a voltage-only check would
    have missed this specific, real fault. Both are still checked, since a
    long/thin cable's resistive drop is a different failure mode that
    would show up as low voltage first.
    """
    problems = []
    for label, nodes in power_status(h).items():
        iusb = next((v for k, v in nodes.items() if "iusb" in k.lower()), None)
        vusb = next((v for k, v in nodes.items() if "vusb" in k.lower()), None)
        if iusb is not None and iusb < min_iusb_amps:
            problems.append(f"{label}: iusb reads {iusb * 1000:.0f} mA "
                            f"(want >= {min_iusb_amps * 1000:.0f} mA)")
        if vusb is not None and vusb < min_vusb_volts:
            problems.append(f"{label}: vusb reads {vusb:.2f} V "
                            f"(want >= {min_vusb_volts:.2f} V)")
    if not problems:
        return None
    return (
        "the Analog Discovery itself is reporting low input power:\n    "
        + "\n    ".join(problems)
        + "\n\n  This is the same condition WaveForms' own app shows as \"the analog\n"
          "  circuit of the device is turned off\" / \"PLL Not Locked\" -- the AD3\n"
          "  wants ~3 W / 600 mA and the USB port is not delivering it, so nothing\n"
          "  measured while this is true is trustworthy, chip or no chip. Try a\n"
          "  different cable/port (rear ports over front, no hub/extension), or a\n"
          "  powered hub / 5 V auxiliary supply."
    )


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


def wait_supply_stable(h, channel="V+", tol=0.004, timeout=8.0, interval=0.2):
    """Poll a rail until successive readings agree, and return the last.

    **A rail does not reach its new setting when the call returns, and going
    down is far slower than going up.** Nothing discharges the supply's own
    output capacitance except whatever load is on it, so stepping V+ from
    3.28 V to 1.65 V into a 20 kOhm resistor takes seconds, not the
    fraction supply()'s settle waits. Reading the voltage too early gave a
    bias current 60% too high on one point of a slew-versus-bias sweep,
    which is worse than a slow measurement: the rail had reached the right
    place by the time the captures ran, so the *reading* was wrong while the
    measurement was right, and the two disagreed for no visible reason.
    """
    last = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        now = supply_status(h, channel).get("voltage")
        if now is None:
            return None
        if last is not None and abs(now - last) <= tol:
            return now
        last = now
        time.sleep(interval)
    return last


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
