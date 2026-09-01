# SPDX-License-Identifier: Apache-2.0
"""Which PCB pad to clip a probe onto, looked up rather than remembered.

A design's `ua[k]` is not a pad letter, and the answer is composed from two
independent halves. Tiny Tapeout muxes the chip's analog pins, so which
*internal analog index* a project's `ua[k]` lands on depends on where that
project was placed on that shuttle; and which *PCB pad* an internal index
comes out on depends on how that shuttle's chip carrier is wired to the
demoboard. Both halves are free to change, so `tt_um_tnt_mosbius` on
ttsky26b may well come out on different letters than the same design on
ttsky25a. Nothing here guesses either half.

**Half one, the project: the shuttle index API.**
https://index.tinytapeout.com/{shuttle}/{macro}.json publishes that
project's `analog_pins`, a list indexed by `ua` whose values are internal
analog indices -- for `tt_um_tnt_mosbius` on ttsky25a, `[5, 0, 4, 1, 3, 2]`,
i.e. `ua0` is internal 5, `ua1` is internal 0, and so on. That is a
documented JSON API (https://github.com/TinyTapeout/tinytapeout-index,
index files CC0), it is per-project and per-shuttle, and it is the same data
tinytapeout.com itself renders from.

**Half two, the carrier: ETR_CARRIER_PADS below.** No API publishes the pad
letters. tinytapeout.com's own Analog pins table composes them in the
browser from a hard-coded twelve-entry array in the website's source
(`functions/components/AnalogPinout.tsx` in TinyTapeout/tinytapeout_www),
indexed by internal analog index. So a project page is not an independent
source for the letters: it is this same table, rendered.

That array is reproduced here, but *verified from the boards themselves*
rather than copied on trust (2026-08-29), by joining two KiCad layouts on
the carrier connector's pin numbers:

  - TinyTapeout/breakout-ttsky-cob, connector `J1`
    (HRS_DF12NB-60DS-0.5V): pin -> net `an0`..`an11`
  - TinyTapeout/tt-demo-pcb, connector `J5` (TT_HRS_CARRIER_REVC), `L`
    side: pin -> net `A`..`X`, the demoboard's ANALOG header letters

Joining pin `N` to `L{N}` gives `an0..an11` -> C D F G J K X W U T R Q,
matching the website's array exactly, and the same join lines up every
`uio`, `ui_in`, `project_clk` and `project_rst` pin, so the alignment is
not a coincidence. Two other facts fell out of it and are worth knowing at
a bench: the ETR carrier routes only twelve of the header's twenty-two
lettered pads to the chip at all, and on the ttsky carrier eight of the
remaining ten (A, B, E, H, L, M, N, P) are tied straight to ground, so
clipping a probe onto the wrong letter is not merely a dead node.

*Which* shuttle to ask about does not have to be assumed: the chip
carrier's ROM names it, and mosbius/program.py's read_board_identity()
reads it back over the demoboard.

Verified against silicon 2026-08-28, before any of this was fetched: `ua1`
-> pad C and `ua2` -> pad J measured a working inverter, `ua3` -> pad D a
working ring oscillator. Those three agree with what this composes, which
is the only end-to-end check the mapping has.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from mosbius import messages
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
PROJECT_INDEX_URL = "https://index.tinytapeout.com/{shuttle}/{macro}.json"
PROJECT_PAGE_URL = "https://tinytapeout.com/chips/{shuttle}/{macro}"
CACHE_DIR = Path("build")


# Internal analog index -> PCB pad, for the two chip carriers Tiny Tapeout
# has shipped. This is the carrier's wiring, not the chip's and not the
# project's, which is why it is keyed by carrier and not by shuttle.
#
# ETR_CARRIER_PADS is verified from the two KiCad layouts named in the
# module docstring; it is also, letter for letter, the array the website
# renders its PCB Pin column from. Twelve entries, because the carrier
# brings out twelve of the demoboard's twenty-two lettered analog pads.
#
# PRE_ETR_CARRIER_PADS covers the shuttles that predate the ETR demoboard,
# whose breakout labelled its analog pins A0..A5 and B0..B5 rather than with
# letters. Upstream's own website intends this split but never reaches it:
# its check is `shuttle in nonETRShuttles` against a JavaScript *array*,
# which tests indices rather than values and so is always false. So
# tinytapeout.com currently prints ETR letters on tt06/tt07/tt08 project
# pages, where they mean nothing. That is the second reason not to scrape
# those pages, and the reason this does the split itself.
ETR_CARRIER_PADS = ("C", "D", "F", "G", "J", "K", "X", "W", "U", "T", "R", "Q")
PRE_ETR_CARRIER_PADS = tuple(f"A{i}" for i in range(6)) + tuple(f"B{i}" for i in range(6))
PRE_ETR_SHUTTLES = frozenset({"tt06", "tt07", "tt08"})


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
# nothing. Only twelve of the twenty-two reach the chip at all through the
# ETR carrier -- those in ETR_CARRIER_PADS -- and only as many of those as
# the project has analog pins carry anything. That is why the bench output
# draws the whole header rather than listing letters: a letter is only
# findable in relation to its neighbours and the grounds beside it.
GND_PAD = "gnd"
ANALOG_HEADER = (
    ("A", "C", GND_PAD, "E", "G", "J", GND_PAD, "L", "N", "Q", GND_PAD, "S", "U", "W", GND_PAD, "3v3"),
    (GND_PAD, "B", "D", "F", GND_PAD, "H", "K", "M", GND_PAD, "P", "R", "T", GND_PAD, "V", "X", GND_PAD),
)


class PadLookupError(Exception):
    """The pad mapping could not be established, explained in full."""


def carrier_pads(shuttle: str) -> tuple[str, ...]:
    """The chip carrier's internal-analog-index -> PCB pad wiring.

    Which carrier a shuttle ships with is the only thing that has to be
    decided from the shuttle's name, and there have been exactly two:
    everything from the ETR demoboard onwards uses the lettered ANALOG
    header, while tt06/tt07/tt08 predate it.
    """
    return PRE_ETR_CARRIER_PADS if shuttle in PRE_ETR_SHUTTLES else ETR_CARRIER_PADS


def _analog_pins(shuttle: str, macro: str) -> list[int]:
    """`analog_pins` for one project, off the shuttle index API.

    The list is indexed by `ua` and its values are internal analog indices.
    Cached under build/ on first fetch, so a bench with no internet needs
    one download or one manual save.
    """
    cache = CACHE_DIR / f"pads_{shuttle}_{macro}.json"
    url = PROJECT_INDEX_URL.format(shuttle=shuttle, macro=macro)

    if cache.exists():
        body = cache.read_text()
    else:
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "mosbius-configurator"}
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read().decode()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise PadLookupError(
                    messages.PADS_PROJECT_NOT_ON_SHUTTLE.format(
                        macro=macro, shuttle=shuttle, url=url,
                    )
                ) from exc
            raise PadLookupError(
                messages.PADS_CANT_FETCH_ENTRY_ANALOG.format(
                    macro=macro, shuttle=shuttle, exc=exc, url=url, cache=cache,
                )
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PadLookupError(
                messages.PADS_CANT_FETCH_ENTRY_PCB.format(
                    macro=macro, shuttle=shuttle, exc=exc, url=url, cache=cache,
                    page_url=PROJECT_PAGE_URL.format(shuttle=shuttle, macro=macro),
                )
            ) from exc
        CACHE_DIR.mkdir(exist_ok=True)
        cache.write_text(body)

    try:
        entry = json.loads(body)
        analog_pins = entry["analog_pins"]
        pins = [int(index) for index in analog_pins]
    except (ValueError, TypeError, KeyError) as exc:
        raise PadLookupError(
            messages.PADS_UNREADABLE_ENTRY.format(
                source=cache if cache.exists() else url, exc=exc, url=url,
            )
        ) from exc

    if not pins:
        raise PadLookupError(
            messages.PADS_NO_ANALOG_PINS.format(macro=macro, shuttle=shuttle, url=url)
        )
    return pins


def pad_map(shuttle: str, macro: str) -> dict[str, str]:
    """{'ibias': 'K', 'ua1': 'C', ...} for one design on one shuttle.

    Composed from the two halves in the module docstring: the index API for
    ua -> internal analog pin, and the carrier's own wiring for internal
    analog pin -> PCB pad.

    `ua` 0 is named `ibias` here because that is what this chip's bias
    reference pin is called everywhere else in this package and on every
    schematic. Every other `ua[k]` keeps its number.
    """
    pins = _analog_pins(shuttle, macro)
    pads = carrier_pads(shuttle)

    mapping = {}
    for ua, internal in enumerate(pins):
        if not 0 <= internal < len(pads):
            raise PadLookupError(
                messages.PADS_INTERNAL_PIN_NOT_ON_CARRIER.format(
                    macro=macro, shuttle=shuttle, ua=ua, internal=internal,
                    n_pads=len(pads), pads=", ".join(pads),
                )
            )
        mapping["ibias" if ua == 0 else f"ua{ua}"] = pads[internal]
    return mapping


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
    label = messages.PADS_HEADER_LABEL_ONE if len(marked) == 1 else messages.PADS_HEADER_LABEL_MANY
    plural = "" if len(marked) == 1 else "s"
    return "\n".join([
        messages.PADS_HEADER_TITLE,
        "",
        "   " + rows[0],
        "   " + rows[1],
        "",
        messages.PADS_HEADER_CAPTION.format(
            label=label, plural=plural, pad_list=", ".join(marked),
        ),
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
        drawn_by = ", ".join(users) if users else messages.PADS_TABLE_IBIAS_FALLBACK
        on_pin["ibias"] = [
            messages.PADS_TABLE_IBIAS_ROW.format(amps=decoded.ibias * 1e6, drawn_by=drawn_by)
        ]

    def order(name: str) -> tuple[int, str]:
        # ua1..ua5 in the order the design names them; ibias last, since it
        # is bench setup rather than a signal to look at.
        return (1, "") if name == "ibias" else (0, name)

    lines = [messages.PADS_TABLE_TITLE.format(macro=macro, shuttle=shuttle), ""]
    lines.append(messages.PADS_TABLE_HEADER)
    lines.append("  -------   ----------   ----------------------------------")
    for pin in sorted(in_use, key=order):
        what = ", ".join(on_pin.get(pin, [])) or messages.PADS_TABLE_NO_TERMINAL
        lines.append(messages.PADS_TABLE_ROW.format(pad=in_use[pin], pin=pin, what=what))
    if not in_use:
        lines.append(messages.PADS_TABLE_EMPTY)

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
        lines.append(messages.PADS_TABLE_IDLE.format(which=which))
        lines.append("")
    lines.append(messages.PADS_TABLE_FOOTER.format(macro=macro, shuttle=shuttle))
    return "\n".join(lines)
