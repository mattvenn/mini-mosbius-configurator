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


# --- check.py --------------------------------------------------------------

CHECK_E1_SUPPLY_SHORT = (
    "DANGEROUS -- supply short\n\n"
    "  VAPWR is joined to VGND through {n} closed switch{plural}:\n\n"
    "{path}\n\n"
    "  This draws unlimited current from the 3.3V supply straight to ground.\n"
    "  On real silicon that can damage the chip, so the upload is blocked.\n\n"
    "  Why it happened: closing every switch on that path ties VAPWR and\n"
    "  VGND together somewhere in the matrix -- often a bus_short switch\n"
    "  joining a VAPWR-tapped row to a VGND-tapped one, or two rail taps\n"
    "  landing on the same bus segment via different switches.\n\n"
    "  To fix: open one of the switches on the path above -- moving the\n"
    "  net to another row is usually enough."
)

CHECK_E2_IBIAS_SHORT = (
    "DANGEROUS -- ibias shorted to {rail}\n\n"
    "  ibias (ua[0]) is joined to {rail} through {n} closed switch"
    "{plural}:\n\n"
    "{path}\n\n"
    "  ibias is a current *input* (SPEC.md Sec 3.4b) that biases every\n"
    "  mirror and tail on the chip. Tying it to a rail forces whatever\n"
    "  current source drives it directly into {rail}, and every device\n"
    "  that depends on ibias loses its bias point.\n\n"
    "  To fix: open one of the switches on the path above."
)

CHECK_E3_PIN_INTO_RAIL = (
    "DANGEROUS -- {pin} shorted to {rail}\n\n"
    "  {pin} is joined to {rail} through {n} closed switch"
    "{plural}:\n\n"
    "{path}\n\n"
    "  {pin} is a package pin the demoboard can drive as a stimulus.\n"
    "  If it ever is, this path sends that drive straight into\n"
    "  {rail} -- a hard short the demoboard's output stage may not\n"
    "  survive.\n\n"
    "  To fix: open one of the switches on the path above, or route\n"
    "  this net through a different bus segment."
)

CHECK_E4_PIN_CONTENTION = (
    "DANGEROUS -- {a} and {b} are tied together\n\n"
    "  They're joined through {n} closed switch"
    "{plural}:\n\n"
    "{path}\n\n"
    "  Both are package pins the demoboard can drive independently.\n"
    "  If it ever drives them to different voltages, this path\n"
    "  shorts them together.\n\n"
    "  To fix: open one of the switches on the path above, or route\n"
    "  these nets through different bus segments."
)

CHECK_W1_SAME_NET = "    ({name}.d and {name}.s are the same net)"

CHECK_W1_SHORTED_CHANNEL = (
    "WARNING -- {name}'s drain and source are tied together\n\n"
    "  They're joined through {n} closed switch"
    "{plural}:\n\n"
    "{path}\n\n"
    "  This shorts out {name}'s channel -- current flows straight\n"
    "  through instead of being modulated by the gate, so the\n"
    "  transistor does nothing useful.\n\n"
    "  To fix: route {name}'s drain and source to different nets."
)

# W2 is assembled from several independently-chosen pieces (one-vs-many
# headline/intro, all-gates-vs-nothing-reaches "why", an optional
# untied-tail hint) plugged into one body template -- see
# _check_w2_floating_crosspoint.
CHECK_W2_HEADLINE_ONE = "WARNING -- nothing biases {names}"
CHECK_W2_HEADLINE_MANY = "WARNING -- nothing biases the net joining {names}"

CHECK_W2_INTRO_ONE = "  It has a closed switch on it, but the net it sits on\n"
CHECK_W2_INTRO_MANY = (
    "  These terminals are wired together, but the net they form\n"
)

CHECK_W2_WHY_ALL_GATES = (
    "  Every terminal on it is a gate, so nothing can set its\n"
    "  voltage -- there is no transistor channel to a rail here,\n"
    "  and no switch to one either.\n\n"
)

CHECK_W2_WHY_NOTHING_REACHES = (
    "  Nothing reaches it: not a closed switch to a rail or a\n"
    "  ua[] pin, and not a transistor channel that gets to one\n"
    "  either (a drain only conducts to a rail if its own source\n"
    "  is tied to one).\n\n"
)

