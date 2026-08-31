#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Dump every AnalogIO channel/node the Analog Discovery reports.

Written to chase a specific symptom: WaveForms' own app can refuse to arm
the analog front end at all --

    The analog circuit of the device is turned off.
    AVCC3V3
    The device needs at least 3W/600mA. To satisfy this: ...
    CDCE Not Locked.
    PLL Not Locked.

-- when the USB port cannot deliver the current the AD3 wants, and that is
invisible to a script that only reads back the channels it explicitly set
(V+/V-). This just prints whatever `ad3.power_status()` gets back, raw, so
we can see which channel and node actually carries that condition on real
hardware, and at what value, before `ad3.check_power()`'s "usb"/"aux" name
match and 4.65 V threshold are trusted for anything.

Run it twice: once with the setup working normally, once (if you can
reproduce it safely) with the cable/port that triggered the WaveForms
warning above, and compare the two dumps -- whatever changed between them
is the field worth matching on.

    python3 tools/ad3/check_ad3_power.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ad3  # noqa: E402


def main() -> None:
    handle = ad3.open_device()
    try:
        status = ad3.power_status(handle)
        print("\n  AnalogIO channels this device reports:\n")
        for label, nodes in status.items():
            print(f"    {label}")
            for name, value in nodes.items():
                print(f"        {name:<12s} {value:.4f}")
        warning = ad3.check_power(handle)
        print()
        if warning:
            print("  check_power() says:\n\n  " + warning.replace("\n", "\n  "))
        else:
            print("  check_power() found nothing matching its 'usb'/'aux' + "
                  "'volt' pattern below 4.65 V.\n"
                  "  That does NOT mean the device is healthy -- it may mean the\n"
                  "  pattern above doesn't match this device's real channel names.\n"
                  "  Compare the dump above against what WaveForms' own app shows.")
    finally:
        ad3.close(handle)


if __name__ == "__main__":
    main()
