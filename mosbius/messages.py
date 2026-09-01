# SPDX-License-Identifier: Apache-2.0
"""Every hand-written user-facing message in mosbius/*.py, in one place.

TODO.md item 4: "all user facing text will ultimately be in a separate
file, for internationalisation and for easy re-writing of all messages."
See docs/superpowers/specs/2026-09-01-user-facing-messages-design.md.

Only the text lives here. Which message applies, which word to use, and
what values to interpolate all stay exactly where they were -- a call
site does `messages.KEY.format(...)`, nothing more. Grouped by the
module each message came from, in that module's own definition order.
"""

from __future__ import annotations


# --- simulate.py ------------------------------------------------------

SIMULATE_ROUTE_HINT = (
    "      python3 -m mosbius.cli route {netlist} --out {routed}\n"
    "      python3 -m mosbius.cli simulate {routed}"
)

SIMULATE_STALE_ROUTED = (
    "{routed_path} is out of date\n\n"
    "  These were changed after it was written:\n\n"
    "{what}\n\n"
    "  So this file still describes the circuit as it used to be routed.\n"
    "  Simulating it would build a routed netlist for that old circuit,\n"
    "  and a drawn-vs-routed testbench would then compare two different\n"
    "  designs -- which runs, and produces numbers, and means nothing.\n\n"
    "  To fix:\n\n"
    "{fix}"
)

SIMULATE_STALE_FIX_REGENERATE = "    sh tools/regenerate_routed.sh {sch}\n"

SIMULATE_STALE_FIX_ROUTE_AND_SIMULATE = (
    "    python3 -m mosbius.cli route {netlist} --out {routed_path}\n"
    "    python3 -m mosbius.cli simulate {routed_path}\n"
)

SIMULATE_UNREADABLE = (
    "{reason}\n"
    "  `mosbius simulate` reads a routed design: the JSON file that\n"
    "  `mosbius route --out <file>` writes. That file records which hardware\n"
    "  device and which bus row every part of your schematic became, which is\n"
    "  what a simulation of the real switch matrix needs to know.\n"
    "  If you haven't routed this design yet, route it first and simulate what\n"
    "  routing wrote:\n\n"
    "{route_hint}"
)

SIMULATE_XSCHEM_NETLIST_GIVEN = (
    "{path} is an xschem netlist, not a routed design\n"
    "  `mosbius simulate` starts from the JSON file that\n"
    "  `mosbius route --out <file>` writes, not from the netlist itself.\n"
    "  The netlist says what you drew; routing is the step that decides\n"
    "  which of the chip's hardware devices each drawn device becomes and\n"
    "  which bus row each net becomes, and the simulation is built out of\n"
    "  exactly those decisions -- it can't make them for you.\n"
    "  Route this netlist first, then simulate what routing wrote:\n\n"
    "{route_hint}"
)

SIMULATE_NOT_JSON = (
    "{path} is not a routed design: it isn't JSON at all\n"
    "  `mosbius simulate` reads the JSON file that\n"
    "  `mosbius route --out <file>` writes. Check you passed the path you\n"
    "  meant to -- a routed design is named <name>.mosbius.json and starts\n"
    "  with a '{{' character."
)

SIMULATE_NO_BITSTREAM_KEY = (
    "{path} is JSON, but not a routed design\n"
    "  A routed design is what `mosbius route --out <file>` writes, and it\n"
    "  always carries a \"bitstream\" entry (the 48 hex characters that\n"
    "  configure the chip) -- this file has no such entry, so there is no\n"
    "  configuration here to build a simulation from. Re-run `mosbius route`\n"
    "  with --out pointing at this path to write a real one."
)

SIMULATE_BAD_BITSTREAM = (
    "{path} has a \"bitstream\" entry that isn't a usable configuration\n"
    "{detail}\n"
    "  A routed design's bitstream is written by `mosbius route --out`, so a\n"
    "  broken one usually means the file was hand-edited. Re-run `mosbius\n"
    "  route` with --out pointing at this path to rewrite it."
)
