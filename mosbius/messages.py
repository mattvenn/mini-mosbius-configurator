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


# --- route.py ------------------------------------------------------------

ROUTE_SETTING_NOT_VALID = (
    "DOESN'T FIT -- {device}'s {prop}={value} is not a setting this "
    "chip has\n\n"
    "  {prop}= is stored as a 2-bit cycler: n = {step} * (1 + b_lsb + "
    "2*b_msb)\n  (SPEC.md Sec 2.11). That gives exactly four settings, "
    "{options},\n  and nothing in between.\n\n"
    "  Nothing is rounded to the nearest one on your behalf: the chip "
    "would\n  then be built to a different {prop} than your schematic "
    "shows, which is\n  the kind of silent difference this tool exists "
    "to prevent.\n\n"
    "  To fix: set {prop}= to one of {options} on {device} in the "
    "schematic,\n  and press Netlist again."
)

ROUTE_NOT_ENOUGH_FETS = (
    "DOESN'T FIT -- not enough {label} with independent sources\n\n"
    "  Your circuit needs {count} {label} transistors:\n"
    "    {names}\n\n"
    "  The chip has only {indep_count} of those whose source you can\n"
    "  route wherever you like:\n"
    "    {indep_list}\n\n"
    "  There are {pair_count} more, but they are the two halves of a\n"
    "  differential pair and share one source between them:\n"
    "    {pair_list}\n"
    "  So they suit two transistors that want a common source, or a\n"
    "  single transistor if that shared source is tied to {pair_rail}.\n\n"
    "  Currently placed: {placed}.\n"
    "  Couldn't place: {couldnt_place}.\n\n"
    "  Ideas:\n"
    "    - If two of these could share a source, they'd fit the pair.\n"
    "    - A programmable current sink/source (mosbius_nsink/psource) can\n"
    "      often replace a source-degenerated transistor."
)

ROUTE_TOO_MANY_NTAIL = (
    "DOESN'T FIT -- only one NMOS differential-pair tail on this chip\n\n"
    "  {count} mosbius_ntail devices requested, but there's exactly "
    "one NMOS\n  tail bank (role ntail, ctrl_dpn_tail)."
)

ROUTE_TOO_MANY_PTAIL = (
    "DOESN'T FIT -- only one PMOS differential-pair tail on this chip\n\n"
    "  {count} mosbius_ptail devices requested, but there's exactly "
    "one PMOS\n  tail bank (role ptail, ctrl_dpp_tail)."
)

ROUTE_TOO_MANY_NSINK = (
    "DOESN'T FIT -- too many current sinks\n\n"
    "  {count} mosbius_nsink devices requested, but the chip has only "
    "{max}\n  (nsink_a, nsink_b)."
)

ROUTE_TOO_MANY_PSOURCE = (
    "DOESN'T FIT -- too many current sources\n\n"
    "  {count} mosbius_psource devices requested, but the chip has "
    "only {max}\n  (psource_a, psource_b)."
)

ROUTE_TOO_MANY_OTA = (
    "DOESN'T FIT -- only one OTA on this chip\n\n"
    "  {count} mosbius_ota devices requested, but there's exactly one "
    "(ota)."
)

# Repeated in every reach-related message below, because it is the fact
# that makes the failure make sense and the reader may be meeting it for
# the first time (route.py's own _WHY_LIMITED_REACH comment).
ROUTE_WHY_LIMITED_REACH = (
    "  Why some terminals reach fewer rows than others: the differential\n"
    "  pair's and the OTA's *input* crosspoints have a switch to three bus\n"
    "  rows only, not to all six (SPEC.md Sec 2.12). Every other terminal on\n"
    "  the chip reaches all six.\n"
)

ROUTE_PORT_NET_UNREACHABLE_ROW = (
    "  '{net}' is a package pin, and its bus row is a permanent bond "
    "wire\n  rather than something the router picks: {net} is always "
    "bus_{side}[{row}]\n  (SPEC.md Sec 2.10).\n\n"
    "{why_limited_reach}\n"
    "  To fix: move this signal to a pin bonded to a row this "
    "terminal can\n  reach ({options}), or arrange for the restricted "
    "device not to be the\n  one sitting on this net."
)

ROUTE_INTERNAL_NET_UNREACHABLE_ROW = (
    "  '{net}' was placed on bus row {row}, which this terminal has no "
    "switch\n  to.\n\n{why_limited_reach}"
)

ROUTE_CANNOT_REACH_ROW = (
    "DOESN'T FIT -- {touch_desc} cannot reach "
    "bus_{side}[{row}]\n\n"
    "  {role}.{terminal} reaches {rows_reach}, "
    "and nothing else.\n\n"
    "{why}"
)

# _check_shared_source_is_reachable's message is built from several
# independently-wrapped paragraphs via check.py's _wrap() helper -- each
# paragraph is its own constant, migrated separately, and the call site
# keeps the _wrap(...) call structure (see route.py).
ROUTE_SHARED_SOURCE_HEADLINE = "nothing else can connect to '{net}'"

ROUTE_SHARED_SOURCE_EXPLAIN = (
    "{halves} share a source on '{net}', which is what made "
    "them the two halves of a differential pair "
    "({pair_roles}): the chip wires those "
    "two sources together in silicon. That shared node has no switch "
    "of its own onto the bus (SPEC.md Sec 2.12), so nothing outside "
    "the pair can be joined to it -- not another device, and not a "
    "package pin."
)

ROUTE_SHARED_SOURCE_PROBLEM_PIN = (
    "'{net}' is a package pin, and this node cannot reach one."
)

ROUTE_SHARED_SOURCE_ALSO_CARRIES = " It also carries {others}."

ROUTE_SHARED_SOURCE_PROBLEM_OTHER = "'{net}' also carries {others}."

