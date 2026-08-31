#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The mechanism shared by tools/sim/check_<example>_sim.py.

Each of those scripts reads an ngspice batch-mode log, pulls a handful of
named values out of it, and compares them against the reference numbers
published in that example's README. The reading and comparing is identical
everywhere; what differs is the numbers, the units, and -- most
importantly -- what to say when a value is missing. A missing measurement
means something specific per circuit (the ring failed to start
oscillating; the SR latch never set), and that sentence is the whole value
of the check to someone meeting it for the first time, so it stays in the
per-example script and is passed in here as `hint`.

Nothing in this module knows about any particular example. It is a helper,
not a framework: a checker that needs to do something different should just
do it, rather than growing an option here.
"""

from __future__ import annotations

import re
import sys


def read_log(usage: str) -> tuple[str, str]:
    """(log_path, text) from argv, or exit 2 with `usage`."""
    if len(sys.argv) != 2:
        print(f"usage: {usage} <ngspice-log>", file=sys.stderr)
        raise SystemExit(2)
    path = sys.argv[1]
    return path, open(path).read()


def measurements(
    text: str,
    names,
    log_path: str,
    *,
    hint: str,
    scale: float = 1.0,
) -> dict[str, float] | None:
    """Pull each of `names` out of an ngspice log, or explain what is wrong.

    ngspice writes both `.meas` results and plain `print` output as
    "name = value", so one pattern covers both. Returns None (having
    printed `hint` and the tail of the log) if any name is missing, which
    is always worth reporting with the log rather than as a bare failure:
    the cause is nearly always visible in the last twenty lines.

    `scale` multiplies every value -- 1e9 to read seconds out as
    nanoseconds, say -- because the reference numbers are published in
    whatever unit the README's table uses.
    """
    values: dict[str, float] = {}
    for name in names:
        m = re.search(rf"^\s*{name}\s*=\s*([0-9.eE+-]+)", text, re.MULTILINE)
        if not m:
            print(
                f"FAIL: no '{name}' measurement found in {log_path}. {hint}\n\n"
                "Tail of the log:\n" + "\n".join(text.splitlines()[-20:])
            )
            return None
        values[name] = float(m.group(1)) * scale
    return values


def compare_relative(values, reference, tolerance, *, fmt) -> bool:
    """Each value within +-`tolerance` (a fraction) of its reference.

    Prints one line per measurement whether it passes or not: seeing the
    numbers that were fine is what makes the one that is not legible.
    `fmt` renders a value with its unit, so this module never has to know
    whether it is looking at volts, hertz or nanoseconds.
    """
    ok = True
    for name, ref in reference.items():
        measured = values[name]
        # sorted(), because a negative reference puts the two products the
        # other way round -- the current source's sink leg is about -200uA,
        # where ref*(1+tol) is the *lower* bound.
        low, high = sorted((ref * (1 - tolerance), ref * (1 + tolerance)))
        in_range = low <= measured <= high
        ok = ok and in_range
        print(
            f"{name}: {fmt(measured)} (reference {fmt(ref)}, expected "
            f"{fmt(low)} to {fmt(high)}) -- "
            f"{'ok' if in_range else 'OUT OF RANGE'}"
        )
    return ok


def compare_absolute(values, reference, tolerance, *, fmt) -> bool:
    """Each value within +-`tolerance` in absolute units of its reference.

    For quantities whose reference sits at or near zero, where a fraction
    of the reference is meaningless -- the SR latch's stored low levels are
    a few millivolts from ground, so 5% of them is nothing.
    """
    ok = True
    for name, ref in reference.items():
        measured = values[name]
        in_range = abs(measured - ref) <= tolerance
        ok = ok and in_range
        print(
            f"{name}: {fmt(measured)} (reference {fmt(ref)}, expected within "
            f"+-{fmt(tolerance)} of it) -- {'ok' if in_range else 'OUT OF RANGE'}"
        )
    return ok


def verdict(ok: bool, *, subject: str, readme: str, causes: str) -> int:
    """The closing paragraph, and the exit code.

    A failure here is not necessarily a bug: rebuilding the device library
    or changing the circuit moves these numbers legitimately. What must not
    happen is the reference moving in one place and not the other, so the
    message names both places every time.
    """
    if ok:
        print(f"\nOK -- {subject} as-drawn/as-routed simulation matches the "
              f"reference measurements.")
        return 0
    print(
        f"\nSomething about {subject}'s simulated behavior has changed. If "
        f"this is an intentional change ({causes}), update the reference "
        f"numbers here and in {readme} together; otherwise treat this as a "
        f"real regression."
    )
    return 1
