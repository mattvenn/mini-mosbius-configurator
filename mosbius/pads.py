# SPDX-License-Identifier: Apache-2.0
"""Which PCB pad to clip a probe onto, derived rather than remembered.

A design's `ua[k]` is not a pad letter, and the relationship is not fixed:
Tiny Tapeout muxes the chip's analog pins, so which internal analog index
a project's `ua[k]` lands on depends on where that project was placed on
that shuttle. Hard-coding "ua1 is pad C" would be right for
`tt_um_tnt_mosbius` on ttsky25a and wrong for the same design on the next
shuttle -- so nothing here hard-codes it. Two lookups compose:

1. **design `ua[k]` -> internal analog index**, per project, per shuttle.
   Published in the shuttle index, e.g.
   https://index.tinytapeout.com/ttsky25a.json, as each project's
   `analog_pins` list. The copy of the index on the demoboard itself is
   stripped to address/clock_hz/macro/title, so this comes over HTTP and
   is cached under `build/`.

2. **internal analog index -> PCB pad letter**, a property of the *board*,
   identical for every design on it. That is PAD_LETTERS below.

PAD_LETTERS is the one piece that is written down rather than derived, and
it is worth knowing how firmly. It was read off the Analog pins table on
https://tinytapeout.com/chips/ttsky25a/tt_um_tnt_mosbius, whose `ua` ->
PCB pin -> internal index columns give indices 0..5 as pads C, D, F, G, J,
K -- the carrier's six analog pads in letter order, skipping E, H and I.
That is one project's table, not a Tiny Tapeout specification, so if a
board ever letters its analog pads differently this is the line that has
to change, and a wrong pad shows up as a probe reading nothing rather than
as an error. Verified on hardware 2026-08-28: `ua1` -> pad C and `ua2` ->
pad J measured a working inverter, `ua3` -> pad D a working ring
oscillator.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from mosbius.decode import decode
from mosbius.model import SwitchConfig

PAD_LETTERS = "CDFGJK"
INDEX_URL = "https://index.tinytapeout.com/{shuttle}.json"
CACHE_DIR = Path("build")


class PadLookupError(Exception):
    """The pad mapping could not be established, explained in full."""


def _shuttle_index(shuttle: str) -> dict:
    cache = CACHE_DIR / f"shuttle_{shuttle}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    url = INDEX_URL.format(shuttle=shuttle)
    try:
        # index.tinytapeout.com answers 403 to urllib's default user-agent
        request = urllib.request.Request(url, headers={"User-Agent": "mosbius-configurator"})
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PadLookupError(
            f"can't fetch the shuttle index for {shuttle} ({exc}).\n\n"
            f"  It is needed because which PCB pad a design's ua[k] comes out on\n"
            f"  depends on where the project sits on the shuttle, so it cannot be\n"
            f"  assumed. Two ways forward:\n"
            f"    - save {url}\n"
            f"      as {cache} and re-run, or\n"
            f"    - read the pads off the project's own page, whose Analog pins\n"
            f"      table lists ua -> PCB pin directly:\n"
            f"      https://tinytapeout.com/chips/{shuttle}/<your project>"
        ) from exc
    CACHE_DIR.mkdir(exist_ok=True)
    cache.write_text(body)
    return json.loads(body)


def pad_map(shuttle: str, macro: str) -> dict[str, str]:
    """{'ibias': 'K', 'ua1': 'C', ...} for one design on one shuttle."""
    index = _shuttle_index(shuttle)
    projects = index.get("projects", index if isinstance(index, list) else [])
    match = next((p for p in projects if p.get("macro") == macro), None)
    if match is None:
        raise PadLookupError(
            f"{macro} is not in the {shuttle} shuttle index.\n\n"
            f"  Check the name against the chip in the socket: the demoboard\n"
            f"  reports its shuttle from the chip's own ROM."
        )
    indices = match.get("analog_pins")
    if not indices:
        raise PadLookupError(
            f"{macro} on {shuttle} declares no analog pins in the shuttle index.\n\n"
            f"  A design with no analog pins has nothing to probe -- if that is\n"
            f"  wrong, the index is the place it needs fixing."
        )
    if max(indices) >= len(PAD_LETTERS):
        raise PadLookupError(
            f"{macro} uses analog index {max(indices)}, but this board is only\n"
            f"  known to letter {len(PAD_LETTERS)} analog pads ({PAD_LETTERS}).\n"
            f"  See mosbius/pads.py's note on where that list comes from."
        )
    names = ["ibias"] + [f"ua{k}" for k in range(1, len(indices))]
    return {name: PAD_LETTERS[idx] for name, idx in zip(names, indices)}


def pads_in_use(config: SwitchConfig, shuttle: str, macro: str) -> dict[str, str]:
    """Only the pins this configuration actually connects something to.

    The bench state is the bitstream: which pads matter follows from what
    the configuration wires up, so a wiring table built from this lists the
    circuit in the socket rather than every pin the chip has.

    A `ua[k]` counts as in use when its net reaches a crosspoint -- every
    pin appears in the decode paired with its bus row whether or not
    anything is on it, so the crosspoint is what distinguishes a wired pin
    from an idle one. `ibias` counts when some device actually draws on the
    bias reference: a mirror or the OTA always does, while a differential
    pair does only if its shared source is left off the rail, since tying
    it to a rail shorts the tail bank out.
    """
    decoded = decode(config)
    wanted = {
        f"ua{net.name[3:-1]}"
        for net in decoded.nets
        if net.name.startswith("ua[")
        and any(node.startswith("xpt_") for node in net.nodes)
    }
    for device in decoded.devices:
        if device.name.startswith(("nsink", "psource", "ota")):
            wanted.add("ibias")
        elif "diffpair" in device.name:
            tied = any(v for k, v in device.settings.items() if k.startswith("shared_source"))
            if not tied and device.settings.get("tail"):
                wanted.add("ibias")

    pads = pad_map(shuttle, macro)
    return {name: pad for name, pad in pads.items() if name in wanted}