CHECK_W2_HINT_UNTIED_TAIL = (
    "\n\n  Most likely fix here: {bits} is off, so the shared\n"
    "  diff-pair tail on this net's transistor is floating too. The\n"
    "  tail has no matrix terminal of its own (SPEC.md Sec 2.12) --\n"
    "  that bit is the only way to tie it to a rail, and with it set\n"
    "  the half works as an ordinary common-source FET."
)

CHECK_W2_BODY = (
    "{headline}\n\n"
    "{intro}"
    "  has no DC path to VAPWR, VGND, or a ua[] pin.\n\n"
    "{why}"
    "  In SPICE it floats and settles at an arbitrary voltage; on\n"
    "  real silicon leakage pulls it somewhere uncontrolled, slowly.\n\n"
    "  To fix: connect it to something that drives it -- a drain\n"
    "  whose transistor has its source on a rail, a mirror output,\n"
    "  or a ua[] pin you can drive from the demoboard.{hint}"
)

CHECK_W3_PARTLY_WIRED = (
    "WARNING -- {name} is partly wired\n\n"
    "  {used} {has_have} a closed\n"
    "  switch, but {unused} {is_are}\n"
    "  left with no connection at all.\n\n"
    "  A transistor with a floating terminal isn't doing the job it\n"
    "  looks like it's doing -- an unconnected gate floats to an\n"
    "  arbitrary voltage, an unconnected drain/source leaves the\n"
    "  device conducting nowhere.\n\n"
    "  To fix: either wire up {unused}, or remove {name}\n"
    "  from the design if it isn't meant to be used."
)

# I1's sentences are picked and joined per finding (a segment can be
# empty, bond-only, or single-switch, in any combination) -- see
# _render_i1.
CHECK_I1_HEADLINE = "{subjects} {do_does} nothing"

CHECK_I1_SENTENCE_EMPTY = (
    "{names} {verb} nothing connected to {it_them} at all."
)

CHECK_I1_SENTENCE_BONDED_ONE = (
    "{seg} is connected only to its package pin ({pins}) -- "
    "that bond wire is part of the chip rather than something "
    "the schematic added, so it joins the segment to nothing else."
)

CHECK_I1_SENTENCE_BONDED_MANY = (
    "{names} are connected only to their package pins "
    "({pins}) -- those bond wires are part of the chip rather "
    "than something the schematic added, so each joins its "
    "segment to nothing else."
)

CHECK_I1_SENTENCE_WIRED = "{names} {verb} just one connection{each}."

CHECK_I1_PARAGRAPH2 = (
    "A bus segment needs at least two connections (to actually join two "
    "things) to have any effect, so {consequence} wiring anything "
    "together."
)

# D1's "subject" line (which/how many devices, one vs several) is built
# separately from the DANGEROUS/WARNING body that embeds it -- see
# _check_d1_source_on_wrong_rail.
CHECK_D1_SUBJECT_ONE = "  {names} is a mosbius_{kind} with its source on {wrong}"

CHECK_D1_SUBJECT_MANY = (
    "  {n} of your mosbius_{kind} devices have their source on "
    "{wrong}:\n    {names}"
)

CHECK_D1_RAILS_SHORTED = (
    "DANGEROUS -- VAPWR and VGND are joined somewhere in your schematic\n\n"
    "{subject}\n\n"
    "  Meanwhile {home} does not appear on a single device terminal\n"
    "  anywhere in this netlist.\n\n"
    "  Why that combination means the rails are shorted: a "
    "mosbius_{kind}'s\n"
    "  body is hard-wired to {home} on silicon, and its source belongs on\n"
    "  that same rail. The body still reads {home} here because it is not a\n"
    "  wire you drew -- it comes from the symbol's own template\n"
    "  (mosbius_{kind}.sym, template=\"... b={home}\" with extra=\"b\"), so it\n"
    "  is the one connection xschem cannot merge with anything else.\n"
    "  Everything you did draw as {home} came back as {wrong} instead.\n\n"
    "  That is what happens when the two rails are wired together: xschem\n"
    "  merges them into a single net, keeps one of the two names, and the\n"
    "  short itself vanishes from the netlist before this tool ever sees\n"
    "  it. Nothing here can find it by looking at connectivity, because\n"
    "  by then there is only one rail left to look at.\n\n"
    "  On real silicon this ties the 3.3V supply straight to ground and\n"
    "  draws unlimited current, so nothing is routed or uploaded from\n"
    "  here.\n\n"
    "  To fix: find the wire joining {wrong} and {home} in your schematic,\n"
    "  delete it, and press Netlist again. Both rail names should then be\n"
    "  back on the terminals you drew them on."
)

