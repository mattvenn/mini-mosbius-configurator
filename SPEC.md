# mini-mosbius-configurator — Specification & Plan

Status: **DRAFT — awaiting sign-off**
Date: 2026-08-19

An xschem library and Python toolchain for [tnt's mini-MOSbius](https://tinytapeout.com/chips/ttsky25a/tt_um_tnt_mosbius)
(`tt_um_tnt_mosbius`, Sky130, TT shuttles). Draw an analog circuit in xschem,
simulate it in ngspice, extract the configuration bitstream from that same
schematic, and load it into the taped-out chip.

Upstream design is vendored as the git submodule `ttsky-mini-mosbius/`
(https://github.com/smunaut/ttsky-mini-mosbius, Apache-2.0). We do not modify it.

---

## 1. Goal

Close the loop that upstream explicitly leaves open. From `ttsky-mini-mosbius/docs/info.md`:

> A configuration bitstream needs to be loaded serially to control all the analog
> switches on-board. **The software suite to generate this is yet to be written.**

There is an existing hand-built web configurator by tnt
(https://people.osmocom.org/tnt/stuff/tt/mosbius.html) that produces a bitstream
from a clickable SVG. **Treat it as a placeholder.** It works — bitstreams it
produces have been loaded into real silicon and behaved — but it is a stopgap:

- It is not connected to simulation. You cannot simulate what you clicked, and you
  cannot click what you simulated.
- Clicking individual switches in a matrix is not a comfortable way to design.
  Users work in tight edit loops, and the configurator does not support that.

**This project supersedes it.** The point of the tool is to make circuits
comfortable to design *in xschem*, then validate them and generate the bitstream:

```
design in xschem  ->  validate (fits? safe?)  ->  generate bitstream  ->  upload
```

That forward path is the product. Everything else in this document exists to serve
it — the xschem schematic becomes the single source of truth for both simulation
and silicon.

### 1.1 Audience — this is a teaching tool

Mini-MOSbius exists so people can **learn analog design**; the Tiny Tapeout
announcement calls it "an FPGA, but for learning analog electronics". The users are
therefore beginners, and that is a design constraint on everything here, not a
documentation afterthought.

**Every message should teach.** When the tool refuses something, a beginner has hit
a property of the hardware they do not know about yet. That moment is the best
opportunity to explain it. So each diagnostic states:

1. **what** happened,
2. **why** the hardware behaves that way,
3. **what to try instead**.

A terse `E1: supply short VAPWR-VGND` is a failure of the tool, not just terse
output — the user learns nothing and is left guessing. Concretely:

```
DANGEROUS — supply short

  VAPWR is joined to VGND through 3 closed switches:

    VAPWR --(bus_pwr[6])--  bus_B[6]
          --(bus_short[6])- bus_A[6]
          --(bus_pwr[3])--  VGND

  This draws unlimited current from the 3.3 V supply straight to ground.
  On real silicon that can damage the chip, so the upload is blocked.

  Why it happened: row 6 is the only row where a VAPWR tap (bus_B[6]) sits
  opposite a VGND tap (bus_A[6]). Closing the short switch on that row ties
  the two supplies together. Rows 1-5 have no such conflict.

  To fix: move this net to another row, or leave row 6's short open.
```

The same standard applies to routing failures, capacity limits, and the watcher's
running commentary. Where the tool can name what the user appears to be building
(§3.8), it should — recognising "this is a current mirror" is itself teaching.

This also raises the value of features that would otherwise be optional polish: the
"looks like" topology recognition in decode, showing which pins a net came out on,
and reporting *why* a device was allocated where it was.

### 1.1 Prior art — the full-size MOSbius flow

The original MOSbius project (Peter Kinget et al., https://mosbius.org) already has
a working design flow for the big chip, and it is close in spirit to this one:

| Piece | What it does |
|---|---|
| [MOSbiusCADFlow](https://github.com/peterkinget/MOSbiusCADFlow) `LTspice/` | Symbol library plus a `MOSbius_chip.asc` template containing the chip's devices; the user rearranges and wires them |
| `MOSbiusTools/` | Python. `cir_to_connections` turns an LTspice `.cir` netlist into `connections.json`; `connections_to_bitstream` turns that into DATA/CLK files |
| [MOSbius_MicroPython_Flow](https://github.com/Jianxun/MOSbius_MicroPython_Flow) | Programs the chip from a Raspberry Pi Pico, consuming the same JSON config |

**What we adopt:**

- **A two-stage pipeline with a human-editable intermediate file.** Their
  `connections.json` sits between schematic and bitstream. That is better than an
  opaque in-memory pipeline: it is inspectable, hand-editable when you want to
  bypass the schematic, and it makes the two halves independently testable. Our
  `SwitchConfig` (§3) becomes a documented file format for the same reason.
- **A template schematic** as a starting point, carrying the supplies, `ibias` and
  port symbols so a new design begins from something that already netlists.
- **Pico/MicroPython as the programming host**, which matches the TT demoboard's
  RP2040 and is already proven on the big chip.

**Where we deliberately differ:**

- **Automatic routing.** Their flow has the user name nodes `BUS01`..`BUS10` by
  hand. We route automatically (§3.2), because "more easily design the circuit" is
  the entire point of this tool and manual bus assignment is the least comfortable
  part of the existing workflow.
- **Real device models.** They simulate against a generic 0.25 µm model, since the
  MOSbius chip is 65 nm thick-oxide and those models are not public. Sky130 is
  open and the submodule contains the actual device schematics, so **we simulate
  the real devices** rather than an approximation.
- **Live validation.** Their flow has no continuous feasibility or safety
  checking; ours does (§3.1, §3.3).

**A lesson taken from them:** the MicroPython flow shipped V1 and V2 with
*incompatible* config formats. Our intermediate file carries a schema version from
the first commit.

Note that no data-level compatibility is possible in either direction — different
chip, different bus count, different device mix. The value is ergonomic
familiarity for people who have used the big MOSbius.

### 1.2 Non-goals

- No changes to `ttsky-mini-mosbius/`. It is a read-only submodule.
- The web configurator is a placeholder this project replaces, not a system we owe
  ongoing compatibility to. We use its SVG as the source of the bit map and remain
  bit-compatible so existing bitstreams stay loadable — but that is a courtesy,
  not a design constraint, and it is **not** an independent oracle for validating
  the map (§6.1).
- No layout, DRC, LVS, or re-tapeout work.
- No automatic circuit synthesis. The user decides the topology; we route it onto
  the fixed switch matrix and tell them if it does not fit.

---

## 2. Verified hardware model

Everything in this section was derived from the submodule sources and
cross-checked against the web configurator. Confidence is noted per item.

### 2.1 Configuration chain — VERIFIED

`ttsky-mini-mosbius/src/ctrl_top.v` defines a **192-bit shift register**,
`ctrl_out[191:0]`, built from a chain of `ctrl_block` instances.

Within one `ctrl_block` (`src/ctrl_block.v`):

```
shift[0] = data_in
shift[N:1] = N x dfrtp_1, clocked on clk, async reset on rst_n
ctrl_out[N-1:0] = shift[N:1] & enable     // and2_2 mask
data_out = shift[N]
```

Consequences that the tooling depends on:

- **`enable` gates the outputs combinationally.** All switches are forced open
  while `enable` is low, regardless of shift register contents. This makes
  glitch-free loading possible: hold `enable` low, shift 192 bits, raise `enable`.
- **`rst_n` asynchronously clears the chain**, i.e. all switches open.
- Data flows from `data_in` toward `ctrl_out[191]`, so the **first bit clocked in
  ends up in `ctrl_out[191]`** and the last in `ctrl_out[0]`.
  **Transmit order is MSB-first: bit 191 first, bit 0 last.**

### 2.2 Chain composition — VERIFIED

| Bits | Block | `ctrl_top.v` instance | Width |
|---|---|---|---|
| 0–155 | Analog switch matrix, 26 columns x 6 | `blk_I` generate loop | 26 x 6 |
| 156–161 | Dual PMOS | `blk_pmos_dual_I` | 6 |
| 162–167 | PMOS current mirror | `blk_pmos_cm_I` | 6 |
| 168–171 | PMOS differential pair | `blk_pmos_dp_I` | 4 |
| 172–175 | NMOS differential pair | `blk_nmos_dp_I` | 4 |
| 176–183 | NMOS current mirror | `blk_nmos_cm_I` | 8 |
| 184–189 | Dual NMOS | `blk_nmos_dual_I` | 6 |
| 190–191 | OTA | `blk_nmos_ota_I` | 2 |

Column *c* of the matrix owns `ctrl_out[6*c+5 : 6*c]`.

### 2.3 Physical column order — VERIFIED

`mag/asw_matrix.mag` instantiates 26 columns on a 1840-unit X pitch. Sorting the
`transform` X offsets gives the chain order (position = X/1840):

```
 0 asw_col_short_0     7 asw_col_b_2      14 asw_col_b_5     21 asw_col_b_8
 1 asw_col_a_0         8 asw_col_b_3      15 asw_col_ab_2    22 asw_col_b_9
 2 asw_col_b_0         9 asw_col_a_3      16 asw_col_a_6     23 asw_col_b_10
 3 asw_col_ab_0       10 asw_col_a_4      17 asw_col_b_6     24 asw_col_a_9
 4 asw_col_a_1        11 asw_col_b_4      18 asw_col_a_7     25 asw_col_a_10
 5 asw_col_a_2        12 asw_col_ab_1     19 asw_col_b_7
 6 asw_col_b_1        13 asw_col_a_5      20 asw_col_a_8
```

Each `asw_col_*` wraps `asw_col_base`, which is one `asw_col_ctrl` (the 6-bit
`ctrl_block`) plus `array 0 0 3680 0 5 4622` of `tt_asw_3v3` — i.e. **6 analog
switches per column, one per bus row**.

**Cross-check:** position 0 is the *short* column (it shorts bus A to bus B on
each row). Its bits are therefore 0–5. The web configurator assigns the six
short-column toggles the bits `0, 2, 4, 1, 3, 5`. This independently confirms
both that column 0 is `asw_col_short` **and** that the configurator's bit
numbering is identical to `ctrl_out[]` indexing.

### 2.4 The 192-bit budget closes exactly — VERIFIED

`xschem/mosbius.sym` exposes every configuration bit as a named digital input
pin. Summing the pin widths:

| Group | Pins | Bits |
|---|---|---|
| `cfga_*` (bus A side switches) | 14 pins | 75 |
| `cfgb_*` (bus B side switches) | 14 pins | 75 |
| `cfg_bus_short[6:1]` | 1 | 6 |
| `cfg_bus_pwr[6:1]` | 1 | 6 |
| `ctrl_*` (device settings) | 18 pins | 30 |
| **Total** | **48** | **192** |

192 config pins == 192 shift register bits, **with no bits left over and none
missing**. Plus 6 non-config pins: `VAPWR`, `VDPWR`, `VGND`, `ibias`,
`bus_A[6:1]`, `bus_B[6:1]`.

Note that `cfg_bus_pwr` (which ties buses to `VAPWR`/`VGND`) is *not* part of
`asw_matrix.mag` — its 6 bits live in the differential-pair control blocks
(within bits 168–175), presumably because those blocks sit next to the power
rails in the layout. The configurator agrees: it places bus-power toggles at bits
168, 169, 170 (VAPWR) and 172, 173, 174 (VGND).

Configurator toggle/cycler accounting also closes exactly:
156 matrix toggles + 14 device toggles + 22 cycler bits = 192.

### 2.5 Bitstream encoding — VERIFIED

- 192 bits, presented as **48 hex characters**, big-endian: leftmost hex nibble
  holds bits 191–188. (The configurator uses
  `bitmask.toString(16).padStart(48,'0')` over a BigInt where bit *n* is
  `ctrl_out[n]`.)
- Serial transmission is MSB-first (bit 191 first), per §2.1.

### 2.6 Chip pinout — VERIFIED (`info.yaml`)

| Pin | Function |
|---|---|
| `ui[0]` | `data_in` |
| `ui[1]` | `enable` |
| `uo[0]` | `data_out` (chain output, for readback) |
| `ua[0]` | Reference bias (`ibias`) |
| `ua[1..5]` | Bus segments — **not** `bus_A[1..5]`; see §2.10 for the real mapping |
| `clk` | Shift clock (TT harness) |
| `rst_n` | Chain reset, active low (TT harness) |

`clock_hz: 0` — the shift clock is supplied by the host, at whatever rate it
likes. 3.3V analog domain (`uses_3v3: true`).

### 2.7 Row-within-column mapping — VERIFIED

Parsing the configurator SVG geometrically (accumulating nested `transform`s to
get absolute coordinates for every `data-mosbius-toggle` circle) shows all 156
matrix bits fall into leaf groups of 6 (a full column) or 3 (half of an `ab`
column). **Every full column has the identical row pattern**, top to bottom:

```
row 1 2 3 4 5 6  ->  bit offset  0 2 4 1 3 5
```

and `ab` columns split **even offsets (0,2,4) to the A side, odd (1,3,5) to B**.
The three `ab` columns are bases 18, 72 and 90 — exactly the three signal pairs
whose `cfg` pins are 3 bits wide (`dpn_in`, `dpp_in`, `otan_in`).

Drawing row == bus index, confirmed **independently** via `cfg_bus_pwr`. The
netlist says:

| `cfg_bus_pwr[n]` | connects | to |
|---|---|---|
| 6 | `bus_B[6]` | VAPWR |
| 5 | `bus_A[4]` | VAPWR |
| 4 | `bus_B[1]` | VAPWR |
| 3 | `bus_A[6]` | VGND |
| 2 | `bus_B[5]` | VGND |
| 1 | `bus_A[2]` | VGND |

The configurator places its VAPWR toggles on rows 1B, 4A, 6B and its VGND toggles
on rows 2A, 5B, 6A. Those are the same six (side, index) pairs. Two unrelated
sources, exact agreement.

### 2.8 Switch connectivity — VERIFIED

`xschem -n mosbius.sch` (run in IIC-OSIC-TOOLS) yields all **162** switch
instances with full connectivity, in the uniform form:

```
x13[5] VGND VDPWR VAPWR cfga_otan_outp[5] xpt_otan_outp bus_A[5] tt_asw_3v3
       ^VGND ^VDPWR ^VAPWR ^ctrl           ^mod          ^bus
```

i.e. `cfg<side>_<signal>[n]` closes a switch between crosspoint node
`xpt_<signal>` and `bus_<side>[n]`. 30 distinct `cfg` signals covering all 162
switches. This is a complete, machine-readable description of the matrix.

### 2.9 The one remaining extraction step

Everything above pins down *bit -> (column base, bus, side)* and separately
*cfg signal -> (crosspoint node, bus, side)*. What remains is the **join**:
which of the 26 column bases carries which of the 30 `cfg` signals.

This is a finite labelling problem over 30 items, heavily over-constrained by:

- **Side** — X sign in the drawing gives A vs B.
- **Width** — only three signal pairs are 3 bits wide, and only three columns are;
  they must correspond (bases 18, 72, 90).
- **Device grouping** — each leaf group in the SVG sits inside a parent group that
  draws one device symbol, so columns cluster by device.
- **Anchors** — the configurator's cycler bits already tie device blocks to known
  bit ranges (e.g. bits 156/157 set PMOS-dual width), fixing which device is which.
- **Count** — 26 columns, 30 signals, 3 pairs sharing `ab` columns, plus short:
  the arithmetic closes only one way.

It is a mechanical extraction against sources we already hold, with a definite
answer. It is not a design unknown: **the chip is fabricated, so this mapping is a
fixed fact, and every input needed to recover it is in the submodule and the
configurator.**

### 2.10 A/B partition — VERIFIED

Every crosspoint node reaches **exactly one bus side**. The `a` device halves
(`nfeta`, `pfeta`, `mirn_a`, `mirp_a`, `dpn_inp/outp`, `dpp_inp/outp`,
`otan_inp/outp`) can only reach `bus_A[1..6]`; the `b` halves only `bus_B[1..6]`.

So the array is **12 independent nets**, not 6, and `cfg_bus_short[n]` is the only
way to join `bus_A[n]` to `bus_B[n]`. Connecting an A-side device terminal to a
B-side one *requires* spending a short switch on some row. The router must model
this; it is the main capacity constraint on the matrix.

**External access — VERIFIED from the configurator SVG geometry.** The five
analog pins straddle *both* sides, three on A and two on B. Note that the
`info.yaml` labels ("Bus 1A".."Bus 5A") are sequential pin names, not segment
identities, and do **not** mean `bus_A[1..5]`:

| Pin | Segment |
|---|---|
| `ua[1]` | `bus_A[1]` |
| `ua[2]` | `bus_A[3]` |
| `ua[3]` | `bus_A[5]` |
| `ua[4]` | `bus_B[2]` |
| `ua[5]` | `bus_B[4]` |

**Segment roles.** Combining that with `cfg_bus_pwr` gives a clean partition of
all 12 segments:

| | A side | B side |
|---|---|---|
| Externally pinned | 1, 3, 5 | 2, 4 |
| VAPWR-tappable | 4 | 1, 6 |
| VGND-tappable | 2, 6 | 5 |
| Unencumbered | — | 3 |

The pinned set and the rail-tappable set are **disjoint**: 5 + 6 + 1 = 12 with no
overlap. A design therefore never has to trade an external probe against a power
connection — they use different rows. On the A side the split is exactly by
parity (odd rows pinned, even rows rail).

Combined with §2.10's A/B partition, this means **which device the router picks
determines which pins can observe it**: an A-side terminal can reach 3 external
pins, a B-side terminal 2, and crossing sides costs a `cfg_bus_short`. See §2.12
for the full inventory of what the router may choose between.

### 2.11 Device settings — VERIFIED

Devices are not fixed: several are **banks of unit devices switched in parallel**.
All 11 configurator cyclers use the same encoding,

```
n = step * (1 + b_lsb + 2 * b_msb)
```

with `step = 1` for widths and mirror ratios, and `step = 2` for differential-pair
and OTA tails (a pair is two matched devices, so it counts in 2s).

| Setting | Bits (lsb, msb) | Range |
|---|---|---|
| `pfeta` width | 157, 156 | 1–4 |
| `pfetb` width | 161, 160 | 1–4 |
| `nfeta` width | 189, 188 | 1–4 |
| `nfetb` width | 185, 184 | 1–4 |
| `mirp_a` ratio | 166, 167 | 1–4 |
| `mirp_b` ratio | 164, 165 | 1–4 |
| `mirn_a` ratio | 178, 179 | 1–4 |
| `mirn_b` ratio | 176, 177 | 1–4 |
| `dpp` tail | 162, 163 | 2–8 |
| `dpn` tail | 180, 181 | 2–8 |
| `otan` tail | 182, 183 | 2–8 |

Plus 14 single-bit toggles: four FET source ties (158, 159, 186, 187), two
diff-pair source ties, six `cfg_bus_pwr`, and OTA mode (190, 191).

**Caveat — block names in `ctrl_top.v` indicate physical placement, not logical
function.** Bits 162/163 sit in `blk_pmos_cm` but drive the *PMOS diff-pair tail*;
180/181 and 182/183 sit in `blk_nmos_cm` but drive the `dpn` and OTA tails; and
`cfg_bus_pwr` lives inside the diff-pair blocks (§2.4). Bit meanings must be taken
from the configurator geometry, never inferred from RTL block names.

### 2.12 Device inventory — 7 NMOS, 7 PMOS, OTA (5)

Counted as transistors drawn in the configurator, which is how a designer thinks
about the chip. (Nine *addressable blocks* is a different, less useful count.)

| # | Transistor | Block | Matrix terminals | Settings |
|---|---|---|---|---|
| N1 | `nfeta` | NMOS dual | d, g, s (A) | width 1–4, source→VGND |
| N2 | `nfetb` | NMOS dual | d, g, s (B) | width 1–4, source→VGND |
| N3 | `dpn+` | NMOS diff pair | g=`inp`, d=`outp` (A) | source shared with N4 |
| N4 | `dpn−` | NMOS diff pair | g=`inm`, d=`outm` (B) | source shared with N3 |
| N5 | `dpn` tail | NMOS diff pair | **none — internal** | tail 2–8, or tie shared source to VGND |
| N6 | `mirn_a` | NMOS mirror | 1 terminal (A) | 1–4 |
| N7 | `mirn_b` | NMOS mirror | 1 terminal (B) | 1–4 |
| P1 | `pfeta` | PMOS dual | s, g, d (A) | width 1–4, source→VAPWR |
| P2 | `pfetb` | PMOS dual | s, g, d (B) | width 1–4, source→VAPWR |
| P3 | `dpp+` | PMOS diff pair | g=`inp`, d=`outp` (A) | source shared with P4 |
| P4 | `dpp−` | PMOS diff pair | g=`inm`, d=`outm` (B) | source shared with P3 |
| P5 | `dpp` tail | PMOS diff pair | **none — internal** | tail 2–8, or tie shared source to VAPWR |
| P6 | `mirp_a` | PMOS mirror | 1 terminal (A) | 1–4 |
| P7 | `mirp_b` | PMOS mirror | 1 terminal (B) | 1–4 |
| — | `otan` | OTA — **5 transistors, used as a block** | `inp`, `outp` (A); `inm`, `outm` (B) | tail 2–8, mode (2 bits) |

Plus infrastructure, not transistors: 6 `bus_short` (join `bus_A[n]`↔`bus_B[n]`) and
6 `bus_pwr` taps — VAPWR on B1, A4, B6; VGND on A2, B5, A6.

**Cross-check.** Configurator toggles per block: bus+power 12, each diff pair 19,
each dual 38, each mirror 12, OTA 20 — totalling **170**, exactly the toggle count
in the SVG. Terminals: 28 crosspoints across the matrix.

Notes for the router:

- **Eight FETs are freely usable singly** (N1–N4, P1–P4). The pair halves share only
  a source, so with the tail tied to a rail each is an ordinary common-source FET —
  which is how the blog's 6-transistor SR latch fits.
- **Tails (N5, P5) have no matrix terminals.** They are configurable but not
  wireable; they either set a tail current or are bypassed by the source tie.
- **Mirror legs (N6, N7, P6, P7) are current sinks/sources, not general FETs** —
  gates and sources are tied internally. The NMOS mirror also generates an internal
  `ibias_p` biasing the PMOS mirror and `dpp`.
- **Pair and OTA inputs reach only bus rows 1–3.** With §2.10's pin map, a `+`
  input can reach `ua[1]` or `ua[2]`; a `−` input only `ua[4]` or free `bus_B[3]`.
- **Width is parallel unit count** (base + 1x + 2x), never length.
- Bias chain: `ua[0]` → NMOS mirror → `ibias_p` → PMOS mirror; `ibias` also biases
  N5 and the OTA tail, `ibias_p` biases P5.

## 3. Architecture

Decision (agreed): **schematic-driven**. One xschem schematic is the source of
truth; simulation and silicon are both generated from it, so they cannot diverge.

```
        examples/inverter/inverter.sch          <-- user draws this
                     ^                          (mosbius watch re-runs
                     |                           route+check on every
                     |                           netlist write, §3.3)
                     |
                     |  xschem -n  (netlist)
                     v
              inverter.spice
                     |
                     |  mosbius.netlist  (parse)
                     v
        MosbiusDesign  (nets, device settings)   <-- canonical in-memory model
                     |
        +------------+-------------+
        |                          |
   mosbius.route              mosbius.route
        |                          |
        v                          v
  SwitchConfig (192 bits)    SwitchConfig (192 bits)
        |                          |
   mosbius.spice              mosbius.bitstream
        |                          |
        v                          v
  config.spice                48-hex bitstream
  (.param / V sources           |
   on mosbius.sym pins)         |  mosbius.program
        |                       v
        v                  TT demoboard (RP2040)
     ngspice                ui[0]/ui[1] + clk
        |                       |
        v                       v
   waveforms              readback via uo[0]
```

The **same** `SwitchConfig` object feeds both the SPICE testbench and the
hardware programmer. That is the property that makes sim-vs-silicon divergence
structurally impossible.

### 3.1 Circuit safety checker

A mandatory gate that runs on a `SwitchConfig` before simulation and, more
importantly, **before any bitstream is uploaded to silicon**. Because it operates
on a `SwitchConfig`, it also works on a bitstream imported from anywhere —
including one pasted from tnt's web configurator — which makes it useful
independently of the rest of this toolchain.

**Model.** Build an undirected graph: nodes are the 12 bus segments, the 28
crosspoint nodes, the rails (VAPWR, VGND, VDPWR), `ibias`, and the external pins
`ua[0..5]`. Edges are the switches closed by the config, plus device-internal
connections implied by the `ctrl_*_source` bits. Then run connectivity queries.

**Checks.**

| ID | Severity | Condition |
|---|---|---|
| E1 | **ERROR** | VAPWR and VGND in the same connected component — a dead short across the supply |
| E2 | **ERROR** | `ibias` shorted to either rail |
| E3 | **ERROR** | An externally driven `ua[]` pin in the same component as a rail — the demoboard drives into a hard short |
| E4 | **ERROR** | Two `ua[]` pins both externally driven and shorted together |
| W1 | WARN | A device's own drain and source tied to the same net (shorts out the channel) |
| W2 | WARN | A crosspoint used by the design with no DC path to any rail (floating node) |
| W3 | WARN | A device half enabled but with a terminal left unconnected |
| I1 | INFO | A bus segment with fewer than two connections (does nothing) |

**E1 is not hypothetical.** `bus_A[6]` can be tied to VGND and `bus_B[6]` to
VAPWR, and `cfg_bus_short[6]` joins exactly those two. **Three bits** produce a
supply short. Similarly any A-side crosspoint closed onto both `bus_A[2]` (VGND)
and `bus_A[4]` (VAPWR) shorts the supply through two switches. These are easy to
hit by a single mis-set bit, which is precisely why the check must be automatic
rather than a matter of care.

**Behaviour.** Errors block the upload. `program.py` requires an explicit
`--force` to proceed past an error, and prints the offending net path — not just
"short detected" but the actual chain of switches forming it, so it can be fixed.
Warnings print but do not block.

### 3.1b Two-level schematic structure

Designs are drawn at **two levels**, which makes the chip boundary explicit and
enforced rather than a matter of discipline.

**Level 1 — the design block.** A `minimosbius` schematic whose **port list is
fixed** to what the chip actually brings out:

```
ibias (ua[0])   ua[1]  ua[2]  ua[3]  ua[4]  ua[5]
VAPWR (3.3)     VDPWR (1.8)   VGND
```

Inside it you place generic devices (§3.4) and wire your circuit. You cannot
accidentally connect something "off chip": the only way out is through a port.

**Level 2 — the testbench.** Ordinary xschem. It instantiates the design block and
adds voltage sources, the `ibias` current source, loads and analysis statements —
exactly as upstream's 16 `tb_*.sch` files already do for `mosbius.sym`. No new
concepts, and stimulus lives where a circuit designer expects it.

**Why the fixed port list matters.** It is the interface both implementations
share:

```
                    ports: ibias ua[1..5] VAPWR VDPWR VGND
                                    |
        +---------------------------+---------------------------+
        |                                                       |
   design.sch                                          generated implementation
   generic devices,                                     mosbius.sym with every
   ideal wiring                                         cfg pin tied per the config
        |                                                       |
   "what I meant"                                        "what the chip does"
```

The testbench binds to the port list, so it is **unchanged as you iterate** — only
the block's internals move.

**This also gives a free debugging tool.** Simulating both implementations behind
the same ports and diffing the results separates "my circuit is wrong" from "the
switch matrix is loading it": the ideal version has no transmission-gate
resistance, the routed one carries all 14 transistors per switch. When silicon
disagrees with intent, that diff says which half to look at.

**And it replaces the port annotation in §3.2.** Nets reaching a port *are* the
nets needing a pinned segment — no special marking, it falls out of the schematic's
own interface.

### 3.2 Automatic routing

The user draws an ordinary circuit. The router assigns every net to one of the 12
bus segments and chooses which half of each device pair to use. There is no
manual bus placement and no bus symbols in the schematic.

Inputs to the decision, all derived in §2:

- A net may only sit on a segment its devices can reach (§2.10 A/B partition).
- Joining an A segment to a B one costs one of the 6 `cfg_bus_short` rows.
- Rail connections must land on a rail-tappable segment, or use the device's own
  `ctrl_*_source` tie where one exists (cheaper — no bus consumed).
- **Nets reaching one of the design block's ports must land on a pinned segment**
  (§3.1b). This needs no annotation — the block's port list is fixed to the chip's
  real pins, so connecting a net to `ua[2]` *is* the request.

Where several assignments are legal, prefer fewest switches in series (each closed
switch adds resistance and capacitance in the signal path).

If no assignment exists, the router explains the shortfall in the terms of §1.1 —
what ran out, why the hardware is built that way, and what might be changed:

```
DOESN'T FIT — not enough NMOS with independent sources

  Your circuit needs 3 NMOS whose sources go to different nets:
    M1.s -> vout     M2.s -> VGND     M3.s -> vbias

  The chip has 4 NMOS, but only 2 of them (nfeta, nfetb) have a source you can
  route anywhere. The other 2 are the halves of a differential pair: they share
  a single source node, so they are only usable together, by two transistors
  that want a common source.

  Currently placed: M1 -> nfeta, M2 -> nfetb. M3 has nowhere to go.

  Ideas:
    - If two of these could share a source, they would fit the pair.
    - A programmable current sink (mosbius_nsink) can often replace a
      source-degenerated NMOS.
```

### 3.2b Routing is sticky

**A design's routing is part of the design, not a fresh computation.** Once a
circuit has been routed, that routing persists in its config file (§3.6) and is
**reused** on every later run. The router does not re-solve a design that has not
changed.

This is not test hygiene — it is correctness for analog. Two logically identical
routings are not electrically identical: they put different numbers of
transmission gates in series with a signal, on different bus segments, with
different parasitic loading. Re-routing a working circuit changes its behaviour.

The failure mode this avoids is severe for the audience in §1.1. A beginner has a
design that works on silicon. Months later the router has improved. They open the
tool, change nothing, and the circuit behaves differently — with no edit to point
at as the cause. That teaches the opposite of cause and effect.

**Rules:**

- If the circuit is unchanged, **reuse the stored routing verbatim**. No re-solve,
  no diff, nothing to accept.
- If the circuit changed, **re-route minimally**: keep every existing assignment
  that is still valid and only place what actually moved. Tweaking one transistor's
  width must not relocate unrelated nets, so the rest of the circuit's parasitic
  environment holds still and the behaviour change is attributable to the edit.
- `--reroute` explicitly asks for a fresh solve, and reports what moved and why.
- The config records the router version. A newer router **tells** you a better
  routing exists; it never imposes one.

This also dissolves the snapshot-acceptance problem entirely (§6.1): routings do
not spontaneously change, so there is no bulk diff to rubber-stamp.

### 3.3 Watch mode

`mosbius watch` monitors the netlist file that xschem writes. The user works in
xschem and presses its netlist button whenever they want feedback; the watcher
notices the file change and immediately re-runs parse -> route -> check, printing
a short report.

This turns both the router and the safety checker (§3.1) into **live design
feedback** rather than a gate encountered at the end. The two failure classes the
user cares about — *impossible* (does not fit the matrix) and *dangerous* (shorts,
contention) — are surfaced while the circuit is still being drawn.

Report sketch:

```
mosbius watch — inverter.spice          12:04:31   OK

  net      segment      pin      via
  vin      bus_A[1]     ua[1]    nfeta.g pfeta.g
  vout     bus_A[3]     ua[2]    nfeta.d pfeta.d
  vss      —            —        nfeta.s (ctrl_nfeta_source)
  vdd      —            —        pfeta.s (ctrl_pfeta_source)

  4 shorts free · 9 bus segments free · 190 bits clear
```

and on a problem:

```
mosbius watch — inverter.spice          12:06:02   DANGEROUS

  E1  supply short: VAPWR — VGND
      bus_B[6] --(cfg_bus_pwr[6])-- VAPWR
      bus_B[6] --(cfg_bus_short[6])-- bus_A[6]
      bus_A[6] --(cfg_bus_pwr[3])-- VGND
      upload blocked
```

Requirements: report within about a second of the netlist being written, so it
feels attached to the edit. The netlist lives on the shared mount, so the
host-side Python watcher sees writes from xschem running in the container.

### 3.4 Symbol library and device allocation

The library offers **generic parts**, not named hardware devices:

| Symbol | Properties | Maps to |
|---|---|---|
| `mosbius_nmos` | `w` = 1–4 | `nfeta`, `nfetb`, `dpn+`, `dpn−` |
| `mosbius_pmos` | `w` = 1–4 | `pfeta`, `pfetb`, `dpp+`, `dpp−` |
| `mosbius_nsink` | `ratio` = 1–4 | `mirn_a`, `mirn_b` |
| `mosbius_psource` | `ratio` = 1–4 | `mirp_a`, `mirp_b` |
| `mosbius_ota` | `tail` = 2–8, `mode` | `otan` (one only) |

`w` sets parallel unit count. **Only width is adjustable — the hardware has no
length control.**

**Allocation rule.** Independent FETs are the flexible resource; differential-pair
halves are usable only when their sources are common. So the router **spends the
constrained resource first**:

1. Find sets of same-type FETs in the user's circuit that share a source net.
2. Map those preferentially onto a differential pair (`dpn+`/`dpn−`, `dpp+`/`dpp−`),
   which physically shares a source anyway.
3. Map FETs needing independent sources onto `nfeta`/`nfetb` / `pfeta`/`pfetb`.
4. Choose A vs B side to satisfy any external-port requirements (§3.2).

Capacity is therefore 4 NMOS and 4 PMOS, but only if the circuit's source-sharing
structure matches the hardware's. A design wanting 4 NMOS with four *independent*
sources does not fit, and the watcher says so in those terms rather than just
"failed".

Drawing a `mosbius_ota` twice, or more FETs than exist, is reported the same way.

**A template, not a fixed chip schematic.** MOSbius ships `MOSbius_chip.asc`
containing every device, which the user rearranges — that makes over-allocation
structurally impossible, but it also means you draw the chip you have rather than
the circuit you want. We ship `template.sch` carrying only the harness (supplies,
`ibias`, port symbols) so a new design netlists immediately, and rely on the
watcher (§3.3) to report over-allocation in the terms the user is thinking in
("needs 3 NMOS with independent sources; the chip has 2").

### 3.4b Bias current

`ua[0]` / `ibias` is a **current input**, not a voltage: it feeds the
diode-connected reference leg of `mirror_n`, which then generates `ibias_p` for the
PMOS side plus the programmable mirror outputs. Upstream's testbenches drive it
with 100 µA. Every mirror ratio and every differential-pair and OTA tail scales
with it, so it sets the operating point of the whole analog half.

**The new TT demoboard has a programmable current source driven by its Raspberry
Pi microcontroller** — the same host that loads the bitstream. So the bias is under
software control, not an external resistor.

Consequences:

- **`ibias` belongs in the config file** (§3.6), alongside the switch settings. A
  design is only reproducible if its bias point travels with it.
- **`program.py` sets both**: bias current, then bitstream.
- **Simulation uses the same value**, taken from the same field, so sim and
  silicon share an operating point by construction rather than by the user
  remembering to match them.
- Sweeping `ibias` becomes a first-class experiment — the same circuit at several
  bias points, without touching the bitstream.

### 3.5 Programming sequence

Default load — 192 clocks:

```
0. set ibias                   programmable current source (§3.4b)
1. enable (ui[1]) low          all switches forced open
2. pulse rst_n                 known state; --no-reset to skip
3. shift 192 bits, MSB first   bit 191 first, bit 0 last (§2.5)
4. enable high                 whole configuration applies at once
```

**Step 1 is a safety requirement, not a convention.** `ctrl_block` masks its
outputs with `enable` combinationally (§2.1), so with `enable` high the
partially-shifted chain would drive the matrix on every clock edge — walking
through 192 arbitrary intermediate configurations. Given how few bits it takes to
short the supply (§3.1, E1), that must never happen. `program.py` has no mode that
shifts with `enable` high.

Optional `--verify` — debug only, 384 clocks:

```
3a. shift 192 bits of config            (pass 1, ignore data_out)
3b. shift the same 192 bits again,      captured stream must equal the config;
    capturing uo[0]                     chain ends up holding the config
```

The double shift is needed because the chain is a plain shift register — `uo[0]`
is its far end, so reading it out destroys the contents. A single pass would only
report what was loaded *previously*. Off by default.

### 3.6 The intermediate config file

Following the MOSbius flow's `connections.json` (§1.1), `SwitchConfig` is not just
an in-memory object but a **documented, versioned file format** sitting between
schematic and bitstream:

```
design.sch  --netlist-->  design.spice  --route-->  design.mosbius.json  --pack-->  48 hex
                                                            |
                                                            +--spice--> config for ngspice
                                                            +--check--> safety report
                                                            +--program--> chip
```

Why it earns its place:

- **Inspectable.** When a design does not behave, you can read what the router
  actually decided instead of guessing from 48 hex characters.
- **Hand-editable.** You can bypass the schematic entirely for a quick experiment,
  exactly as MOSbius users hand-write `connections.json`.
- **Testable.** The router and the packer become independently testable halves.
- **It is the committed implementation.** Because routing is sticky (§3.2b), this
  file is not a build artifact to regenerate — it is the design's routed form, and
  it doubles as the regression fixture (§6.1). One format, not two.

It carries `"schema": 1` from the first commit — the MicroPython flow's V1/V2
incompatibility (§1.1) is a mistake worth not repeating.

### 3.7 Why the `mosbius.sym` pin interface is the right seam

`mosbius.sym` already exposes all 192 config bits as named input pins (§2.4). So
the simulation path needs **no behavioural model of the shift register at all** —
we simply drive the `cfg*`/`ctrl*` pins with 0V or VDPWR from a generated
include file. This is faster to simulate and far less error-prone than shifting
192 bits through a digital model.

The shift register only appears on the hardware path, where it is a trivially
simple serialiser.

---

### 3.8 Bitstream decoding — circuit extraction

A supporting capability, not the product — but a useful one. With the placeholder
configurator, understanding an existing bitstream means loading it and reading the
closed switches off the SVG by eye, reconstructing the circuit in your head. That
is slow and error-prone, and it is the reverse of the main flow.

Decoding is **deterministic and much easier than routing**. Where the forward
direction is a search problem, the reverse is plain graph connectivity:

```
1. bits -> switch states                     (bit map, M0)
2. build graph:
     cfg<side>_<sig>[n]  -> edge (xpt_<sig>, bus_<side>[n])
     cfg_bus_short[n]    -> edge (bus_A[n], bus_B[n])
     cfg_bus_pwr[n]      -> edge (bus_?[m], VAPWR | VGND)
     ctrl_<dev>_source   -> edge (xpt_<dev>_s, rail)
     ua[k]               == its bus segment  (§2.10)
3. connected components  -> the electrical nets
4. name nets: any component touching VGND/VAPWR/ua[k] takes that name,
   the rest get net1, net2, ...
5. per device, report which net each terminal sits on, plus its settings
6. drop devices whose terminals are all isolated
```

Output forms:

- **Readable summary** — the direct answer to "what circuit is this?"
- **SPICE subckt** — feeds straight into the existing simulation path, so a
  bitstream from anywhere becomes immediately simulatable.
- **Generated `.sch`** — an xschem schematic. With at most 9 devices, automatic
  placement is easy, and this closes the loop: load a bitstream, get a schematic,
  edit it, emit a new bitstream.

```
$ mosbius decode 0000000000a4000000000000000000000000000c00000082

  Devices in use
    nfeta  w=2   d=net1   g=net2   s=VGND
    pfeta  w=4   d=net1   g=net2   s=VAPWR

  Nets
    net1   ua[2]  (bus_A[3])   nfeta.d  pfeta.d
    net2   ua[1]  (bus_A[1])   nfeta.g  pfeta.g

  Looks like: CMOS inverter   in=ua[1]  out=ua[2]
```

The final "looks like" line is a stretch goal — pattern-matching a handful of
known topologies (inverter, latch, mirror, common-source stage). Useful, but the
net/device table is the substance.

**Decoding also validates the bit map better than anything else in §6.1.** Decode
a bitstream that is known to work on silicon; if the expected circuit comes out,
the map is confirmed against physical reality rather than against the SVG it was
derived from. That breaks the circularity problem outright.

## 4. Deliverables

```
mini-mosbius-configurator/
├── SPEC.md                     this document
├── README.md
├── ttsky-mini-mosbius/         submodule (upstream, read-only)
├── mosbius/                    Python package
│   ├── bitmap.py               canonical bit -> (column, row, signal) table
│   ├── model.py                MosbiusDesign, SwitchConfig, device settings
│   ├── netlist.py              xschem/SPICE netlist parser
│   ├── route.py                design -> switch settings; over-constraint checks
│   ├── check.py                circuit safety checker (§3.1) — shorts, contention
│   ├── watch.py                live netlist watcher (§3.3)
│   ├── bitstream.py            pack/unpack 192 bits <-> 48 hex
│   ├── decode.py               bitstream -> nets -> devices (§3.8)
│   ├── schgen.py               decoded circuit -> xschem .sch (§3.8)
│   ├── spice.py                emit ngspice include driving mosbius.sym pins
│   └── program.py              demoboard load + readback verify
├── xschem/mosbius_lib/         the xschem library
│   ├── mosbius_nmos.sym        generic devices (§3.4), w = 1..4
│   ├── mosbius_pmos.sym        ...
│   ├── minimosbius_template.sch  design block: fixed port list, empty inside
│   └── tb_template.sch           testbench: sources, ibias, analysis (§3.1b)
├── tests/
│   ├── test_bitstream.py
│   ├── test_bitmap.py          structural cross-validation (§6.1)
│   ├── test_check.py           incl. known-bad configs that must be rejected
│   └── designs/                committed configs from real designs (§6.1)
├── examples/
│   ├── inverter/               reproduces the TT blog post's inverter
│   └── sr_latch/               reproduces the TT blog post's SR latch
└── tools/
    └── extract_bitmap.py       regenerates bitmap.py from the submodule
```

### 4.1 Environment

Target is the **already-installed** `~/IIC-OSIC-TOOLS` Docker setup
(`hpretl/iic-osic-tools:latest`), which provides xschem, ngspice, magic and the
sky130A PDK. Verified on xschem 3.4.8RC: netlisting `mosbius.sch` under `latest`
and under the pinned `2025.07` gives byte-identical switch connectivity and device
instances, so the bit map does not depend on the image version. Nothing is installed natively on this Mac, and we will not try to
change that.

- `xschem` and `ngspice` run inside the container via `start_shell.sh`.
- The Python package runs **on the host** (it needs USB serial access to the
  demoboard, which is awkward from Docker on macOS) and has no EDA dependencies.
- A thin `tools/run_sim.sh` wrapper hides the container invocation.

---

## 5. Milestones

Each milestone has a concrete, checkable exit criterion.

### M0 — Complete the bit map *(no library code yet)*

Produce `mosbius/bitmap.py`: all 192 bits, each mapped to its `mosbius.sym` pin,
and for matrix bits to `(crosspoint node, bus, side)`.

Most of this is already done (§2.3, §2.7, §2.8). The remaining work is the join
described in §2.9, done by parsing the configurator SVG's device-group structure
and matching it against the netlist's 30 `cfg` signals.

**Exit criterion:** the structural cross-validation in §6.1 passes — every `cfg`
signal claimed once, sides and widths consistent across SVG, netlist and layout,
and the §2.4 budget closing at 192 bits each claimed exactly once.

### M1 — Python core and **bitstream decoding**

`bitstream.py` (pack/unpack, hex round-trip), `model.py`, `bitmap.py`, `check.py`
(§3.1) and `decode.py` (§3.8). Pure data work — no EDA, no hardware.

**Decode comes before the router to de-risk it, not because it is the goal.** The
router (M3) is worthless if the bit map is wrong, and decode is the cheapest way to
prove the map: it is deterministic where routing is a search, and decoding a
silicon-proven bitstream into its known circuit confirms the map against reality
(§3.8). Getting that settled first means any later router failure is a router bug,
not a mapping question.

It also happens to give `mosbius decode` as a standalone aid for reading existing
bitstreams, which is a welcome side effect rather than the objective.

**Exit criterion:** `pytest` green; round-trips all 192 one-hot bitstreams
byte-exact; a deliberately over-constrained design is rejected with a useful
error; a hand-built short (`bus_pwr[3]` + `bus_pwr[6]` + `bus_short[6]`) is caught
by E1 with the switch path printed; and **decoding a known-good bitstream yields
the expected circuit** — the strongest available confirmation of the bit map.

### M2 — xschem library and simulation

Device symbols (§3.4), testbench template, `spice.py`, and `schgen.py` — so a
decoded bitstream becomes a viewable, editable schematic. Verified inside
IIC-OSIC-TOOLS.

Together with M1 this completes the **reverse** path end to end: bitstream ->
circuit -> schematic -> simulation, all before the router exists.

**Exit criterion:** the inverter example simulates and shows a rise time in the
tens of nanoseconds, consistent with the ~50 ns reported in the TT blog post; and
a decoded bitstream renders as a schematic that netlists back to the same config.

### M3 — Netlist -> bitstream (the router)

`netlist.py` and `route.py`. Parse the xschem netlist, allocate devices (§3.4),
assign nets to bus segments, check the design fits, emit the bitstream. The
forward, harder direction — and by now the bit map is already proven by M1/M2, so
any failure here is a router bug rather than a mapping question.

Includes `watch.py` (§3.3), since it is just a file watcher wrapped around the
route+check pipeline built here.

**Exit criterion:** the inverter and SR-latch schematics each produce a bitstream;
feeding those bitstreams into the web configurator displays the expected circuit;
`mosbius watch` reports a deliberately broken edit within about a second; and
a re-run of an unchanged design reuses its stored routing verbatim (§3.2b).

### M4 — Hardware

`program.py`: shift 192 bits MSB-first with `enable` low, raise `enable`, then
read back through `uo[0]` and compare. Agreed transport: **TT demoboard / RP2040**,
with **readback verification**.

The safety checker runs as a mandatory pre-upload gate, overridable only with an
explicit `--force`.

**Exit criterion:** the inverter example measurably inverts on real silicon; a
deliberately shorted config is refused by `program.py` without reaching the chip;
and `--verify` readback matches at least once during bring-up (after which it is
expected to stay unused).

### M5 — Documentation and examples

README, a worked tutorial, both examples documented with sim-vs-silicon plots.

---

## 6. Verification strategy

### 6.1 Captured configs as the regression corpus

**The configurator is not an independent oracle.** Our bit map is *derived from*
the configurator's SVG attributes, so testing against configurator-produced
bitstreams would prove only that we parse that SVG consistently — not that the
mapping is right. What it *does* provide is empirical weight: it encodes tnt's own
knowledge of the layout, and its bitstreams have been loaded into working silicon.
That makes it a trustworthy **starting point**, not a check. The genuinely independent sources are the xschem netlist (§2.8),
the layout column order (§2.3) and silicon. Two real cross-confirmations already
exist: the short column landing at bits 0–5 in both SVG and layout, and the six
`cfg_bus_pwr` rail assignments matching the netlist exactly.

**Structural cross-validation** (automated, cheap) is therefore the primary check:

- each of the 30 `cfg` signals claimed by exactly one column;
- A-side signals only on A-side columns, B-side only on B;
- the three 3-bit-wide signals only on the three `ab` columns;
- the §2.4 budget closing at exactly 192 bits, each claimed once.

**Captured configs** supply the regression corpus. Because routing is sticky
(§3.2b), a design's config file *is* its committed implementation — the same
artifact serves as design output and as regression fixture:

```
inverter.sch
inverter.mosbius.json     <- committed alongside the design
```

It holds the circuit's topology hash, the routing, the resulting 192 bits, the
bias current, the check verdict and the router version. On every run:

| Topology | Stored routing | Action |
|---|---|---|
| unchanged | present | **reuse verbatim** — no re-solve |
| changed | present | re-route minimally, preserving what still fits |
| any | absent | route from scratch |

A regression is then a much sharper signal than a diff to be reviewed: if the
topology is unchanged and the stored routing no longer produces the same
bitstream, the *packer or bit map* has broken, which is always a bug.

**Configs must be human-readable.** They record the route table, not just hex —
`vin: bus_A[1] -> ua[1]` reads as something a learner can check against what they
drew, where a raw hex string cannot.

**Silicon-confirmed configs.** A config whose circuit has been verified on the real
chip is marked as such. These are the strongest evidence in the corpus, they
accumulate naturally as people use the hardware, and stickiness means they keep
describing the circuit that was actually measured.

### 6.2 Sim-vs-silicon

For each example, compare the ngspice result against a measurement taken from the
programmed chip. Agreement validates the whole chain end to end. Disagreement
localises to either the bit map (M0) or the device models.

### 6.3 Safety checker corpus

A set of configs known to be dangerous (supply shorts via each reachable path,
bias shorted to a rail, driven pin into a rail) that must all be rejected, and a
set of known-good configs — including every example and every committed design —
that must all pass cleanly. A false positive here is as damaging as a false
negative: it teaches the user to reach for `--force`.

### 6.4 Structural invariants

Property tests that must hold for any design:
- Exactly 192 bits, always; hex string always 48 chars.
- `unpack(pack(x)) == x`.
- **`route(decode(b)) == b`** for any valid bitstream — the forward and reverse
  paths must agree, which is a strong joint check once M3 exists.
- Every bit in the map is claimed by exactly one pin (no gaps, no overlaps) —
  this is the §2.4 budget check, enforced as a test.

---

## 7. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Bit map join (§2.9) mislabelled | Low | Over-constrained by five independent checks (§2.9); verified against the golden corpus before anything else is built |
| `mosbius.sch` revision differs from `.mag` layout (`asw_col_pwr` exists as a cell but is unused in `asw_matrix.mag`) | Medium | Treat layout as authoritative for bit order, schematic for connectivity; reconcile in M0 |
| Routing a user circuit onto only 6 buses is over-constrained | Medium | Fail loudly with a clear "needs N buses, have 6" message; do not silently mis-route |
| Demoboard timing / 3.3V level issues | Low | `clock_hz: 0` means we choose the clock rate; start slow. Readback catches load failures |
| macOS Docker + USB serial friction | Low | Python tooling runs on the host, outside the container (§4.1) |

---

## 8. Open questions for sign-off

1. ~~Bus allocation policy.~~ **Answered: fully automatic routing, with a live
   watcher.** You draw the circuit; the tool works out net-to-segment assignment
   and device-half selection with no manual placement. See §3.2 and §3.3.
2. ~~Symbol granularity.~~ **Answered: generic N and P FET symbols with an
   adjustable width; the router assigns them to hardware devices, preferring a
   differential-pair half whenever the schematic shows two FETs sharing a source.**
   See §3.4.
3. ~~Reset and load sequence.~~ **Answered — see §3.5.** Readback is a debug
   feature (`--verify`), not part of the normal load: the chip is known working, so
   paying 384 clocks and a double shift on every load buys nothing. Background: `src/project.v:30-37`
   wires `ctrl_top` to the standard Tiny Tapeout harness signals: `.clk(clk)`,
   `.rst_n(rst_n)`, `.enable(ui_in[1])`, `.data_in(ui_in[0])`,
   `.data_out(uo_out[0])`. So the shift clock is the **TT project clock** and the
   chain reset is the **TT global reset** — both already driven by the demoboard,
   neither needing extra wiring. Remaining choice: should `program.py` pulse
   `rst_n` before each load, or rely on shifting a full 192 bits with `enable`
   low? *(Proposed: pulse reset — it costs nothing and guarantees a known state.)*
4. ~~Golden corpus size.~~ **Answered: configs are committed alongside designs and
   reused rather than regenerated (§3.2b).** The corpus accrues from real use
   instead of being hand-authored, and because routing is sticky there is no
   diff-acceptance problem. See §6.1.

---

## 9. Licence

Apache-2.0, matching upstream `ttsky-mini-mosbius`. `LICENSE` at the repo root and
SPDX headers on source files.

## 10. Sign-off

All four open questions are now answered (§8), each recorded in the architecture:

| Question | Resolution | Section |
|---|---|---|
| Bus allocation | Fully automatic routing, live watcher | §3.2, §3.3 |
| Symbol granularity | Generic N/P FETs; pairs preferred for shared sources | §3.4 |
| Reset / load sequence | `enable` low mandatory; readback is opt-in debug | §3.5 |
| Test corpus | Committed configs, reused not regenerated | §6.1 |

Settled in later discussion:

| Topic | Resolution | Section |
|---|---|---|
| Schematic structure | Two levels: fixed-port design block + testbench | §3.1b |
| Bias current | Programmable from the demoboard's RP2040; stored in the config | §3.4b |
| Message style | Instructive — beginners are the audience | §1.1 |
| Routing stability | Sticky: reused verbatim, minimal re-route on edit | §3.2b |
| Licence | Apache-2.0 | §9 |

Remaining before implementation:

- [ ] Hardware model (§2) reviewed — note §2.9, the one extraction step still open
- [ ] Architecture (§3) approved
- [ ] Milestones (§5) approved

No implementation begins until the above are checked.