ROUTE_SHARED_SOURCE_WHAT_CAN_GO_THERE = (
    "What can go on that node: nothing at all, with the source named "
    "{rail} -- the pair then uses its free tie to that rail, which is "
    "what a pair of ordinary common-source FETs wants. Or a "
    "{tail_symbol}, whose one drawn pin declares the pair's tail "
    "current (tail=2, 4, 6 or 8 multiples of ibias); "
    "examples/diffamp/ has that end to end."
)

ROUTE_SHARED_SOURCE_HOW_TO_MEASURE = (
    "To measure the tail current, measure it where it comes from: "
    "ibias feeds every tail bank on the chip, and the demoboard "
    "drives that pin."
)

ROUTE_DEVICE_ROLE_LINE = "  {name:<12} -> {role:<12}{note}"

ROUTE_NET_ROW_PAD_NOTE = "   package pin {net} -- bond pad + analog mux"

ROUTE_NET_ROW_LINE = "  {net:<8} {where}{note}"

ROUTE_PAD_NOTE = (
    "  {which} {are} connected to the chip's pads, so {they} {add} extra capacitance."
)

ROUTE_ROW_CONFLICT = (
    "DOESN'T FIT -- bus_{side}[{row}] is needed by both "
    "'{net}' and '{owner}'\n\n"
    "  Only one net can occupy a bus row at a time. Try moving one "
    "of these\n  nets' devices to the other side of the chip, if the "
    "device allocation allows it."
)

ROUTE_NO_FREE_ROW = (
    "DOESN'T FIT -- no free bus_{side}[] row left for '{net}'\n\n"
    "  All 6 rows on side {side} are already claimed by other nets, "
    "ports\n  or rail taps. Try routing this net through the other "
    "side, or freeing\n  up a row by sharing it with a net that's "
    "already there."
)

ROUTE_NO_REACHABLE_FREE_ROW = (
    "DOESN'T FIT -- no bus_{side}[] row that every device on "
    "'{net}' can reach\n\n"
    "  '{net}' connects:\n{reach_lines}\n\n"
    "  Free on side {side} right now: bus {free_rows}. The "
    "terminals above can\n  share only bus {reachable_rows}, "
    "and none of that is free.\n\n"
    "{why_limited_reach}\n"
    "  Ideas:\n"
    "    - Free up one of bus {reachable_rows} on side {side}, by "
    "moving another\n      net elsewhere.\n"
    "    - Give this net a package pin (name it ua1..ua5) if you can\n"
    "      spare one: that pins it to the row the pin is bonded to,\n"
    "      which may be a row the restricted terminal can reach.\n"
    "    - Rearrange the circuit so the restricted device is not on\n"
    "      this net at all -- only differential-pair and OTA inputs\n"
    "      are limited."
)

ROUTE_RAIL_TAP_UNREACHABLE_NOTE = (
    "  The {rail} taps still free are {free_taps},\n"
    "  but these terminals can share only bus "
    "{reachable_rows}:\n{reach_lines}\n\n"
    "{why_limited_reach}\n"
)

ROUTE_NO_USABLE_RAIL_TAP = (
    "DOESN'T FIT -- no usable {rail} tap for '{net}'\n\n"
    "{unreachable_note}"
    "  {rail} can only be reached from specific bus rows "
    "(SPEC.md Sec 2.7),\n  and none of the ones this net could use is "
    "available. If the device\n  has a source terminal, tying it "
    "directly to {rail} costs no bus row\n  at all."
)

ROUTE_NO_JOINING_ROW = (
    "DOESN'T FIT -- '{net}' spans both bus sides and no row can "
    "join them\n\n"
    "  '{net}' connects:\n{reach_lines}\n\n"
    "  A net that touches both sides has to sit on the *same* row\n"
    "  number on side A and on side B, bridged by cfg_bus_short. Free\n"
    "  on both sides here: bus {both_free_rows}. The terminals "
    "above can share\n  only bus {reachable_rows}.\n\n"
    "{why_limited_reach}\n"
    "  And bus {rows_free_both} is the only row "
    "ever free on both sides at once:\n  the others are permanently "
    "bonded to a ua[] pin on one side or the\n  other (SPEC.md Sec "
    "2.10). So this is a rule rather than a near miss:\n  a "
    "differential-pair or OTA input can never sit on an internal net\n"
    "  that spans both bus sides, whichever package pins you use.\n\n"
    "  Ideas:\n"
    "    - Get every device on '{net}' onto one bus side. Which side a\n"
    "      device is on follows from the hardware slot it was given, so\n"
    "      in practice this means changing which devices share a source.\n"
    "    - Give the net a package pin (name it ua1..ua5). A port net is\n"
    "      pinned to that pin's own row, which a restricted input may\n"
    "      well reach, and the other side is still bridged with\n"
    "      cfg_bus_short."
)

ROUTE_NO_FREE_ROW_BOTH_SIDES = (
    "DOESN'T FIT -- '{net}' needs a free row on both sides, joined\n\n"
    "  This net connects devices on both side A and side B, which needs "
    "a\n  matching free row on each side plus a cfg_bus_short. No such "
    "pair is\n  available -- every free row on at least one side is "
    "already claimed."
)

ROUTE_VDPWR_UNREACHABLE = (
    "DOESN'T FIT -- VDPWR isn't reachable through the switch matrix\n\n"
    "  VDPWR (1.8V) only powers the switches' own level-shifters "
    "internally\n  -- no cfg_bus_pwr tap or source tie reaches it "
    "(SPEC.md Sec 2.7 only\n  lists VAPWR/VGND taps). Route this "
    "signal through VAPWR or VGND\n  instead, or reconsider whether "
    "this net needs an explicit connection."
)
