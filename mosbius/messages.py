# SPDX-License-Identifier: Apache-2.0
"""Every hand-written user-facing message in mosbius/*.py, in one place.

TODO.md item 4: "all user facing text will ultimately be in a separate
file, for internationalisation and for easy re-writing of all messages."
See docs/superpowers/specs/2026-09-01-user-facing-messages-design.md.

Only the text lives here. Which message applies, which word to use, and
what values to interpolate all stay exactly where they were - a call
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
    "  The netlist describes what you drew; routing is the step that decides\n"
    "  how to map your design to the available resources.\n\n"
    "{route_hint}"
)

SIMULATE_NOT_JSON = (
    "{path} is not a routed design: it isn't JSON at all\n"
    "  `mosbius simulate` reads the JSON file that\n"
    "  `mosbius route --out <file>` writes. Check you passed the path you\n"
    "  meant to - a routed design is named <name>.mosbius.json and starts\n"
    "  with a '{{' character."
)

SIMULATE_NO_BITSTREAM_KEY = (
    "{path} is JSON, but not a routed design\n"
    "  A routed design is what `mosbius route --out <file>` writes, and it\n"
    "  always carries a \"bitstream\" entry (the 48 hex characters that\n"
    "  configure the chip) - this file has no such entry, so there is no\n"
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
    "DOESN'T FIT - {device}'s {prop}={value} is not a setting this "
    "chip has\n\n"
    "  {prop}= is stored as a 2-bit cycler: n = {step} * (1 + b_lsb + "
    "2*b_msb). That gives exactly four settings, "
    "{options}.\n\n"
    "  To fix: set {prop}= to one of {options} on {device} in the "
    "schematic,\n  and press Netlist again."
)

ROUTE_NOT_ENOUGH_FETS = (
    "DOESN'T FIT - not enough {label} with independent sources\n\n"
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
    "DOESN'T FIT - only one NMOS differential-pair tail on this chip\n\n"
    "  {count} mosbius_ntail devices requested, but there's exactly "
    "one NMOS\n  tail bank (role ntail, ctrl_dpn_tail)."
)

ROUTE_TOO_MANY_PTAIL = (
    "DOESN'T FIT - only one PMOS differential-pair tail on this chip\n\n"
    "  {count} mosbius_ptail devices requested, but there's exactly "
    "one PMOS\n  tail bank (role ptail, ctrl_dpp_tail)."
)

ROUTE_TOO_MANY_NSINK = (
    "DOESN'T FIT - too many current sinks\n\n"
    "  {count} mosbius_nsink devices requested, but the chip has only "
    "{max}\n  (nsink_a, nsink_b)."
)

ROUTE_TOO_MANY_PSOURCE = (
    "DOESN'T FIT - too many current sources\n\n"
    "  {count} mosbius_psource devices requested, but the chip has "
    "only {max}\n  (psource_a, psource_b)."
)

ROUTE_TOO_MANY_OTA = (
    "DOESN'T FIT - only one OTA on this chip\n\n"
    "  {count} mosbius_ota devices requested, but there's exactly one "
    "(ota)."
)

# Repeated in every reach-related message below, because it is the fact
# that makes the failure make sense and the reader may be meeting it for
# the first time (route.py's own _WHY_LIMITED_REACH comment).
ROUTE_WHY_LIMITED_REACH = (
    "  Why some terminals reach fewer rows than others: the differential\n"
    "  pair's and the OTA's *input* crosspoints have a switch to three bus\n"
    "  rows only, not to all six. Every other terminal on\n"
    "  the chip reaches all six.\n"
)

ROUTE_PORT_NET_UNREACHABLE_ROW = (
    "  '{net}' is a package pin, and its bus row is a permanent bond "
    "wire\n  rather than something the router picks: {net} is always "
    "bus_{side}[{row}]\n\n"
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
    "DOESN'T FIT - {touch_desc} cannot reach "
    "bus_{side}[{row}]\n\n"
    "  {role}.{terminal} reaches {rows_reach}, "
    "and nothing else.\n\n"
    "{why}"
)

# _check_shared_source_is_reachable's message is built from several
# independently-wrapped paragraphs via check.py's _wrap() helper -- each
# paragraph is its own constant, migrated separately, and the call site
# keeps the _wrap(...) call structure (see route.py). The severity tag is
# kept separate here too, matching every other DOESN'T FIT constant's own
# wording above -- this is the one call site in route.py that still built
# it as a bare literal instead of routing it through messages.py.
ROUTE_SEVERITY_DOESNT_FIT = "DOESN'T FIT - "

ROUTE_SHARED_SOURCE_HEADLINE = "nothing else can connect to '{net}'"

ROUTE_SHARED_SOURCE_EXPLAIN = (
    "{halves} share a source on '{net}', which is what made "
    "them the two halves of a differential pair "
    "({pair_roles}): the chip wires those "
    "two sources together in silicon. That shared node has no switch "
    "of its own onto the bus, so nothing outside "
    "the pair can be joined to it."
)

ROUTE_SHARED_SOURCE_PROBLEM_PIN = (
    "'{net}' is a package pin, and this node cannot reach one."
)

ROUTE_SHARED_SOURCE_ALSO_CARRIES = " It also carries {others}."

ROUTE_SHARED_SOURCE_PROBLEM_OTHER = "'{net}' also carries {others}."

ROUTE_SHARED_SOURCE_WHAT_CAN_GO_THERE = (
    "What can go on that node: nothing at all, with the source named "
    "{rail} - the pair then uses its free tie to that rail, which is "
    "what a pair of ordinary common-source FETs wants. Or a "
    "{tail_symbol}, whose one drawn pin declares the pair's tail "
    "current (tail=2, 4, 6 or 8 multiples of ibias); "
    "see examples/diffamp/."
)

ROUTE_SHARED_SOURCE_HOW_TO_MEASURE = (
    "To measure the tail current, measure it where it comes from: "
    "ibias feeds every tail bank on the chip, and the demoboard "
    "drives that pin."
)

ROUTE_DEVICE_ROLE_LINE = "  {name:<12} -> {role:<12}{note}"

ROUTE_NET_ROW_PAD_NOTE = "   package pin {net} - bond pad + analog mux"

ROUTE_NET_ROW_LINE = "  {net:<8} {where}{note}"

ROUTE_PAD_NOTE = (
    "  {which} {are} connected to the chip's pads, so {they} {add} extra capacitance."
)

ROUTE_ROW_CONFLICT = (
    "DOESN'T FIT - bus_{side}[{row}] is needed by both "
    "'{net}' and '{owner}'\n\n"
    "  Which row a net lands on is the router's decision, not something "
    "you\n  choose directly. This usually happens when reaching a rail "
    "(VAPWR/VGND)\n  tap from one bus side needs a bridge to the same "
    "row number on the\n  other side, and that row is already claimed "
    "by a different net.\n\n"
    "  If the device has a source terminal, tying it directly to its "
    "rail\n  instead of routing through an internal net costs no bus "
    "row at all\n  and avoids the bridge entirely."
)

ROUTE_NO_FREE_ROW = (
    "DOESN'T FIT - no free bus_{side}[] row left for '{net}'\n\n"
    "  All 6 rows on side {side} are already claimed by other nets, "
    "ports\n  or rail taps."
)

ROUTE_NO_REACHABLE_FREE_ROW = (
    "DOESN'T FIT - no bus_{side}[] row that every device on "
    "'{net}' can reach\n\n"
    "  '{net}' connects:\n{reach_lines}\n\n"
    "  Free on side {side} right now: bus {free_rows}. The "
    "terminals above can\n  share only bus {reachable_rows}, "
    "and none of that is free.\n\n"
    "{why_limited_reach}\n"
    "  Ideas:\n"
    "    - Use fewer devices/nets on this side of the chip. Which side "
    "a\n      device lands on follows from the hardware slot it was "
    "given, not\n      something you choose directly, so this means "
    "simplifying the\n      circuit rather than relocating a specific "
    "net.\n"
    "    - Give this net a package pin (name it ua1..ua5) if you can\n"
    "      spare one: that pins it to the row the pin is bonded to,\n"
    "      which may be a row the restricted terminal can reach.\n"
    "    - Rearrange the circuit so the restricted device is not on\n"
    "      this net at all - only differential-pair and OTA inputs\n"
    "      are limited."
)

ROUTE_RAIL_TAP_UNREACHABLE_NOTE = (
    "  The {rail} taps still free are {free_taps},\n"
    "  but these terminals can share only bus "
    "{reachable_rows}:\n{reach_lines}\n\n"
    "{why_limited_reach}\n"
)

ROUTE_NO_USABLE_RAIL_TAP = (
    "DOESN'T FIT - no usable {rail} tap for '{net}'\n\n"
    "{unreachable_note}"
    "  {rail} can only be reached from specific bus rows "
    "and none of the ones this net could use is "
    "available. If the device\n  has a source terminal, tying it "
    "directly to {rail} costs no bus row\n  at all."
)

ROUTE_NO_JOINING_ROW = (
    "DOESN'T FIT - '{net}' spans both bus sides and no row can "
    "join them\n\n"
    "  '{net}' connects:\n{reach_lines}\n\n"
    "  A net that touches both sides has to sit on the *same* row\n"
    "  number on side A and on side B. Free\n"
    "  on both sides here: bus {both_free_rows}. The terminals "
    "above can share\n  only bus {reachable_rows}.\n\n"
    "{why_limited_reach}\n"
    "  And bus {rows_free_both} is the only row "
    "ever free on both sides at once:\n  the others are permanently "
    "bonded to a ua[] pin on one side or the\n  other."
    " So this is a rule rather than a near miss:\n  a "
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
    "DOESN'T FIT - '{net}' needs a free row on both sides, joined\n\n"
    "  This net connects devices on both side A and side B, which needs "
    "a\n  matching free row on each side. No such "
    "pair is\n  available - every free row on at least one side is "
    "already claimed."
)

ROUTE_VDPWR_UNREACHABLE = (
    "DOESN'T FIT - VDPWR isn't reachable through the switch matrix\n\n"
    "  VDPWR (1.8V) only powers the switches' own level-shifters "
    "internally"
)


# --- check.py --------------------------------------------------------------

# Severity tags for the four findings whose message is built via _wrap()
# (prefix + headline kept separate, unlike every finding above/below whose
# tag is baked into its own opening line) -- keeping these in messages.py
# too closes the one place this project's most-repeated words ("WARNING",
# "IMPOSSIBLE", ...) were still living only in check.py's own source.
CHECK_SEVERITY_INFO = "INFO - "

CHECK_SEVERITY_WARNING = "WARNING - "

CHECK_SEVERITY_IMPOSSIBLE = "IMPOSSIBLE - "

CHECK_E1_SUPPLY_SHORT = (
    "DANGEROUS - supply short\n\n"
    "  VAPWR is joined to VGND through {n} closed switch{plural}:\n\n"
    "{path}\n\n"
    "  This draws unlimited current from the 3.3V supply straight to ground.\n"
    "  On silicon that can damage the chip, so the upload is blocked."
)

CHECK_E2_IBIAS_SHORT = (
    "DANGEROUS - ibias shorted to {rail}\n\n"
    "  ibias (ua[0]) is joined to {rail} through {n} closed switch"
    "{plural}:\n\n"
    "{path}\n\n"
    "  ibias is a current *input* that biases every\n"
    "  mirror and tail on the chip. Tying it to a rail forces whatever\n"
    "  current source drives it directly into {rail}, and every device\n"
    "  that depends on ibias loses its bias point."
)

CHECK_E3_PIN_INTO_RAIL = (
    "DANGEROUS - {pin} shorted to {rail}\n\n"
    "  {pin} is joined to {rail} through {n} closed switch"
    "{plural}:\n\n"
    "{path}\n\n"
    "  {pin} is a package pin the demoboard can drive as a stimulus.\n"
    "  If it ever is, this path sends that drive straight into\n"
    "  {rail} - a hard short the demoboard's output stage may not\n"
    "  survive."
)

CHECK_E4_PIN_CONTENTION = (
    "DANGEROUS - {a} and {b} are tied together\n\n"
    "  They're joined through {n} closed switch"
    "{plural}:\n\n"
    "{path}\n\n"
    "  Both are package pins the demoboard can drive independently.\n"
    "  If it ever drives them to different voltages, this path\n"
    "  shorts them together"
)

CHECK_W1_SAME_NET = "    ({name}.d and {name}.s are the same net)"

CHECK_W1_SHORTED_CHANNEL = (
    "WARNING - {name}'s drain and source are tied together\n\n"
    "  They're joined through {n} closed switch"
    "{plural}:\n\n"
    "{path}\n\n"
    "  This shorts out {name}'s channel - current flows straight\n"
    "  through instead of being modulated by the gate, so the\n"
    "  transistor does nothing useful.\n\n"
    "  To fix: route {name}'s drain and source to different nets."
)

# W2 is assembled from several independently-chosen pieces (one-vs-many
# headline/intro, all-gates-vs-nothing-reaches "why", an optional
# untied-tail hint) plugged into one body template -- see
# _check_w2_floating_crosspoint.
CHECK_W2_HEADLINE_ONE = "WARNING - nothing biases {names}"
CHECK_W2_HEADLINE_MANY = "WARNING - nothing biases the net joining {names}"

CHECK_W2_INTRO_ONE = "  It has a closed switch on it, but the net it sits on\n"
CHECK_W2_INTRO_MANY = (
    "  These terminals are wired together, but the net they form\n"
)

CHECK_W2_WHY_ALL_GATES = (
    "  Every terminal on it is a gate, so nothing can set its\n"
    "  voltage - there is no transistor channel to a rail here,\n"
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
    "  tail has no matrix terminal of its own."
)

CHECK_W2_BODY = (
    "{headline}\n\n"
    "{intro}"
    "  has no DC path to VAPWR, VGND, or a ua[] pin.\n\n"
    "{why}"
    "  In SPICE it floats and settles at an arbitrary voltage; on\n"
    "  silicon leakage pulls it somewhere uncontrolled, slowly.\n\n"
    "  To fix: connect it to something that drives it - a drain\n"
    "  whose transistor has its source on a rail, a mirror output,\n"
    "  or a ua[] pin you can drive from the demoboard.{hint}"
)

CHECK_W3_PARTLY_WIRED = (
    "WARNING - {name} is partly wired\n\n"
    "  {used} {has_have} a closed\n"
    "  switch, but {unused} {is_are}\n"
    "  left with no connection at all.\n\n"
    "  A transistor with a floating terminal isn't doing the job it\n"
    "  looks like it's doing - an unconnected gate floats to an\n"
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
    "{seg} is connected only to its package pin ({pins}) - "
    "that bond wire is part of the chip rather than something "
    "the schematic added, so it joins the segment to nothing else."
)

CHECK_I1_SENTENCE_BONDED_MANY = (
    "{names} are connected only to their package pins "
    "({pins}) - those bond wires are part of the chip rather "
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
    "DANGEROUS - VAPWR and VGND are joined somewhere in your schematic\n\n"
    "{subject}\n\n"
    "  Meanwhile {home} does not appear on a single device terminal\n"
    "  anywhere in this netlist.\n\n"
    "  Why that combination means the rails are shorted: a "
    "mosbius_{kind}'s\n"
    "  body is hard-wired to {home} on silicon, and its source belongs on\n"
    "  that same rail. The body still reads {home} here because it is not a\n"
    "  wire you drew - it comes from the symbol's own template\n"
    "  (mosbius_{kind}.sym, template=\"... b={home}\" with extra=\"b\"), so it\n"
    "  is the one connection xschem cannot merge with anything else.\n"
    "  Everything you did draw as {home} came back as {wrong} instead.\n\n"
    "  That is what happens when the two rails are wired together: xschem\n"
    "  merges them into a single net, keeps one of the two names, and the\n"
    "  short itself vanishes from the netlist before this tool ever sees\n"
    "  it. Nothing here can find it by looking at connectivity, because\n"
    "  by then there is only one rail left to look at.\n\n"
    "  On silicon this ties the 3.3V supply straight to ground and\n"
    "  draws unlimited current, so nothing is routed or uploaded from\n"
    "  here.\n\n"
    "  To fix: find the wire joining {wrong} and {home} in your schematic,\n"
    "  delete it, and press Netlist again. Both rail names should then be\n"
    "  back on the terminals you drew them on."
)

# The paragraph that connects D1's WARN branch to the "DOESN'T FIT -- not
# enough NMOS/PMOS with independent sources" the user actually sees --
# _why_it_costs_the_pair's return value.
# Must describe the same situation as ROUTE_NOT_ENOUGH_FETS's headline --
# see check.py's own comment near _why_it_costs_the_pair.
CHECK_D1_WHY_COSTS_PAIR = (
    "  It also costs you the two differential-pair halves. Their shared\n"
    "  tail has no terminal on the switch matrix, so the\n"
    "  only way to give it a voltage is {tail_bit}, and that bit\n"
    "  ties it to {other_rail}. A half therefore cannot take a device whose\n"
    "  source is on {wrong_rail}, which leaves only {independent_slots}. "
    "That is\n"
    "  why this first shows up as \"DOESN'T FIT - not enough "
    "{router_label} with\n  independent sources\".\n\n"
)

CHECK_D1_SOURCE_ON_WRONG_RAIL = (
    "WARNING - source on {wrong} where {home} is expected\n\n"
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
    "  cfg_bus_pwr tap - so the circuit may well route. It just probably\n"
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

# Must describe the same situation as ROUTE_NOT_ENOUGH_FETS's headline --
# see check.py's own comment near _why_it_costs_the_pair.
CHECK_D2_DRAIN_SOURCE_SWAPPED = (
    "WARNING - drain and source look swapped on {names}\n\n"
    "{subject}\n\n"
    "  That is back to front for a common-source transistor. A "
    "mosbius_{kind}'s\n  source belongs on {rail} - the rail its body is "
    "hard-wired to on\n  silicon - and its drain is the end that drives "
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
    "    \"DOESN'T FIT - not enough {kind_upper} with independent "
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
    "ERROR - {tail_name}'s drain doesn't declare a pair\n\n"
    "  {tail_name} is a {symbol}, and its drain is wired to "
    "'{node}'.\n  Drawing a {symbol} declares that net's two "
    "{fet_symbol} devices as a\n  differential pair - but {found}.\n\n"
    "  A {symbol} needs exactly two {fet_symbol} devices sharing its\n"
    "  drain net as their source: those become the pair, and "
    "{tail_name}'s\n  tail= reaches their shared tail current "
    "({tail_bit}).\n\n"
    "  To fix: wire {tail_name}'s drain to the shared source of "
    "exactly two\n  {fet_symbol} devices, or remove {tail_name} if "
    "you didn't mean to\n  draw a pair here."
)

CHECK_D4_TAIL_ON_RAIL = (
    "ERROR - {tail_name}'s drain is wired straight to {rail}\n\n"
    "  {tail_name} is a {symbol}, and its drain - the node its "
    "tail bank\n  feeds - is wired directly to {rail} instead of "
    "to a genuine internal net.\n\n"
    "  That node is never the rail itself: it is the diff pair's "
    "shared\n  source, which has no matrix terminal of its own"
    ".\n  {tail_bit} (what {tail_name}'s "
    "tail= sets) and the rail-tie bit\n  are two different ways to "
    "bias that one node, and they are\n  alternatives, never both "
    "at once.\n\n"
    "  To fix: wire {tail_name}'s drain to the pair halves' actual\n"
    "  shared source net, not to {rail}. If you meant the halves "
    "tied\n  straight to {rail} instead, "
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
    "on the chip - their geometry is built in silicon - so there is "
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
    "symmetric - the three stages of a ring oscillator, say - the "
    "stages that land on the programmable FETs come out at the width "
    "you asked for and this one does not, and the mismatch exists only "
    "on silicon, not in the drawing."
)

CHECK_R1_PARAGRAPH_FIX = (
    "To fix: set the other devices of the same kind to {prop}="
    "{effective} as well, so every stage matches deliberately - "
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
    "reference's W=10), so the chip sinks 2 x ibias - {amps:.0f} uA at "
    "the {ibias_uA:.0f} uA this configuration uses - out of "
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
    "of ibias - see examples/diffamp/), which puts the same current in "
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
    "reference diode - the NMOS with its gate and drain both on "
    "ibias)."
)


# --- pads.py ---------------------------------------------------------------

PADS_PROJECT_NOT_ON_SHUTTLE = (
    "the shuttle index has no project {macro} on shuttle {shuttle}.\n\n"
    "  That usually means the chip in the socket is not the one this\n"
    "  design was taped out on, or --project names a macro that is not\n"
    "  on this shuttle. The demoboard reports its shuttle from the\n"
    "  chip's own ROM, so check --project first. The index is public,\n"
    "  so you can look for yourself:\n"
    "      {url}"
)

PADS_CANT_FETCH_ENTRY_ANALOG = (
    "can't fetch {macro}'s entry in the {shuttle} index ({exc}).\n\n"
    "  It is where the ua -> analog pin numbering comes from, and which\n"
    "  PCB pad to probe is built from that.\n"
    "  Save {url}\n"
    "  as {cache} and re-run to work offline."
)

PADS_CANT_FETCH_ENTRY_PCB = (
    "can't fetch {macro}'s entry in the {shuttle} index ({exc}).\n\n"
    "  Which PCB pad a design's ua[k] comes out on depends on where the\n"
    "  project sits on that shuttle, so it cannot be assumed - the same\n"
    "  design on the next shuttle can come out on different pads. Two\n"
    "  ways forward:\n"
    "    - save {url}\n"
    "      as {cache} and re-run, or\n"
    "    - read the Analog pins table off the project's own page, which\n"
    "      has the same answer already composed:\n"
    "      {page_url}"
)

PADS_UNREADABLE_ENTRY = (
    "{source} is not a project entry this can\n"
    "  read ({exc}). It should be one project's JSON from the shuttle\n"
    "  index, with an `analog_pins` list in it - ua -> internal analog\n"
    "  pin number. If you saved it by hand, check you saved\n"
    "      {url}\n"
    "  and not the whole-shuttle index or the project's web page."
)

PADS_NO_ANALOG_PINS = (
    "{macro} on {shuttle} has no analog pins, so there is nothing to\n"
    "  probe. A purely digital project has none; if you expected this one\n"
    "  to have some, check --project names the macro you meant. The index\n"
    "  entry this read is public:\n"
    "      {url}"
)

PADS_INTERNAL_PIN_NOT_ON_CARRIER = (
    "{macro} on {shuttle} says its ua{ua} is analog pin {internal},\n"
    "  and the chip carrier this shuttle ships with only brings out\n"
    "  {n_pads} of them ({pads}). Either the carrier is a\n"
    "  newer one than mosbius/pads.py knows about - in which case its\n"
    "  wiring needs adding to mosbius/pads.py's carrier_pads(), from\n"
    "  that carrier's own KiCad layout - or the index entry is not\n"
    "  the project you meant."
)

# format_analog_header's English labels around the ASCII-art picture itself
# (the dashes/pipes/brackets of the header drawing are layout, not prose).
PADS_HEADER_TITLE = "  The ANALOG header, along the top edge of the board:"

PADS_HEADER_LABEL_ONE = "The pad in brackets is"
PADS_HEADER_LABEL_MANY = "The pads in brackets are"

PADS_HEADER_CAPTION = (
    "  {label} the one{plural} above"
    " - {pad_list}. Clip the instrument's\n"
    "  ground to any square marked gnd; they are all the same net."
)

# format_pad_table's prose; its aligned column rule ("  -------   ...") is
# layout, not a message, and stays in pads.py.
PADS_TABLE_TITLE = "Pads in use - {macro} on {shuttle}"

PADS_TABLE_HEADER = "  PCB pad   design pin   what this configuration puts on it"

PADS_TABLE_ROW = "  {pad:<9s} {pin:<12s} {what}"

PADS_TABLE_NO_TERMINAL = "connected, but no device terminal on it"

PADS_TABLE_IBIAS_ROW = "bias current in, {amps:.1f} uA - drawn by {drawn_by}"

PADS_TABLE_IBIAS_FALLBACK = "the bias reference"

PADS_TABLE_EMPTY = "  (none - this configuration connects nothing to a package pin)"

PADS_TABLE_IDLE = "  Nothing is on the other analog pads: {which}."

PADS_TABLE_FOOTER = (
    "  These letters are for {macro} as placed on {shuttle}. Its ua ->\n"
    "  analog pin numbering is looked up in the Tiny Tapeout shuttle index."
)


# --- program.py ------------------------------------------------------------

PROGRAM_MPREMOTE_NOT_INSTALLED = (
    "{what} - mpremote isn't installed\n\n"
    "  program.py drives the demoboard through mpremote, the official\n"
    "  MicroPython tool. Install it with 'pip install mpremote' and try\n"
    "  again."
)

# The two port_hint branches _run_mpremote() picks between before building
# PROGRAM_NO_RESULT_LINE.
PROGRAM_PORT_HINT_AUTODETECT = (
    "  mpremote autodetects the port by default, and picks the wrong\n"
    "  serial device when more than one is plugged in (or the wrong one\n"
    "  claims the port first). Tell it which one is the demoboard with\n"
    "  --port, e.g. --port /dev/ttyACM0, and try again.\n\n"
)

PROGRAM_PORT_HINT_EXPLICIT = (
    "  --port {port} was given explicitly, so this isn't mpremote picking\n"
    "  the wrong device - check the board is powered, plugged in, and\n"
    "  actually enumerating at that path.\n\n"
)

PROGRAM_NO_RESULT_LINE = (
    "{what} - no result from the board\n\n"
    "  mpremote exited with code {returncode} and didn't print a result line.\n"
    "  This usually means the board isn't connected, is running the wrong\n"
    "  firmware, or crashed before finishing.\n\n"
    "{port_hint}"
    "Raw output:\n\n"
    "{stdout}\n{stderr}"
)

# The bare "CAN'T READ THE BOARD -- {error}" / "CAN'T PROGRAM -- {error}"
# ProgramError raises that just wrap the device script's own reported
# result["error"] -- not in the plan's site table, added on a full read of
# program.py since each is a complete standalone raise-site message like
# every other one here, not a fragment embedded in a larger template.
PROGRAM_READ_BOARD_ERROR = "CAN'T READ THE BOARD - {error}"

PROGRAM_NO_SHUTTLE_REPORTED = (
    "CAN'T READ THE BOARD - it answered, but reported no shuttle\n\n"
    "  The demoboard reads the shuttle from the chip carrier's own ROM\n"
    "  at boot. Getting nothing back usually means no carrier is seated,\n"
    "  or the firmware is older than chip ROM support. Pass --shuttle\n"
    "  yourself to carry on regardless."
)

PROGRAM_IBIAS_NOT_SET = (
    "\n  BIAS CURRENT NOT SET - this demoboard has no current source.\n\n"
    "  If needed, feed it externally instead."
)

PROGRAM_UPLOAD_BLOCKED = (
    "UPLOAD BLOCKED - {n} safety error{plural} found\n\n"
    "{paths}\n\n"
    "  Fix the design above, or re-run with force=True if you're certain\n"
    "  this is safe."
)

PROGRAM_UPLOAD_ERROR = "CAN'T PROGRAM - {error}"

PROGRAM_UPLOAD_DIDNT_STICK = (
    "UPLOAD DIDN'T STICK - the board says '{enabled}' is selected, "
    "not {project!r}.\n\n"
    "  tt.shuttle.get(...).enable() ran with no error, but the chip's mux\n"
    "  selection did not end up on mini MOSbius.\n"
    "  Re-run; if it keeps happening, check the board is\n"
    "  fully seated or try a fresh USB connection."
)

PROGRAM_VERIFY_FAILED = (
    "VERIFY FAILED - readback doesn't match what was sent\n\n"
    "  sent:      {sent}\n"
    "  captured:  {captured}\n\n"
    "  The chain may have lost sync mid-shift (a bad connection, clock too\n"
    "  fast, or a level issue). Try re-seating the board."
)


# --- decode.py ---------------------------------------------------------

DECODE_SUMMARY_DEVICES_HEADING = "Devices in use"

DECODE_SUMMARY_DEVICES_EMPTY = (
    "Devices in use\n  (none - this config wires nothing to a live device)"
)

DECODE_SUMMARY_DEVICE_LINE = "  {name:<11} {terms}  {settings}"

DECODE_SUMMARY_NETS_HEADING = "Nets"

# Each pin against the segment it is bonded to.
DECODE_SUMMARY_NET_PIN = "{pin} ({bus_node})"

DECODE_SUMMARY_NET_LINE = "  {net:<8} {pin_desc}{terms}"

DECODE_SUMMARY_IBIAS = "ibias = {amps:.1f} uA"


# --- netlist.py --------------------------------------------------------

NETLIST_STALE = (
    "{netlist_path} is older than the schematic it came from\n\n"
    "  {sch}\n  was edited after {netlist_path} was written, so routing this\n"
    "  file would route the circuit as it used to be.\n"
    "  To fix: press Netlist in xschem with {sch_name} open (with xschem\n"
    "  launched from the top of the repo, so it writes to build/), then\n"
    "  run this command again.\n"
)

NETLIST_ROUTED_JSON_GIVEN = (
    "this is a routed design, not an xschem netlist\n"
    "  A file with a \"bitstream\" entry in it is what\n"
    "  `mosbius route --out <file>` writes: routing's answer, not the\n"
    "  question it was asked. `mosbius route` and `mosbius watch` read the\n"
    "  netlist xschem writes for your schematic, `build/<name>.spice`.\n"
    "  To simulate the routing this file already holds, the command is\n"
    "  `python3 -m mosbius.cli simulate <this file>`."
)

NETLIST_PIN_COUNT_MISMATCH = (
    "{name}: mosbius_{kind} takes {n_pins} connections "
    "({pin_names}) but the netlist gives {n_nets}\n"
    "  This usually means the .sym and this parser's DEVICE_PINS table "
    "have drifted apart - check xschem/mosbius_lib/mosbius_{kind}.sym."
)

NETLIST_NO_DEVICES_FOUND = (
    "no mosbius_nmos/mosbius_pmos/mosbius_nsink/mosbius_psource/mosbius_ota/"
    "mosbius_ntail/mosbius_ptail instances found in this netlist\n"
    "  Draw your circuit using the generic devices from xschem/mosbius_lib, "
    "not raw sky130 transistors - the router only "
    "understands those seven."
)


# --- bitstream.py --------------------------------------------------------

BITSTREAM_BIT_OUT_OF_RANGE = (
    "bit {bit} is out of range 0..{max_bit}\n"
    "  The mini-MOSbius config chain is exactly {num_bits} bits "
    "- there is no bit {bit} to set."
)

BITSTREAM_WRONG_LENGTH = (
    "bitstream is {got} hex characters, expected exactly {expected}\n"
    "  A mini-MOSbius config is {num_bits} bits, written as "
    "{expected} hex characters. This string is "
    "{longer_or_shorter} than that - "
    "check for a truncated copy-paste or a mismatched leading '0x'."
)

BITSTREAM_NON_HEX_CHARACTER = (
    "{hexstr!r} contains a non-hex-digit character\n"
    "  A mini-MOSbius bitstream is {expected} hex characters "
    "(0-9, a-f) and nothing else."
)


# --- model.py ---------------------------------------------------------------

MODEL_BIT_OUT_OF_RANGE = (
    "bit(s) {bad} are out of range 0..{max_bit}\n"
    "  The mini-MOSbius config chain is exactly {num_bits} "
    "bits."
)


# --- cli.py ------------------------------------------------------------

CLI_NO_FILE_AT_PATH = (
    "there is no file at {path}\n\n"
    "  This looks like a path rather than a bitstream, and nothing is\n"
    "  there. If you have not routed the design yet, that is the step\n"
    "  that writes it:\n\n"
    "    python3 -m mosbius.cli route build/<design>.spice --out {path}\n\n"
    "  The netlist it reads comes from xschem's Netlist button, with\n"
    "  xschem launched from the top of this repo so it picks up\n"
    "  xschemrc and writes into build/.\n"
)

CLI_UNRECOGNIZED_ARG = (
    "{path} isn't something this command can read\n\n"
    "  It expects either the 48 hex characters of a bitstream, or the\n"
    "  path to a routed design - the JSON file `mosbius route --out`\n"
    "  writes, usually build/<design>.mosbius.json. This file is\n"
    "  neither: it does not parse as JSON.\n\n"
    "  If you meant the netlist (build/<design>.spice), route it first:\n\n"
    "    python3 -m mosbius.cli route {path} --out build/<design>.mosbius.json\n"
)

CLI_JSON_NO_BITSTREAM_KEY = (
    "{path} is JSON, but has no \"bitstream\" in it\n\n"
    "  A routed design records its bitstream under that key. This file\n"
    "  may be from an older version of the router, or hand-edited.\n"
    "  Re-route the design to rewrite it:\n\n"
    "    python3 -m mosbius.cli route build/<design>.spice --out {path}\n"
)

CLI_REPORT_OK = "OK - no errors or warnings{note}."

CLI_REPORT_INFO_NOTE = " ({skipped} info note{plural} hidden, use --verbose)"

CLI_CANT_READ_THAT = "CAN'T READ THAT\n\n  {e}"

CLI_CANT_ASK_BOARD = (
    "can't ask the board which chip is in the socket, and which PCB pad\n"
    "  each ua[k] comes out on depends on that - Tiny Tapeout muxes the\n"
    "  analog pins, so the same design on another shuttle lands on other\n"
    "  pads.\n"
)

CLI_PROJECT_NOT_ON_SHUTTLE = (
    "the chip in the socket is from shuttle {shuttle}, and\n"
    "  {project} is not on it. There are no pads to name, because\n"
    "  this bitstream cannot be programmed to that chip at all -\n"
    "  `mosbius program` would stop with the same thing.\n\n"
    "  Either put the right chip in, or say which project you mean with\n"
    "  --project (it defaults to {default_project}, this repo's own macro)."
)

CLI_CANT_WORK_OUT_PADS = "CAN'T WORK OUT THE PADS\n\n  {e}"

CLI_OUT_OF_DATE = "OUT OF DATE\n\n  {e}"

CLI_IMPOSSIBLE = "IMPOSSIBLE\n\n  {e}"

CLI_DEVICE_ROLES_HEADER = "Device roles:"

CLI_BUS_ROWS_HEADER = "Bus rows:"

CLI_BITSTREAM_LINE = "Bitstream: {bitstream}"

CLI_CANT_SIMULATE = "CAN'T SIMULATE\n\n  {e}"

CLI_SIMULATE_OK = (
    "OK - wrote {out} ({name}_routed, real switch matrix + pads + coupling/wire caps)"
)

CLI_STOPPED_WATCHING = "\nstopped watching."

CLI_PROGRAM_UPLOADED = "OK - uploaded to {project}"

CLI_PROGRAM_VERIFIED_SUFFIX = " (verified)"

CLI_PROGRAM_SHUTTLE_FROM_FLAG = "   shuttle {shuttle} (from --shuttle, not from the chip)"

CLI_PROGRAM_PROVENANCE = "read from the chip in the socket ({identity_source})"

CLI_PROGRAM_SHUTTLE_FROM_CHIP = "   shuttle {shuttle} - {provenance}"

CLI_PROGRAM_CHIP_LINE = "   chip {repo}"

CLI_PROGRAM_CHIP_COMMIT_SUFFIX = " @ {commit}"

CLI_PROGRAM_NO_SHUTTLE_NOTE = (
    "\n  (uploaded fine, but the board reported no shuttle, so which PCB\n"
    "   pad each ua[k] comes out on can't be worked out - that mapping\n"
    "   is per shuttle. Re-run with --shuttle to get the table:\n\n"
    "     mosbius pads {bitstream} --shuttle {default_shuttle})"
)

CLI_PROGRAM_PAD_TABLE_UNAVAILABLE = (
    "  (uploaded fine, but the pad table needs the shuttle index)\n\n  {e}"
)

# build_parser()'s argparse help= text -- shown by `mosbius --help` and
# `mosbius <command> --help`, plausibly the first text a beginner reads.
# ap's own description=__doc__ is the module docstring, not a message
# string, and stays a docstring (Python's own introspection convention,
# same as every other docstring left untouched by this migration).

CLI_HELP_DECODE = "show the circuit a 48-hex-char bitstream configures"

CLI_HELP_PADS = "which PCB pad each connected pin comes out on, for a loaded bitstream"

CLI_HELP_CHECK = "run the safety checker against a bitstream"

CLI_HELP_ROUTE = "netlist -> bitstream (parses, allocates, checks)"

CLI_HELP_SIMULATE = "routed design -> an estimate of the circuit as it would be on silicon"

CLI_HELP_WATCH = "re-run route+check every time the netlist file changes"

CLI_HELP_PROGRAM = "upload a bitstream to hardware"

CLI_HELP_IBIAS = "bias current in amps (default: 100uA)"

CLI_HELP_PROJECT = "project macro name (default: {default_project})"

CLI_HELP_SHUTTLE = (
    "shuttle the chip came from - decides which pad each ua[k] is on "
    "(default: read off the chip in the socket; without a board, pass "
    "e.g. --shuttle {default_shuttle})"
)

CLI_HELP_PORT = "serial port, e.g. /dev/ttyACM0 (default: mpremote autodetects)"

CLI_HELP_BITSTREAM_ARG = "a routed design (build/<design>.mosbius.json), or the 48 hex characters themselves"

CLI_HELP_VERBOSE = "also show INFO notes (e.g. unused bus rows)"

CLI_HELP_NETLIST_ARG = "an xschem-netlisted .spice file"

CLI_HELP_ROUTE_OUT = "persist/reuse routing here"

CLI_HELP_ROUTE_FORCE = "re-route even if --out's stored routing is still valid"

CLI_HELP_SIMULATE_ROUTED_ARG = (
    "a routed design JSON (<name>.mosbius.json), written by `mosbius route --out` - not the netlist"
)

CLI_HELP_SIMULATE_OUT = "output .spice path (default: <name>_routed.spice next to the input)"

CLI_HELP_WATCH_ONCE = "report once and exit, don't poll"

CLI_HELP_PROGRAM_FORCE = "upload even if check() finds an error"

CLI_HELP_PROGRAM_NO_RESET = "skip the known-state reset before shifting"

CLI_HELP_PROGRAM_VERIFY = "shift the bits back out and compare"


# --- watch.py ---------------------------------------------------------

# header + "   " + one of the status words/messages below -- the "   "
# separator is watch.py's own literal, kept out of these constants so
# reusing CLI_OUT_OF_DATE/CLI_IMPOSSIBLE below doesn't change what they
# mean in cli.py's own, differently-formatted usage.
WATCH_HEADER = "mosbius watch - {name}          {time}"

WATCH_CANT_READ = "CAN'T READ\n\n  {e}"

WATCH_STATUS_DANGEROUS = "DANGEROUS"

WATCH_STATUS_IMPOSSIBLE = "IMPOSSIBLE"

WATCH_STATUS_OK = "OK"

WATCH_STATUS_OK_WITH_WARNINGS = "OK, with warnings"

WATCH_MORE_WARNINGS = "  {n} warning(s) - see 'mosbius check' for detail"
