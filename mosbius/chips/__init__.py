# SPDX-License-Identifier: Apache-2.0
"""Which mini-MOSbius part a design is being routed for.

There is more than one mini-MOSbius. Two different designs have been taped
out -- tnt's (`tt_um_tnt_mosbius`) and Andrew Kang's (`tt_um_mosbius`) -- and
each appears on several Tiny Tapeout shuttles. They share a circuit family:
the same device roles, the same crosspoint names, the same `tt_asw_3v3` switch
cell, the same two internal bus sides joined by `cfg_bus_short`. They differ in
how many bits their config chain has, which bit does what, how a package pin
reaches the bus, and how a bus row reaches a rail.

A `Chip` is all of that in one object, so the router, the checker and the SPICE
writer can be written once and asked which part they are working on. Everything
that used to be a module-level constant compiled for tnt lives here.

Two things every caller should know:

- **Nothing guesses which part is in the socket.** `chip_for_macro()` maps the
  macro name the user already passes as `--project` to a part. A macro with no
  bit map raises rather than falling back, because shifting one part's chain
  into the other closes arbitrary switches: the whole point of the bit map is
  that bit 47 means different things on the two chips.
- **The derived maps below are the router's vocabulary.** They are computed
  once per part from the generated bit table, never restated, so a regenerated
  table cannot drift from the rows the router thinks exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from mosbius.chips import kang_bits, tnt_bits
from mosbius.chips.bits import DeviceSettingBit, MatrixBit

DATA_DIR = Path(__file__).parent.parent / "data"


@dataclass(frozen=True)
class BondedPins:
    """Package pins wired to bus rows by permanent bond wires (tnt's part).

    A bond wire is not a switch. The row a pin sits on is always joined to it,
    so a net routed onto that row reaches the outside world whether or not the
    design asked for it, and a net that needs that pin has no choice of row.
    """

    rows: dict[str, tuple[str, int]]  # "ua[1]" -> ("A", 1)

    switched = False


@dataclass(frozen=True)
class SwitchedPins:
    """Package pins that reach a bus row through a matrix switch (Andrew's).

    Each pin still reaches exactly one row, but the connection costs a bit and
    is absent unless the design asks for it, so an unused pin is genuinely
    disconnected rather than merely unused.
    """

    rows: dict[str, tuple[str, int]]  # "ua[1]" -> ("A", 1)
    bits: dict[str, int]              # "ua[1]" -> the cfg_bus_ext bit

    switched = True


@dataclass(frozen=True)
class Chip:
    """One taped-out mini-MOSbius part."""

    key: str        # short name used in code and in diagnostics: "tnt", "kang"
    macro: str      # the Tiny Tapeout macro name, e.g. "tt_um_tnt_mosbius"
    title: str      # how to name it to a user, e.g. "tnt's mini-MOSbius"
    num_bits: int   # length of the config chain
    matrix_bits: dict[int, MatrixBit]
    setting_bits: dict[int, DeviceSettingBit]
    pins: BondedPins | SwitchedPins
    device_terminals: dict[str, dict[str, str]]
    bus_wire_cap: dict[str, float]
    device_library: Path
    # Which physical `ua[k]` carries the bias reference. tnt puts it on ua[0],
    # Andrew on ua[5]. It is the one analog pin with no switch matrix behind
    # it, so it is named rather than numbered everywhere a user sees it.
    ibias_ua: int
    # Which device-setting bits put the OTA in amplifier mode: the load gates
    # have to follow one of its own drains, and nothing in a schematic says
    # which. tnt needs `ctrl_otan_mode[0]` closed, matching the ideal symbol,
    # which hardwires both load gates to `outp`. Andrew's `ctrl_otan_diode`
    # means the opposite -- closing it diode-connects the *output*, turning
    # the block into a follower rather than an amplifier -- so his amplifier
    # mode is the open state and this is empty. Leaving tnt's open floats the
    # gate node and the block is not an amplifier at all.
    ota_amplifier_bits: tuple[tuple[str, int], ...]
    # How to describe the OTA's own settings to a user, as
    # {label: DeviceSettings field}. The two parts genuinely differ here, so
    # the label a reader sees follows the part rather than being one wording
    # bent to cover both.
    ota_setting_fields: dict[str, str]
    # Terminals the symbol library draws that this part does not bring out to
    # the switch matrix, and why. A design that wires one cannot be built
    # here, and saying so is the whole point: without this the router drops
    # the connection, produces a bitstream, and reports success.
    absent_terminals: dict[tuple[str, str], str]
    # Schematic port name -> the physical `ua` number that port really is.
    #
    # A design sheet's five bus pins are called ua1..ua5 on both parts, because
    # that is the vocabulary a user draws in and the same sheet has to route to
    # either chip. On tnt's part those names are also the physical pin numbers.
    # On Andrew's they are not: his bias reference is ua[5] and his five matrix
    # pins are ua[0]..ua[4], so the sheet's ua1 is physically his ua[0].
    #
    # Only pad lookup needs the physical number, since the shuttle index is
    # written in those terms. Nothing on the demoboard is labelled with either
    # numbering -- a user reads PCB pad letters -- so this translation stays
    # inside mosbius/pads.py rather than surfacing as two names for one pin.
    ua_index: dict[str, int]
    # Whether programming has to drive the design's reset. Andrew's chain has a
    # reset input; tnt's does not, and driving one that is not there is silent.
    needs_reset: bool
    num_rows: int = 6

    # -- identity -----------------------------------------------------------

    def __str__(self) -> str:
        return self.title

    @property
    def hex_chars(self) -> int:
        """Bitstream length. A chain that is not a multiple of four bits still
        rounds up to a whole hex digit, so this is not always num_bits // 4.
        """
        return (self.num_bits + 3) // 4

    # -- the bit table, indexed the ways the router asks for it -------------

    @cached_property
    def all_bits(self) -> dict[int, MatrixBit | DeviceSettingBit]:
        return {**self.matrix_bits, **self.setting_bits}

    @cached_property
    def matrix_bit_by_pin_row(self) -> dict[tuple[str, int], int]:
        """bit for (pin, row), for every matrix signal with a crosspoint."""
        return {
            (mb.pin, mb.row): bit
            for bit, mb in self.matrix_bits.items()
            if mb.crosspoint is not None
        }

    @cached_property
    def bus_short_bit_by_row(self) -> dict[int, int]:
        """bit for cfg_bus_short[row], which joins the two bus sides."""
        return {
            mb.row: bit
            for bit, mb in self.matrix_bits.items()
            if mb.pin == "cfg_bus_short"
        }

    @cached_property
    def _rail_taps(self) -> dict[str, dict[tuple[str, int], int]]:
        """rail -> {(side, row): bit}, every way a bus row reaches a rail.

        Keyed by rail first, because a (side, row) alone does not identify a
        tap: tnt's six taps happen to sit on six different rows, one rail
        each, but Andrew's are two full columns, so every A-side row can reach
        either rail and a (side, row) key would collide.
        """
        taps: dict[str, dict[tuple[str, int], int]] = {}
        for bit, mb in self.matrix_bits.items():
            if mb.rail is None:
                continue
            taps.setdefault(mb.rail, {})[(mb.bus, mb.row)] = bit
        return taps

    def rail_taps(self, rail: str) -> dict[tuple[str, int], int]:
        """Where this rail can be reached, and which bit does it."""
        return self._rail_taps.get(rail, {})

    @cached_property
    def setting_bit_by_pin_index(self) -> dict[tuple[str, int], int]:
        return {(sb.pin, sb.index): bit for bit, sb in self.setting_bits.items()}

    @cached_property
    def crosspoints(self) -> set[str]:
        return {mb.crosspoint for mb in self.matrix_bits.values() if mb.crosspoint}

    @cached_property
    def _switch_pin_by_crosspoint(self) -> dict[str, tuple[str, str]]:
        by_crosspoint: dict[str, tuple[str, str]] = {}
        for mb in self.matrix_bits.values():
            if mb.crosspoint is None:
                continue  # a bus-level bit: no device terminal behind it
            known = by_crosspoint.setdefault(mb.crosspoint, (mb.pin, mb.bus))
            if known != (mb.pin, mb.bus):
                raise AssertionError(
                    f"{mb.crosspoint} is reached by two different switch pins, "
                    f"{known} and {(mb.pin, mb.bus)} -- {self.key}'s bit map "
                    f"disagrees with itself"
                )
        return by_crosspoint

    @cached_property
    def _terminal_tables(self) -> tuple[dict, dict]:
        """Which switch pin each device terminal is wired to, and which bus
        side that puts it on. Both are derived from the generated bit map
        rather than transcribed, so a correction there cannot silently drift
        out of sync with the router.

        Side is a property of the terminal, not of the device. Most roles sit
        wholly on one side, but tnt's OTA straddles both, inp/outp on side A
        and inm/outm on side B, so no single value could describe it. Asking
        for a *role's* side is what used to raise KeyError('ota') the moment
        anyone routed one, until 2026-08-21.
        """
        pins: dict[tuple[str, str], str] = {}
        sides: dict[tuple[str, str], str] = {}
        for role, terminals in self.device_terminals.items():
            for terminal, crosspoint in terminals.items():
                pin, side = self._switch_pin_by_crosspoint[crosspoint]
                pins[(role, terminal)] = pin
                sides[(role, terminal)] = side
        return pins, sides

    @cached_property
    def terminal_pin(self) -> dict[tuple[str, str], str]:
        return self._terminal_tables[0]

    @cached_property
    def terminal_side(self) -> dict[tuple[str, str], str]:
        return self._terminal_tables[1]

    @cached_property
    def rows_by_pin(self) -> dict[str, frozenset[int]]:
        """Which bus rows each switch pin can actually reach.

        Most terminals reach all six rows, but the diff-pair and OTA *inputs*
        reach only rows 1 to 3 (SPEC.md Sec 2.12). Derived, not transcribed,
        for the same reason as the terminal tables.
        """
        rows: dict[str, set[int]] = {}
        for pin, row in self.matrix_bit_by_pin_row:
            rows.setdefault(pin, set()).add(row)
        return {pin: frozenset(r) for pin, r in rows.items()}

    @cached_property
    def terminal_by_crosspoint(self) -> dict[str, str]:
        """Crosspoint node -> "device.terminal", so a diagnostic can say
        `ndiffpair+.g` instead of `xpt_dpn_inp`.
        """
        return {
            xpt: f"{device}.{terminal}"
            for device, terminals in self.device_terminals.items()
            for terminal, xpt in terminals.items()
        }

    # -- rows ---------------------------------------------------------------

    @cached_property
    def rows(self) -> frozenset[int]:
        return frozenset(range(1, self.num_rows + 1))

    @cached_property
    def all_rows(self) -> set[tuple[str, int]]:
        return {(side, row) for side in ("A", "B") for row in self.rows}

    @cached_property
    def port_row(self) -> dict[str, tuple[str, int]]:
        """"uaN" (the net name a schematic uses) -> (side, row)."""
        return {
            pin.replace("ua[", "ua").rstrip("]"): where
            for pin, where in self.pins.rows.items()
        }

    def port_bit(self, net: str) -> int | None:
        """The bit that connects package pin `net` ("ua1") to its bus row,
        or None on a part where that connection is a bond wire and costs no
        bit. Routing a port net has to close this, or the pin is left
        genuinely disconnected and the design measures nothing.
        """
        if not self.pins.switched:
            return None
        return self.pins.bits[f"ua[{net[2:]}]"]

    @cached_property
    def pin_by_row(self) -> dict[tuple[str, int], str]:
        """The same map backwards: which pin sits on a row, so a diagnostic
        can name the pad a net would leak to in the user's own vocabulary.
        """
        return {where: pin for pin, where in self.port_row.items()}

    @cached_property
    def pinned_rows(self) -> set[tuple[str, int]]:
        """Rows an internal net must never use, because a package pin is
        permanently bonded to them. Empty on a part whose pins are switched:
        there, using the row is free and only closing the bit connects the pin.
        """
        if self.pins.switched:
            return set()
        return set(self.pins.rows.values())

    @cached_property
    def tappable_rows(self) -> set[tuple[str, int]]:
        """Every (side, row) that can reach some rail."""
        return {sr for taps in self._rail_taps.values() for sr in taps}

    @cached_property
    def free_rows(self) -> set[tuple[str, int]]:
        """Rows an ordinary internal net may use. A tappable row is free: its
        rail bit is simply left open.
        """
        return self.all_rows - self.pinned_rows

    @cached_property
    def joinable_rows(self) -> list[int]:
        """Row numbers a net spanning both bus sides can use, i.e. free of a
        bond wire on A *and* on B. `cfg_bus_short[row]` spends the same row
        number on both sides, so a net that needs one needs both halves.
        """
        return sorted(
            row for row in self.rows
            if ("A", row) in self.free_rows and ("B", row) in self.free_rows
        )

    # -- pins ---------------------------------------------------------------

    @property
    def ibias_pin(self) -> str:
        return f"ua[{self.ibias_ua}]"

    @cached_property
    def external_pins(self) -> dict[str, tuple[str, int]]:
        """The matrix-reachable analog pins, "ua[1]".."ua[5]" style. The bias
        pin is deliberately absent: it has no switch behind it.
        """
        return dict(self.pins.rows)


# --------------------------------------------------------------------------
# The parts themselves.
# --------------------------------------------------------------------------

# Every device's terminal names -> crosspoint node (SPEC.md Sec 2.12 device
# inventory). The 4 independent FETs expose d/g/s. The diff-pair halves don't
# expose a source terminal (it's shared and has no crosspoint) -- ndiffpair+/
# pdiffpair+ read the netlist's "inp"/"outp" as g/d, ndiffpair-/pdiffpair- read
# "inm"/"outm". The 4 current mirrors expose one terminal, named "out". The
# tail banks have no matrix terminal at all, but still need an entry, since
# route.py's _collect_touches() indexes this by every allocated role.
_SHARED_TERMINALS: dict[str, dict[str, str]] = {
    "nmos_a": {"d": "xpt_nfeta_d", "g": "xpt_nfeta_g", "s": "xpt_nfeta_s"},
    "nmos_b": {"d": "xpt_nfetb_d", "g": "xpt_nfetb_g", "s": "xpt_nfetb_s"},
    "pmos_a": {"d": "xpt_pfeta_d", "g": "xpt_pfeta_g", "s": "xpt_pfeta_s"},
    "pmos_b": {"d": "xpt_pfetb_d", "g": "xpt_pfetb_g", "s": "xpt_pfetb_s"},
    "ndiffpair+": {"g": "xpt_dpn_inp", "d": "xpt_dpn_outp"},
    "ndiffpair-": {"g": "xpt_dpn_inm", "d": "xpt_dpn_outm"},
    "pdiffpair+": {"g": "xpt_dpp_inp", "d": "xpt_dpp_outp"},
    "pdiffpair-": {"g": "xpt_dpp_inm", "d": "xpt_dpp_outm"},
    "nsink_a": {"out": "xpt_mirn_a"},
    "nsink_b": {"out": "xpt_mirn_b"},
    "psource_a": {"out": "xpt_mirp_a"},
    "psource_b": {"out": "xpt_mirp_b"},
    "ntail": {},
    "ptail": {},
}

# Real horizontal bus-wire self-capacitance to substrate, per switch-matrix
# bus row -- the actual physical metal trace running a bus row's full length
# across all 26 columns of the matrix, in farads. This is a genuinely
# different, longer-distance effect than anything device-level: every bus row
# is otherwise a zero-length ideal net in a routed simulation, which
# understates real silicon timing significantly (see the ring-oscillator
# investigation: including this closed real ground, ~93.5MHz -> ~37.62MHz on
# the measured ring-oscillator bitstream against its ~30MHz silicon
# measurement).
#
# Extracted via magic PEX on ttsky-mini-mosbius/mag/asw_matrix.mag (the full
# matrix, not a single column -- `extract all` + `extresist` + `ext2spice
# cthresh=5f rthresh=10`), then summing every real (non-self) capacitor
# touching each bus row's own resistor-connected wire network. Verified
# independently twice (2026-08-22): 4 of 5 rows measured both times agree to
# within <1%. `bus_B[2]` did NOT -- the first measurement (1819.36fF) went
# through the special `asw_col_short` column assuming its per-index row order
# matches the regular (hardware-validated) `asw_col_a`/`asw_col_b` columns'
# `[6,3,5,2,4,1]` pattern; re-checking directly proved that assumption wrong
# for `asw_col_short` (its supposed row-2 node isn't even electrically the
# same net as the real `bus_B[2]` measured through a regular column). The
# value below (922.84fF) comes only from regular columns, using the confirmed
# mapping. `bus_B[5]` couldn't be found as a distinctly-labeled node in either
# extraction run (an ext2spice net-naming quirk specific to that one
# row/column combination, not yet understood) -- using `bus_A[5]`'s value as a
# same-row estimate, flagged here rather than silently guessed.
#
# These are tnt's layout. Andrew Kang's part has its own metal and has not
# been extracted; see its own entry for what it uses instead.
_TNT_BUS_WIRE_CAP: dict[str, float] = {
    "bus_A[1]": 885.65e-15,
    "bus_A[2]": 874.79e-15,
    "bus_A[3]": 864.30e-15,
    "bus_A[4]": 745.87e-15,
    "bus_A[5]": 735.37e-15,
    "bus_A[6]": 724.85e-15,
    "bus_B[1]": 938.25e-15,
    "bus_B[2]": 922.84e-15,
    "bus_B[3]": 901.54e-15,
    "bus_B[4]": 772.52e-15,
    "bus_B[5]": 735.37e-15,  # estimated, see spice.py -- not independently measured
    "bus_B[6]": 746.72e-15,
}


TNT = Chip(
    key="tnt",
    macro="tt_um_tnt_mosbius",
    title="tnt's mini-MOSbius",
    num_bits=tnt_bits.NUM_BITS,
    matrix_bits=tnt_bits.MATRIX_BITS,
    setting_bits=tnt_bits.DEVICE_SETTING_BITS,
    # SPEC.md Sec 2.10 -- VERIFIED external analog pin map, straight from
    # ttsky-mini-mosbius/src/project.v `assign ua[k] = bus_X[n];`. Three on
    # side A and two on side B: CLAUDE.md's trap 1 is that info.yaml's
    # "Bus 1A".."Bus 5A" labels are pin names, not segment identities.
    pins=BondedPins(rows={
        "ua[1]": ("A", 1),
        "ua[2]": ("A", 3),
        "ua[3]": ("A", 5),
        "ua[4]": ("B", 2),
        "ua[5]": ("B", 4),
    }),
    device_terminals={
        **_SHARED_TERMINALS,
        "ota": {
            "inp": "xpt_otan_inp", "outp": "xpt_otan_outp",
            "inm": "xpt_otan_inm", "outm": "xpt_otan_outm",
        },
    },
    bus_wire_cap=_TNT_BUS_WIRE_CAP,
    device_library=DATA_DIR / "mosbius_device_library.spice",
    ibias_ua=0,
    ota_amplifier_bits=(("ctrl_otan_mode", 0),),
    ota_setting_fields={
        "tail": "otan_tail",
        "diode_connect_via_outp": "otan_mode0",
        "diode_connect_via_outm": "otan_mode1",
    },
    absent_terminals={},
    ua_index={f"ua[{k}]": k for k in range(1, 6)},
    needs_reset=False,
)


KANG = Chip(
    key="kang",
    macro="tt_um_mosbius",
    title="Andrew Kang's mini-MOSbius",
    num_bits=kang_bits.NUM_BITS,
    matrix_bits=kang_bits.MATRIX_BITS,
    setting_bits=kang_bits.DEVICE_SETTING_BITS,
    # Every pin is on side A, reached through a `cfg_bus_ext` switch rather
    # than a bond wire, and the sheet's ua1..ua5 sit on rows 1..5 in order.
    # The bits come from the generated table rather than being restated here.
    pins=SwitchedPins(
        rows={f"ua[{k}]": ("A", k) for k in range(1, 6)},
        bits={
            f"ua[{mb.row}]": bit
            for bit, mb in kang_bits.MATRIX_BITS.items()
            if mb.pin_net is not None
        },
    ),
    device_terminals={
        **_SHARED_TERMINALS,
        # One output, not two, and it is the *high-impedance* one.
        #
        # Both parts are the same five-transistor core: one PMOS load is
        # diode-connected and mirrors into the other, whose drain is the
        # output with the gain on it. tnt brings both nodes out to the matrix
        # and lets a config bit choose which is diode-connected; Andrew keeps
        # the diode-connected node internal and brings out only the gain
        # node. The symbol calls that node `outm` -- with tnt's
        # `ctrl_otan_mode[0]` closed, which is what this router emits, `outp`
        # is the diode and `outm` has the gain -- so Andrew's single output is
        # the symbol's `outm`, and its `outp` has no crosspoint here at all.
        "ota": {
            "inp": "xpt_otan_inp", "inm": "xpt_otan_inm",
            "outm": "xpt_otan_out",
        },
    },
    # Not extracted. Andrew's layout has its own metal and nobody has run PEX
    # on it, so these are tnt's numbers reused as a stated estimate: the two
    # matrices are the same shape and the same cell, so the magnitude is
    # right, but no digit here is a measurement of this part.
    bus_wire_cap=_TNT_BUS_WIRE_CAP,
    device_library=DATA_DIR / "kang_device_library.spice",
    ibias_ua=5,
    ota_amplifier_bits=(),
    ota_setting_fields={
        "tail": "otan_tail",
        "output_diode_connected": "otan_diode",
    },
    absent_terminals={
        # Wrapped here rather than at the call site, so the sentence a
        # reader meets is written once, in the place that knows the fact.
        ("ota", "outp"): (
            "This chip's OTA has one output, not two. Both parts are the\n"
            "  same five-transistor amplifier, but tnt's brings the\n"
            "  diode-connected node out to the switch matrix as a second\n"
            "  output, while this one keeps that node inside the block. So\n"
            "  the + output exists on silicon and simply cannot be reached\n"
            "  from outside.\n\n"
            "  To fix: use the - output, which is the one with the gain on\n"
            "  it, and leave the + output unconnected."
        ),
    },
    ua_index={f"ua[{k}]": k - 1 for k in range(1, 6)},
    # Andrew's wrapper has an active-low reset on ui[2]. tnt's design has no
    # reset at all, and driving one that is not there is silent.
    needs_reset=True,
)


CHIPS: dict[str, Chip] = {chip.key: chip for chip in (TNT, KANG)}
CHIP_BY_MACRO: dict[str, Chip] = {chip.macro: chip for chip in CHIPS.values()}

# What the rest of the toolchain assumes when nothing says otherwise. This is
# the part this project was built against and measured on.
DEFAULT_CHIP = TNT


class UnknownChipError(Exception):
    """A macro name that no bit map in this package describes."""


def chip_for_macro(macro: str) -> Chip:
    """Which part a Tiny Tapeout macro name is.

    Raises rather than guessing. A bit map is what gives a chain position its
    meaning, so using the wrong one does not produce a slightly wrong circuit,
    it produces an unrelated one.
    """
    try:
        return CHIP_BY_MACRO[macro]
    except KeyError:
        from mosbius import messages

        known = "\n".join(
            f"    {c.macro}  ({c.title})" for c in CHIP_BY_MACRO.values()
        )
        raise UnknownChipError(
            messages.CHIP_UNKNOWN_MACRO.format(macro=macro, known=known)
        ) from None