# The paragraph that connects D1's WARN branch to the "DOESN'T FIT -- not
# enough NMOS/PMOS with independent sources" the user actually sees --
# _why_it_costs_the_pair's return value.
CHECK_D1_WHY_COSTS_PAIR = (
    "  It also costs you the two differential-pair halves. Their shared\n"
    "  tail has no terminal on the switch matrix (SPEC.md Sec 2.12), so the\n"
    "  only way to give it a voltage is {tail_bit}, and that bit\n"
    "  ties it to {other_rail}. A half therefore cannot take a device whose\n"
    "  source is on {wrong_rail}, which leaves only {independent_slots}. "
    "That is\n"
    "  why this first shows up as \"DOESN'T FIT -- not enough "
    "{router_label} with\n  independent sources\".\n\n"
)

CHECK_D1_SOURCE_ON_WRONG_RAIL = (
    "WARNING -- source on {wrong} where {home} is expected\n\n"
    "{subject}.\n"
    "  A mosbius_{kind}'s body is hard-wired to {home} on silicon "
    "(that is what\n"
    "  mosbius_{kind}.sym's template=\"... b={home}\" records), and its source\n"
    "  belongs on the same rail.\n\n"
    "{why_costs_pair}"
    "  The usual cause is a symbol flipped vertically: mosbius_nmos has its\n"
    "  source at the bottom and its drain at the top, and mosbius_pmos is\n"
    "  the other way up.\n\n"
    "  This is a warning rather than a hard stop because the router can\n"
    "  still reach {wrong} from a source terminal, through a bus row and a\n"
    "  cfg_bus_pwr tap -- so the circuit may well route. It just probably\n"
    "  is not the circuit you meant to draw.\n\n"
    "  To fix: wire the source of {names} to {home}."
)

# D2's "subject" line, same shape as D1's.
CHECK_D2_SUBJECT_ONE = (
    "  {names} is a mosbius_{kind} with its drain on {rail} and its\n"
    "  source on {nets}, an ordinary net inside your circuit."
)

CHECK_D2_SUBJECT_MANY = (
    "  {n} of your mosbius_{kind} devices have their drain on {rail} "
    "and their\n  source on an ordinary net inside your circuit "
    "({nets}):\n    {names}"
)

CHECK_D2_DRAIN_SOURCE_SWAPPED = (
    "WARNING -- drain and source look swapped on {names}\n\n"
    "{subject}\n\n"
    "  That is back to front for a common-source transistor. A "
    "mosbius_{kind}'s\n  source belongs on {rail} -- the rail its body is "
    "hard-wired to on\n  silicon -- and its drain is the end that drives "
    "the rest of the\n  circuit. As drawn, these two are the other way "
    "round.\n\n"
    "  Why it is worth saying: nothing downstream can tell a reversed\n"
    "  transistor from a deliberate one, so the request is taken at face\n"
    "  value and costs you something either way.\n\n"
    "  It costs a bus row even when it routes. Only the *source* terminal\n"
    "  has a free tie to its rail:\n"
    "    {source_tie}\n"
    "  With the source on an internal net that tie is unusable, so "
    "reaching\n  {rail} from the drain instead has to spend a bus row and "
    "a cfg_bus_pwr\n  tap.\n\n"
    "  And it can cost you the circuit. The chip has only two "
    "{kind_upper} whose\n  source can be routed anywhere at all, so once "
    "there are more than two\n  such requests the allocator gives up:\n"
    "    \"DOESN'T FIT -- not enough {kind_upper} with independent "
    "sources\"\n"
    "  which points at the size of your circuit rather than at the "
    "wiring.\n\n"
    "  The usual cause is a symbol flipped vertically: mosbius_{kind} has "
    "its\n  {top} at the top and its {bottom} at the bottom, the opposite "
    "way up\n  from mosbius_{other_kind}. A "
    "schematic drawn before 2026-08-21 used the\n  older pin geometry, so "
    "a symbol copied from one comes out reversed.\n\n"
    "  This is a hint, not a hard stop: a source on an internal net is\n"
    "  exactly right in a cascode or a source follower. It is flagged only\n"
    "  because the drain is on {rail} as well, and that combination has no\n"
    "  sensible reading.\n\n"
    "  To fix: swap the two connections on {names}, so the source goes to\n"
    "  {rail} and the drain carries the signal."
)

