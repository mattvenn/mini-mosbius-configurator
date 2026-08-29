# SPDX-License-Identifier: Apache-2.0
"""Which PCB pad to clip a probe onto, looked up rather than remembered.

A design's `ua[k]` is not a pad letter, and the relationship is fixed by
neither the design nor the board alone. Tiny Tapeout muxes the chip's
analog pins, so which internal analog index a project's `ua[k]` lands on
depends on where that project was placed on that shuttle; and which PCB
pad an internal index comes out on depends on how that shuttle's carrier
is wired. Both halves can change from one shuttle to the next, so
`tt_um_tnt_mosbius` on ttsky26b may well come out on different letters
than the same design on ttsky25a. Nothing here can know that, and nothing
here guesses it.

**The lookup is one fetch: the project's own page.** Every project page
carries an Analog pins table with exactly the three columns needed --
`ua`, PCB Pin, Internal index -- already composed for that project on that
shuttle, e.g.

    https://tinytapeout.com/chips/ttsky25a/tt_um_tnt_mosbius

    ua   PCB Pin   Internal index   Description
    0    K         5                Reference Bias
    1    C         0                Bus 1A
    ...

so `pad_map()` reads `ua` -> PCB Pin straight off it and never computes a
letter. Both other candidate sources were tried and are not enough on
their own: the shuttle index (https://index.tinytapeout.com/ttsky25a.json)
publishes each project's `analog_pins`, which is `ua` -> internal index and
carries no letters; and the copy of the index on the demoboard itself is
stripped further still -- a `Design` there has macro/name/clock_hz/address
and no `analog_pins` at all, checked on a real board 2026-08-29.

*Which* shuttle to ask about does not have to be assumed: the chip
carrier's ROM names it, and mosbius/program.py's read_board_identity()
reads it back over the demoboard.

This is plain server-rendered HTML rather than an API, so it is parsed by
matching the table's own column headers rather than by position -- see
_parse_analog_pins(). If Tiny Tapeout ever restyles those pages this is
the thing that breaks, and it breaks loudly: a page that parses to no rows
raises rather than returning a partial map.

Verified against hardware 2026-08-28, before any of it was fetched: `ua1`
-> pad C and `ua2` -> pad J measured a working inverter, `ua3` -> pad D a
working ring oscillator. Those three agree with what the page now says,
which is the only independent check this mapping has ever had.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from mosbius.decode import decode
from mosbius.model import SwitchConfig
from mosbius.route import TERMINAL_WORD

# What is in the socket unless someone says otherwise: this project's macro,
# on the shuttle it was taped out with. Kept here rather than in the CLI so
# `mosbius program` and `mosbius pads` cannot drift apart.
#
# DEFAULT_SHUTTLE is never used as a silent fallback. The chip carrier has
# its own ROM naming the shuttle it came from, the demoboard parses it at
# boot, and mosbius/program.py's read_board_identity() reads it back, so
# the shuttle is a measurement rather than an assumption. When that read
# fails the CLI stops rather than guessing -- a pad table names a physical
# pad to clip onto, and a wrong one reads exactly like a right one -- so
# this constant only appears in help text and in the `--shuttle ttsky25a`
# the failure suggests for working away from the bench.
DEFAULT_PROJECT = "tt_um_tnt_mosbius"
DEFAULT_SHUTTLE = "ttsky25a"
PROJECT_PAGE_URL = "https://tinytapeout.com/chips/{shuttle}/{macro}"
CACHE_DIR = Path("build")


# The ANALOG breakout header as it is physically laid out on the demoboard,
# read off the board itself (TT demoboard ETR v3.2) rather than derived:
# two rows, with ground squares among the lettered pads.
#
# Written out position by position because the arrangement is not guessable
# from the letters. Sixteen columns; a ground every fourth column in each
# row, the two rows offset by two so the grounds alternate as you read
# along -- bottom, top, bottom, top -- starting with the one directly under
# `A`. The rightmost column is the supply pair, 3v3 over ground. The
# consequence is that `B` is not under `A`, it is under the gap to its
# right, and which row carries the higher letter of a pair flips at every
# ground. Anyone reconstructing this from the letter sequence alone gets it
# wrong, which is why it is data and not a rule.
#
# The letters run A..X with I and O left out, the usual convention so they
# cannot be misread as 1 and 0, so a gap in the sequence is normal and means
# nothing. Only a handful of the twenty-two carry any one chip's analog
# pins -- which handful is what pad_map() looks up, and it is not the same
# from shuttle to shuttle; the rest belong to other things on the board.
# That is
# why the bench output draws the whole header rather than listing six
# letters: a letter is only findable in relation to its neighbours and the
# grounds beside it.
GND_PAD = "gnd"
ANALOG_HEADER = (
    ("A", "C", GND_PAD, "E", "G", "J", GND_PAD, "L", "N", "Q", GND_PAD, "S", "U", "W", GND_PAD, "3v3"),
    (GND_PAD, "B", "D", "F", GND_PAD, "H", "K", "M", GND_PAD, "P", "R", "T", GND_PAD, "V", "X", GND_PAD),
)


class PadLookupError(Exception):
    """The pad mapping could not be established, explained in full."""


class _AnalogPinsParser(HTMLParser):
    """Pull the Analog pins table out of a Tiny Tapeout project page.

    The page is server-rendered HTML, not an API, so this matches the
    table by its own column headers rather than by position: it collects
    every table on the page, then keeps the one whose header row contains
    both `ua` and a PCB-pin column. A restyle that renames those headers
    makes this find nothing, which raises -- far better than a restyle
    that reorders the columns and silently hands back a wrong letter.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None
        elif tag == "tr" and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _parse_analog_pins(html: str, shuttle: str, macro: str) -> dict[str, str]:
    """{'ibias': 'K', 'ua1': 'C', ...} from a project page's HTML.

    `ua` 0 is named `ibias` here because that is what this chip's bias
    reference pin is called everywhere else in this package and on every
    schematic -- the page calls it "Reference Bias" in its description
    column. Every other `ua[k]` keeps its number.
    """
    parser = _AnalogPinsParser()
    parser.feed(html)

    def column(header_row, *wanted):
        for i, cell in enumerate(header_row):
            text = cell.strip().lower()
            if any(w == text for w in wanted):
                return i
        return None

    for table in parser.tables:
        if not table:
            continue
        header = table[0]
        ua_col = column(header, "ua")
        pad_col = column(header, "pcb pin", "pcb pad", "pin")
        if ua_col is None or pad_col is None:
            continue
        found = {}
        for row in table[1:]:
            if max(ua_col, pad_col) >= len(row):
                continue
            number, pad = row[ua_col].strip(), row[pad_col].strip()
            if not number.isdigit() or not pad:
                continue
            found["ibias" if number == "0" else f"ua{number}"] = pad
        if found:
            return found

    raise PadLookupError(
        f"{macro}'s page on {shuttle} has no Analog pins table this can read.\n\n"
        f"  That table is where the PCB pad letters come from -- it is the only\n"
        f"  place that publishes them, so there is nothing to fall back on.\n"
        f"  Either the project has no analog pins (a purely digital design has\n"
        f"  nothing to probe), or Tiny Tapeout has restyled the page and\n"
        f"  mosbius/pads.py's _parse_analog_pins() needs updating. Check by eye:\n"
        f"      {PROJECT_PAGE_URL.format(shuttle=shuttle, macro=macro)}"
    )