# D3's "found" clause: what, if anything, shares the tail's drain net.
CHECK_D3_FOUND_NONE = "nothing else in the design has its source on '{node}'"

CHECK_D3_FOUND_SOME = (
    "{n} {fet_symbol} devices have their source there: {names}"
)

CHECK_D3_TAIL_WRONG_ARITY = (
    "ERROR -- {tail_name}'s drain doesn't declare a pair\n\n"
    "  {tail_name} is a {symbol}, and its drain is wired to "
    "'{node}'.\n  Drawing a {symbol} declares that net's two "
    "{fet_symbol} devices as a\n  differential pair -- but {found}.\n\n"
    "  A {symbol} needs exactly two {fet_symbol} devices sharing its\n"
    "  drain net as their source: those become the pair, and "
    "{tail_name}'s\n  tail= reaches their shared tail current "
    "({tail_bit}).\n\n"
    "  To fix: wire {tail_name}'s drain to the shared source of "
    "exactly two\n  {fet_symbol} devices, or remove {tail_name} if "
    "you didn't mean to\n  draw a pair here."
)

CHECK_D4_TAIL_ON_RAIL = (
    "ERROR -- {tail_name}'s drain is wired straight to {rail}\n\n"
    "  {tail_name} is a {symbol}, and its drain -- the node its "
    "tail bank\n  feeds -- is wired directly to {rail} instead of "
    "to a genuine internal\n  net.\n\n"
    "  That node is never the rail itself: it is the diff pair's "
    "shared\n  source, which has no matrix terminal of its own "
    "(SPEC.md Sec 2.12).\n  {tail_bit} (what {tail_name}'s "
    "tail= sets) and the rail-tie bit\n  are two different ways to "
    "bias that one node, and they are\n  alternatives, never both "
    "at once.\n\n"
    "  To fix: wire {tail_name}'s drain to the pair halves' actual\n"
    "  shared source net, not to {rail}. If you meant the halves "
    "tied\n  straight to {rail} instead (CLAUDE.md Traps #3), "
    "remove {tail_name}\n  and wire their sources to {rail} "
    "directly."
)

# R1's headline/intro (one device vs several) and the four body
# paragraphs, assembled by _render_r1 and passed through _wrap.
CHECK_R1_HEADLINE_ONE = (
    "{name}'s {prop}={requested} was ignored: {role} has a fixed width"
)
CHECK_R1_HEADLINE_MANY = (
    "{names} had their {prop}={requested} ignored: "
    "{role_list} have a fixed width"
)

CHECK_R1_INTRO_ONE = (
    "The router put {name} on {role}, one of the two halves of the"
)
CHECK_R1_INTRO_MANY = (
    "The router put {names} on {role_list}, the two halves of the"
)

CHECK_R1_PARAGRAPH_DROPPED = (
    "{intro} {kind} differential pair. Those halves have no width bits "
    "on the chip -- their geometry is built in silicon -- so there is "
    "nothing in the bitstream that could carry {prop}={requested}, and "
    "it was dropped."
)

CHECK_R1_PARAGRAPH_INSTEAD = (
    "What you get instead is {prop}={effective}. A half is {geometry}, "
    "which is exactly the geometry of a programmable FET at its maximum "
    "{prop}={effective} ({prog}'s 1x always-on slice plus its switchable "
    "1x and 2x slices)."
)

CHECK_R1_PARAGRAPH_WHY = (
    "Why this matters: it is built at {prop}={effective} where your "
    "schematic says {prop}={requested}. In a circuit that looks "
    "symmetric -- the three stages of a ring oscillator, say -- the "
    "stages that land on the programmable FETs come out at the width "
    "you asked for and this one does not, and the mismatch exists only "
    "on silicon, not in the drawing."
)

CHECK_R1_PARAGRAPH_FIX = (
    "To fix: set the other devices of the same kind to {prop}="
    "{effective} as well, so every stage matches deliberately -- "
    "examples/ringosc/ring.sch does exactly that. They match in W/L, "
    "though not in parasitics: the programmable FET's 1x and 2x slices "
    "sit behind drain switches and the diff-pair half does not."
)