def pad_map(shuttle: str, macro: str) -> dict[str, str]:
    """{'ibias': 'K', 'ua1': 'C', ...} for one design on one shuttle.

    Read off that project's own page, because the answer is a property of
    the project *and* the shuttle together and neither this package nor the
    demoboard holds it. The page is cached under build/ on first fetch, so
    a bench with no internet needs one download or one manual save.
    """
    cache = CACHE_DIR / f"pads_{shuttle}_{macro}.html"
    if cache.exists():
        return _parse_analog_pins(cache.read_text(), shuttle, macro)

    url = PROJECT_PAGE_URL.format(shuttle=shuttle, macro=macro)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "mosbius-configurator"})
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise PadLookupError(
                f"there is no page for {macro} on shuttle {shuttle}.\n\n"
                f"  That usually means the chip in the socket is not the one this\n"
                f"  design was taped out on, or --project names a macro that is not\n"
                f"  on this shuttle. The demoboard reports its shuttle from the\n"
                f"  chip's own ROM, so check --project first:\n"
                f"      {url}"
            ) from exc
        raise PadLookupError(
            f"can't fetch {macro}'s page on {shuttle} ({exc}).\n\n"
            f"  Its Analog pins table is where the PCB pad letters come from.\n"
            f"  Save {url}\n"
            f"  as {cache} and re-run to work offline."
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PadLookupError(
            f"can't fetch {macro}'s page on {shuttle} ({exc}).\n\n"
            f"  Which PCB pad a design's ua[k] comes out on depends on where the\n"
            f"  project sits on that shuttle and how that shuttle's carrier is\n"
            f"  wired, so it cannot be assumed -- the same design on the next\n"
            f"  shuttle can come out on different letters. Two ways forward:\n"
            f"    - save {url}\n"
            f"      as {cache} and re-run, or\n"
            f"    - read the Analog pins table off that page yourself; its\n"
            f"      ua -> PCB Pin columns are exactly what this needs."
        ) from exc

    CACHE_DIR.mkdir(exist_ok=True)
    cache.write_text(body)
    return _parse_analog_pins(body, shuttle, macro)


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
    if _bias_users(decoded):
        wanted.add("ibias")

    pads = pad_map(shuttle, macro)
    return {name: pad for name, pad in pads.items() if name in wanted}


def _bias_users(decoded) -> list[str]:
    """The devices in a decoded design that actually draw on the bias
    reference, so `ibias` is only called for when something needs it.

    A mirror or the OTA always draws. A differential pair draws only if
    its shared source is left off the rail, since tying it to a rail
    shorts the tail bank out (CLAUDE.md's R3 note).
    """
    users = []
    for device in decoded.devices:
        if device.name.startswith(("nsink", "psource", "ota")):
            users.append(device.name)
        elif "diffpair" in device.name:
            tied = any(v for k, v in device.settings.items() if k.startswith("shared_source"))
            if not tied and device.settings.get("tail"):
                users.append(device.name)
    return users


def _pin_name(net: str) -> str:
    """decode() names a pin net `ua[3]`; a pad map keys it `ua3`."""
    return f"ua{net[3:-1]}" if net.startswith("ua[") else net


def format_analog_header(in_use: dict[str, str]) -> str:
    """A picture of the ANALOG header with this design's pads marked.

    The letter alone does not find a hole on a real board: the pads are
    small, the silkscreen is smaller, and the letter sequence has gaps in
    it (no I, no O) so counting along goes wrong. What finds it is the
    shape -- this letter, that many places from the end, with a ground
    square on one side. So this draws the header as it physically is and
    puts the used pads in brackets, rather than asking someone to hunt.

    The grounds are drawn for the same reason: every measurement here
    needs the instrument grounded to the board, that is the other lead the
    user has to place, and it is on this same header.
    """
    width = 4
    rows = []
    for row in ANALOG_HEADER:
        cells = []
        for pad in row:
            label = f"[{pad}]" if pad in in_use.values() else pad
            cells.append(label.center(width))
        rows.append("".join(cells).rstrip())
    marked = sorted(in_use.values())
    return "\n".join([
        "  The ANALOG header, along the top edge of the board:",
        "",
        "   " + rows[0],
        "   " + rows[1],
        "",
        f"  {'The pad in brackets is' if len(marked) == 1 else 'The pads in brackets are'}"
        f" the one{'' if len(marked) == 1 else 's'} above"
        f" -- {', '.join(marked)}. Clip the instrument's",
        "  ground to any square marked gnd; they are all the same net.",
    ])


def format_pad_table(config: SwitchConfig, shuttle: str, macro: str) -> str:
    """The bench table: which PCB pad to clip onto, for every pin this
    configuration actually connects, and what is on it.

    This is the answer to "the bitstream is loaded, now where do I put the
    probe?", and it cannot be answered from the schematic alone: the
    schematic says `ua2`, and nothing on the board is labelled that way.
    """
    decoded = decode(config)
    in_use = pads_in_use(config, shuttle, macro)
    everything = pad_map(shuttle, macro)

    on_pin: dict[str, list[str]] = {}
    for device in decoded.devices:
        for terminal, net in device.terminals.items():
            pin = _pin_name(net)
            if pin in in_use:
                on_pin.setdefault(pin, []).append(
                    f"{device.name} {TERMINAL_WORD.get(terminal, terminal)}"
                )
    if "ibias" in in_use:
        # Both halves of one differential pair draw through the same tail,
        # so naming the pair once reads as what it is.
        users = list(dict.fromkeys(d.rstrip("+-") for d in _bias_users(decoded)))
        drawn_by = ", ".join(users) if users else "the bias reference"
        on_pin["ibias"] = [
            f"bias current in, {decoded.ibias * 1e6:.1f} uA -- drawn by {drawn_by}"
        ]

    def order(name: str) -> tuple[int, str]:
        # ua1..ua5 in the order the design names them; ibias last, since it
        # is bench setup rather than a signal to look at.
        return (1, "") if name == "ibias" else (0, name)

    lines = [f"Pads in use -- {macro} on {shuttle}", ""]
    lines.append("  PCB pad   design pin   what this configuration puts on it")
    lines.append("  -------   ----------   ----------------------------------")
    for pin in sorted(in_use, key=order):
        what = ", ".join(on_pin.get(pin, [])) or "connected, but no device terminal on it"
        lines.append(f"  {in_use[pin]:<9s} {pin:<12s} {what}")
    if not in_use:
        lines.append("  (none -- this configuration connects nothing to a package pin)")

    idle = sorted(
        (pad, pin) for pin, pad in everything.items() if pin not in in_use
    )
    lines.append("")
    if in_use:
        # The letters above say which pad; this says where it is. Both are
        # needed -- "pad C" is not findable by reading silkscreen alone.
        lines.append(format_analog_header(in_use))
        lines.append("")
    if idle:
        which = ", ".join(f"{pad} ({pin})" for pad, pin in idle)
        lines.append(f"  Nothing is on the other analog pads: {which}.")
        lines.append("")
    lines += [
        f"  These letters are for {macro} as placed on {shuttle}, and are read",
        "  from that project's own page every time rather than remembered. The",
        "  same design on another shuttle can come out on entirely different",
        "  pads: both where the project sits on the shuttle and how that",
        "  shuttle's carrier is wired are free to change.",
    ]
    return "\n".join(lines)