# R2's headline/intro/body, same shape as R1's.
CHECK_R2_HEADLINE_ONE = (
    "{name}'s tail={requested} was ignored: {role} has no tail current"
)
CHECK_R2_HEADLINE_MANY = (
    "{names} had their tail={requested} ignored: "
    "{role_list} have no tail current"
)

CHECK_R2_INTRO_ONE = (
    "The router put {name} on {role}, which has no tail-current "
    "bit of its own"
)
CHECK_R2_INTRO_MANY = (
    "The router put {names} on {role_list}, which have no "
    "tail-current bit of their own"
)

CHECK_R2_PARAGRAPH_DROPPED = (
    "{intro}, so there is nothing here for tail= to set and it was "
    "dropped."
)

CHECK_R2_PARAGRAPH_ALTERNATIVES = (
    "Only mosbius_ota, mosbius_ntail and mosbius_ptail carry a tail you "
    "can write in the schematic. If you meant to change how hard this "
    "device drives, that is w= (1, 2, 3 or 4) on a "
    "mosbius_nmos/mosbius_pmos, or ratio= on a "
    "mosbius_nsink/mosbius_psource. If you meant a differential pair's "
    "tail current, that belongs on a mosbius_ntail/mosbius_ptail wired "
    "to the pair's shared source, not on either half."
)

# R3's headline and three body paragraphs.
CHECK_R3_HEADLINE = (
    "the differential pair on {nets} will draw "
    "{amps:.0f} uA you did not ask for"
)

CHECK_R3_PARAGRAPH_SINKS = (
    "{devices} became differential-pair halves, and a pair's tail "
    "current bank has no off state. Its smallest setting is one "
    "always-on transistor (diff_n.sch M8, W=20 against the bias "
    "reference's W=10), so the chip sinks 2 x ibias -- {amps:.0f} uA at "
    "the {ibias_uA:.0f} uA this configuration uses -- out of "
    "{nets}, whatever the schematic says. `mosbius decode` shows it as "
    "tail=2."
)

CHECK_R3_PARAGRAPH_DISAGREE = (
    "Your as-drawn simulation has no such current in it, so the drawn "
    "and routed halves of a testbench will disagree, and disagree more "
    "the higher you set ibias."
)

CHECK_R3_PARAGRAPH_FIX = (
    "Two ways to make them agree. Draw a {tail_symbol} on that "
    "node and say which tail current you want (2, 4, 6 or 8 multiples "
    "of ibias -- see examples/diffamp/), which puts the same current in "
    "both. Or name that net {rail}, which closes the pair's free "
    "source tie and shorts the tail bank out, leaving two ordinary "
    "common-source FETs."
)

# B1's headline and body paragraphs, one set per branch (no generator
# drawn at all, or more than one drawn).
CHECK_B1_NO_GENERATOR_HEADLINE = "this design has no bias generator on the sheet"

CHECK_B1_NO_GENERATOR_DREW = (
    "You drew {drew}, and every one of those copies the chip's bias "
    "reference: they are mirror legs and tail banks, and what sets "
    "their current is the voltage that reference makes out of the "
    "ibias pin."
)

CHECK_B1_NO_GENERATOR_GAP = (
    "Nothing on this sheet makes it, so in simulation their gates sit "
    "wherever the DC solver leaves them and the currents mean nothing. "
    "On silicon the reference is always there, so this is a gap in the "
    "drawing rather than something the chip could do."
)

CHECK_B1_NO_GENERATOR_FIX = (
    "To fix: place one mosbius_bias from xschem/mosbius_lib and wire it "
    "to the ibias pin. examples/currentsource/ has it done. Copying a "
    "fresh mini_mosbius.sch also gets you one."
)

CHECK_B1_TOO_MANY_HEADLINE = (
    "this design has {count} bias generators, and needs exactly one"
)

CHECK_B1_TOO_MANY_SHARE = (
    "They sit in parallel on the ibias pin, so they share the current "
    "the demoboard sends: two references make half the reference "
    "current each, and every mirror, tail bank and OTA tail on the "
    "sheet comes out at half of what its ratio= or tail= asks for."
)

CHECK_B1_TOO_MANY_FIX = (
    "The chip has one, feeding everything. To fix: delete all but one "
    "mosbius_bias (or, on an older sheet, all but one drawn "
    "reference diode -- the NMOS with its gate and drain both on "
    "ibias)."
)
