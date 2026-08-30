# mini-mosbius-configurator

xschem library + Python toolchain for **tnt's mini-MOSbius** (`tt_um_tnt_mosbius`,
Sky130, Tiny Tapeout). Draw an analog circuit in xschem, validate it, generate the
192-bit configuration bitstream, upload it to the taped-out chip.

## Read this first

**`SPEC.md` is the source of truth.** It is signed off and covers the verified
hardware model, the architecture, and the milestone plan. Read it before doing
anything. Do not re-derive facts that are already marked VERIFIED there.

Status: M0-M4 complete and tested, M5 (docs + examples) in progress. See §5 for
the milestone plan.

**M4 has run on real silicon (2026-08-28), and the first measurement is
in.** A TTDBv3 [3.2] demoboard with a ttsky25a chip, driven from the
host: `mosbius program ... --verify` loaded `examples/inverter`'s
bitstream and the readback matched, which is SPEC.md Sec 8.4's exit
criterion met. Then an Analog Discovery 3 measured the transfer curve of
that inverter through the real switch matrix. Against the same circuit
simulated: threshold 1.599 V measured (calibrated), 1.600 V as routed,
1.605 V as drawn -- all three within 6 mV. **That last number was 1.495 V
until 2026-08-29, and the "the matrix moves the threshold 105 mV, and
silicon agrees" claim built on it is withdrawn**: the 1.495 V came from
the model-binning bug in trap 10 below, and with correct devices the
matrix barely moves this inverter's trip point at all. What the matrix
demonstrably costs here is speed -- 24.63 ns of rise time against 8.16 ns. Peak gain -17.6 V/V measured at 25 mV steps and
-20.7 V/V at 4 mV steps (the transition is only ~220 mV wide, so the step
size matters), against -15.4 V/V as routed. Absolute levels agreed too,
but only to the AD3's uncalibrated ~45 mV of channel offset, which is
larger than the ~1.3 mV the deck says a 1 MOhm probe droops VOH -- so a
level difference in that range is not evidence of anything until the
instrument is calibrated. `tools/measure_inverter_ad3.py` reproduces the
measurement, `tools/ad3.py` is the SDK wrapper.

Three things that cost time on the way there, all fixed, none worth
rediscovering:

- **The bitstream was fine; `mpremote` was the problem.** It soft-resets
  the board to get a clean REPL, and a soft reset does not clear the
  RP2350's GPIO, so ttboard's boot-time carrier detection reads pins that
  are still driven, decides no chip carrier is present, skips the chip
  ROM, and leaves the shuttle as `unknown` -- an index with no projects
  in it, so `tt.shuttle.has('tt_um_tnt_mosbius')` is False with the chip
  sitting right there. `program.py`'s generated script now calls
  `DemoboardDetect.probe()` *before* anything imports (and so creates)
  the `DemoBoard` singleton. Order matters: probing after the singleton
  exists does not help.
- **The AD3's scope range is a peak-to-peak span, not a maximum.**
  `FDwfAnalogInChannelRangeSet(h, ch, 5.0)` is +/-2.5 V about the channel
  offset. A 3.3 V rail measured that way reads back a steady, confident
  2.591 V -- the clipping ceiling -- with no error reported anywhere, and
  a whole afternoon went into explaining a supply that was never low. The
  tell is that clipped samples are *perfectly* flat: sd exactly 0.000 mV
  over thousands of points is a railed ADC, never a quiet signal.
  `tools/ad3.py` centres the 5 V span on 1.65 V for chip signals and puts
  every capture through `check_clipping()`.
- **On macOS the WaveForms cask alone does not give you the SDK.** The
  app carries a private copy of `dwf.framework`, so the GUI finds the
  device while every script reports 0 devices and `Adept NOK`. The DMG
  ships a second, standalone `dwf.framework` for `/Library/Frameworks`,
  and nothing works until it is copied there (`sudo cp -R
  /Volumes/WaveForms/dwf.framework /Library/Frameworks/`).

**This chip is an `ss` part, not `tt`, and that closed the last gap
(2026-08-28).** Both silicon measurements disagreed with the decks in the
same direction -- the ring 11% slow, the inverter's gain 17% high -- and
both are explained by the corner: at `ss` the ring lands within 0.3% of
39.528 MHz measured, the inverter's trip point within 4 mV of 1.599 V and
its gain within 4.6%. `tools/sweep_corners.sh` re-runs both testbenches at
tt/fs/sf/ff/ss by rewriting the `.lib` line in the netlist (leaving the
committed schematics, and so every published number, at `tt`), and
`tools/compare_corners.py` ranks them against the bench.

**It takes both circuits, and that is the transferable part.** An
inverter's trip point is a pure NMOS-versus-PMOS strength ratio: `fs` and
`sf` land 105 mV either side of the measurement while `tt`, `ff` and `ss`
sit within 6 mV, so it pins symmetry and says nothing about speed. A
ring's frequency is speed and barely separates `fs` from `tt` (43.47
against 43.89 MHz), because slowing the PMOS while speeding the NMOS
roughly cancels around a loop. Either alone leaves half the corner space
open. This also excluded a reasonable prior -- sky130 silicon is often
said to sit nearer `fs` than `tt`, and a ring measured slow is what
fitting a corner to digital speed alone would call `fs` -- by 105 mV of
trip point, fifty times the measurement's repeatability. One chip is one
sample; this says nothing about the shuttle.

**Which PCB pad a design's `ua[k]` comes out on is composed from two
looked-up halves, never computed (rewritten 2026-08-29).** The chip's
analog pins are muxed, so which *internal analog pin* a `ua[k]` lands on
depends on where that project sits on that shuttle; and which *PCB pad* an
internal analog pin reaches depends on how that shuttle's chip carrier is
wired to the demoboard. Both halves are free to change, so the same design
on ttsky26b may come out on entirely different letters, and nothing in this
repo may assume otherwise. For `tt_um_tnt_mosbius` on ttsky25a the answer is
ua0-ua5 -> K, C, J, D, G, F, of which five are confirmed on silicon
(ua0->K, ua1->C, ua2->J, ua3->D, ua4->G); only ua5->F is not. ua0->K was
confirmed 2026-08-29 by sweeping a supply into pad K through 20 kOhm and
watching it clamp -- `tools/measure_ibias_clamp_ad3.py`, written up in
`examples/README.md` -- and ua4->G the same day by `examples/diffamp/`'s
output sitting at 2.07 V against a simulated base of 1.985/2.020 V.

*Half one is an API.* `mosbius/pads.py` fetches
https://index.tinytapeout.com/ttsky25a/tt_um_tnt_mosbius.json -- the Tiny
Tapeout shuttle index, https://github.com/TinyTapeout/tinytapeout-index,
index files CC0 -- whose `analog_pins: [5, 0, 4, 1, 3, 2]` is ua -> internal
analog pin, and caches it as `build/pads_<shuttle>_<macro>.json`.

*Half two is not published anywhere, and lives in `ETR_CARRIER_PADS`.*
This file previously said `mosbius/pads.py` should read the letters off the
project's own page instead, because that page's Analog pins table has a PCB
Pin column. **That page is not an independent source and scraping it is
gone (2026-08-29).** tinytapeout.com composes that column in the browser
from exactly the same index `analog_pins`, indexed into a hard-coded
twelve-entry array in `functions/components/AnalogPinout.tsx` in
TinyTapeout/tinytapeout_www: `['C','D','F','G','J','K','X','W','U','T','R','Q']`.
So the old code round-tripped through rendered HTML to recover a JSON field
plus a constant, and inherited a bug while doing it: the website's own
`shuttle in nonETRShuttles` check tests JavaScript array *indices*, not
values, so it never fires, and tt06/tt07/tt08 project pages show ETR
letters for a carrier that labelled its analog pins A0..A5 / B0..B5.
`pads.carrier_pads()` makes that split itself.

That constant is now verified from the boards rather than trusted
(2026-08-29), by joining two KiCad layouts on the carrier connector's pin
numbers: TinyTapeout/breakout-ttsky-cob `J1` (HRS_DF12NB-60DS-0.5V) gives
pin -> `an0`..`an11`, TinyTapeout/tt-demo-pcb `J5` (TT_HRS_CARRIER_REVC),
`L` side, gives pin -> the ANALOG header letters `A`..`X`. Pin `N` to
`L{N}` yields an0..an11 -> C D F G J K X W U T R Q, matching the website
letter for letter, and the same join lines up every `uio`, `ui_in`,
`project_clk` and `project_rst` pin, so the alignment is not luck. Two
facts fell out of that join and are worth knowing at a bench: the ETR
carrier routes only **twelve** of the header's twenty-two lettered pads to
the chip at all, and on the ttsky carrier eight of the other ten (A, B, E,
H, L, M, N, P) are tied straight to **ground** -- so a probe on the wrong
letter is not merely a dead node. (S and V go to resistor nets.)

The demoboard's own copy of the index is a third thing that looks like a
source and is not: a `Design` there has macro/name/clock_hz/address and no
`analog_pins` at all (checked on hardware 2026-08-29). And an older
`PAD_LETTERS = "CDFGJK"`, described as "the carrier's six analog pads in
letter order, skipping E, H and I", was right about this project and wrong
about everything else: those six are the first six of the carrier's twelve,
not a run with gaps, and E and H are real pads. `ETR_CARRIER_PADS` is the
whole table, keyed by carrier rather than by shuttle, which is what that
constant should always have been.

Telling a user to "connect to ua1" is useless -- nothing on the board is
labelled that way -- so the output draws the ANALOG header itself
(`pads.ANALOG_HEADER`, read off a physical TT demoboard ETR v3.2), with
the pads in use bracketed and the ground squares shown. That layout is
data, not a rule: 16 columns, a ground every fourth column in each row and
the rows offset by two, so `B` is not under `A` but under the gap to its
right.

**The meter is in the testbench now, as `rprobe`/`cprobe` (2026-08-28).**
Each `tb_*.sch` carries `Rprobe_drawn`/`Cprobe_drawn` and
`Rprobe_routed`/`Cprobe_routed` -- the old `Cload_*`/`cload` names are
gone -- defaulting to a 10x passive probe (`rprobe=10meg cprobe=10p`),
with an Analog Discovery (`1meg`/`24p`) and a 1x probe (`1meg`/`100p`)
named in the sheet's own comment. This is the mirror image of the pad
decision: pads are baked into the generated deck because every user has
them, while nobody has the same probe, so the instrument is a parameter
and it lives at Level 2 with the rest of the bench -- never in the design
block, never in `<name>_routed.spice`. The default stayed at 10 pF so
every published number holds; resistance is the cheap half anyway (no
example here drives a node stiffer than ~50 kOhm), but without it an
output is a perfect open circuit and VOH sits exactly on the rail, so the
sheet cannot reproduce a bench measurement of a level at all.
`tb_inverter.sch` also gained a `dc Vin 0 3.3 0.005` sweep, which is what
the silicon comparison above is against. And a units error went with it:
`examples/README.md` called the diff amp's output "a ~20 MOhm node"
alongside its own 200 ns at 10 pF, which is 20 kOhm.

**Every symbol in the library now appears in a worked example, and
`examples/pdiffamp/` is what closed that (2026-08-29).** It is the diff
amp in the opposite polarity -- a PMOS pair on `pdiffpair+/-` with a
`mosbius_ptail`, loaded by an NMOS mirror on `nmos_a`/`nmos_b` -- and it
is the only example that places a `mosbius_ptail` or reaches
`ctrl_dpp_tail` at all. Its quiescent output sits one NMOS `Vgs` *above*
`VGND` (1.12 V) where the NMOS diff amp's sits one PMOS `Vgs` below
`VAPWR` (2.0 V), so its testbench steps ±10 mV rather than ±40 mV: at
21 V/V a bigger step compresses against the bottom rail and the chord gain
measures the compression. As drawn and as routed agree to about 1%.

**Measured on silicon 2026-08-29** (`tools/measure_pdiffamp_ad3.py`, pads
`ibias` K, `ua1` C, `ua2` J, `ua4` G): 17.82 V/V fitted at 99.4 uA against
21.22 as drawn, i.e. 16% low -- the third circuit on this part to fall
short in the same direction, after the diff amp's 18% and otabuf's, and so
the third piece of evidence for the `ss` corner. Its gain moves 1.028x
across 2.55x of tail current, where strong inversion predicts 1.60x, which
is the NMOS pair's moderate-inversion result reproduced on the PMOS side
with different devices. And it measures a **+18 mV input offset**, the one
quantity the sheet cannot produce at all, since both simulated branches
are symmetric by construction.

Two things it flushed out on the way, both worth not rediscovering: the
model-binning trap in the list below, and a router limitation now in
`TODO.md` -- `route_rail_net()` chooses a `cfg_bus_pwr` tap without
checking which row its `cfg_bus_short` pulls in on the other side, so a
design whose FET *drain* needs a rail (any source follower) gets either a
`DANGEROUS -- ua[5] shorted to VAPWR` or a spurious `DOESN'T FIT`,
decided by the order xschem happened to list the instances in.

**`examples/srlatch/` draws its write transistors `w=4` now, and the
warning it used to provoke is asserted in the test suite instead
(2026-08-29).** `XM5`/`XM6` land on diff-pair halves, whose width is fixed
in silicon, so the sheet's old `w=1` was ignored by the router (with a
warning) while the as-drawn deck went on simulating devices four times
weaker than the chip builds. That was visible for weeks as
`treset_drawn` = 18.79 ns coming out *slower* than `treset_routed` = 10.94
ns, backwards from every other example and written up here as an anomaly.
The model-binning fix then made it fatal: with correct devices the
too-weak write pair could no longer overpower the keeper PMOS, and the
as-drawn latch stopped setting at all (`qd_after_set` 0.0009 V against
3.300 V). Drawing `w=4` gives `treset_drawn` = 1.77 ns, restores the
ordering, and changes **no bit of the bitstream**, because there were
never any width bits behind the request. Two things came with it:
`tools/check_srlatch_sim.py` gained the "as drawn must be faster than as
routed" assertion it could not make before, and
`tools/run_srlatch_measured_edge.sh`'s `--drawn-w4` flag is gone, since
the sheet is what that flag used to simulate.

`TODO.md` holds deferred work. It is renumbered from 1 whenever items are
removed, so a `TODO.md` §number goes stale the moment anything above it
closes -- cite one only in `TODO.md` itself, and describe the item in
prose anywhere else. (The older `TODO.md Sec N` citations still scattered
through `SPEC.md`, `tools/` and `tests/` predate that rule and mostly
point at the numbering of a list that has since been rewritten; treat
them as historical labels, not as live pointers.)

Also closed on 2026-08-23: handing `mosbius simulate` the netlist
(`build/inverter.spice`) instead of the routed design
(`build/inverter.mosbius.json`) ended in a `json.decoder.JSONDecodeError`
traceback. `mosbius/simulate.py` now raises `SimulateError` -- naming
which of the two files the command reads, why routing has to happen
first, and the two commands to run with the user's own filenames already
substituted in -- for a netlist, a missing/unreadable path, JSON with no
`bitstream` entry, and a `bitstream` that won't unpack. The mirror slip
is covered too: a routed design JSON handed to `route`/`watch` now says
so, instead of "no mosbius_* instances found in this netlist".

Closed on 2026-08-23, so don't re-report it: the 192 config-bit ties
`mosbius/spice.py` emits are no longer written as a literal `0` ohms.
ngspice refuses a zero-ohm resistor, silently substitutes 1e-12 and warns
once per resistor, so every `mosbius simulate` deck opened with 192
`Value of resistor r.x2.rcfgNNN is too small` lines that buried any real
warning. `CONFIG_TIE_OHMS` now writes ngspice's own substitute value out,
which changes nothing electrically -- verified on `examples/inverter/`,
where both measured rise times are identical to the last digit before and
after, and the warning count goes 192 -> 0.

Closed on 2026-08-21, so don't re-report them: a reversed drain/source is
now a `D2` hint that fires before the "DOESN'T FIT" it explains; a single
`mosbius_ota` routes (side is per *terminal* now -- the OTA is the one
device on both bus sides at once); `tail=` on a `mosbius_ota` reaches
`ctrl_otan_tail`; and a terminal asked for a bus row it has no switch to
raises a `RouteError` naming the device, the net and the rows it can
reach, instead of a `KeyError`.

Closed on 2026-08-22, so don't re-report them: a schematic can now draw a
differential pair's tail current, with `mosbius_ntail`/`mosbius_ptail`
(one drawn pin -- the drain, wired to the pair's shared source -- plus
`tail=2/4/6/8`) reaching `ctrl_dpn_tail`/`ctrl_dpp_tail`; and `ibias` on
`mosbius_nsink`/`mosbius_psource`/`mosbius_ota` is implicit now (`extra=`),
matching the body ties, since the router always ignored a drawn connection
there. See `examples/diffamp/` for the tail feature end to end. Also: a
check that fires on several near-identical devices no longer repeats its
whole explanation per device -- `check.py`'s `merge_findings()` collapses
them into one block at print time (`cli.py`/`watch.py` both call it);
`SafetyReport.findings` is untouched, still one entry per offending
device, so this is display-only. And: which hardware slot a FET request
becomes no longer depends on the order xschem happened to list instances
in -- `route.py`'s `allocate_devices()` searches orderings
(`_allocate_fets_by_constraint()`) and keeps one where no diff-pair
gate is forced onto a two-sided net or an out-of-range package pin,
instead of just trying the netlist's own order and letting a badly-
ordered-but-electrically-fine circuit fail to route.

Closed on 2026-08-23, so don't re-report or re-investigate: a routed
design can now get a real, silicon-accurate SPICE simulation of itself as
routed onto the chip, with
one command, `mosbius simulate <routed.mosbius.json>`. It writes a
self-contained `<name>_routed.spice` subcircuit -- the real switch
matrix, real row-coupling capacitance, real bus-wire capacitance, and
real pad models on whichever package pins the design actually uses --
with the same 9-pin port list (`ibias ua1 ua2 ua3 ua4 ua5 VAPWR VDPWR
VGND`) every hand-drawn design already exposes, so it drops straight into
an existing testbench (e.g. via xschem's `spice_sym_def` instance
property) in place of an ideal `mosbius_*`-symbol block, and the
testbench's own stimulus/analysis/probes carry over unchanged -- the tool
never assumes what kind of simulation a design needs. The switch matrix
and its parasitics are baked into `mosbius/data/mosbius_device_library.spice`
once (`tools/rebuild_mosbius_device_library.sh` regenerates it if the
chip design or PDK models ever change), so ordinary use needs no
docker/xschem/magic step, only Python. See SPEC.md §3.7 and TODO.md's own
closing note for the full investigation this shipped from -- reaches
~1.28x of real silicon's measured frequency on the exact measured
ring-oscillator bitstream, down from 82x before that investigation
started.

Closed on 2026-08-28, so don't re-report either: **two silent
drawn-vs-routed divergences around the differential pair's shared source**,
found auditing the ideal library against the submodule. (a) That node has
no crosspoint -- `_collect_touches` drops a half's `s` terminal on purpose
-- and nothing checked the net was otherwise empty, so a third device
drawn onto it, or the net named `ua4` to measure the tail on a pin, routed
clean, said "OK -- no errors or warnings", and produced a bitstream
byte-identical to the one you get without that connection.
`_check_shared_source_is_reachable()` now raises a `RouteError` naming
what else is on the net and what may legitimately be there (nothing plus
the rail tie, or a `mosbius_ntail`/`mosbius_ptail`). (b) The tail bank has
no off state -- `diff_n`/`diff_p`/`ota_n` each have one always-on slice
gated by the bias reference (M8, W=20 against the reference's W=10) -- so
a pair floating on an internal net sinks 2 x ibias that the as-drawn model
does not have; `check.py`'s new `R3` says so, and stays quiet when the
source is rail-tied (the tie shorts the bank out) or a tail is drawn.

The rest of that audit came back clean, so don't redo it: every device
geometry matches silicon at every setting (nmos/pmos slice totals, mirror
slaves, both tail banks, the OTA's input pair and PMOS loads, and the
diff-pair halves -- which is why `w=4` is exactly a half), bodies match
(NMOS to GND, PMOS to VAPWR), the merged-slice junction parameters come
out identical to the three real slices (W/nf is constant across them), the
OTA's real topology is our ideal model under `ctrl_otan_mode[0]`, and all
18 device-setting bit groups are reachable by the router.

Closed on 2026-08-28, so don't re-derive it: **the ideal library's bias
reference is now the chip's, and there is exactly one of it per design.**
Every `mosbius_nsink`/`mosbius_psource`/`mosbius_ntail`/`mosbius_ptail`
used to carry its own diode-connected reference on the shared `ibias` net
as well as its slave leg, so N devices split the one reference current N
ways (two `mosbius_nsink ratio=2` measured -99 uA each against -200 uA
right, one alone measured -201 uA), and `mosbius_psource`'s reference was
a PMOS diode on the NMOS-referenced node -- a lone one delivered 1.65 pA,
and beside an nsink the two diodes formed a conducting chain across the
supply (+501/-707 uA where +-200 was right). `mini_mosbius.sch` now
carries the chip's own generator, three devices sized from the submodule
(`mirror_n.sch` M1 reference L=1 W=10 nf=2, its 1:1 `iout_fixed` copy M2,
`mirror_p.sch` M4 diode L=1 W=30 nf=4), the device symbols keep only
their slaves, and `mosbius_psource.sym` references `ibias_p` -- the node
`mosbius_ptail.sym`'s template had always named and nothing generated.
The slave widths were already right against the real reference, so
`ratio=N` and `tail=N` now both mean N x ibias, as the hardware's 2/4/6/8
cycler encoding does. Consequences, all verified: `examples/diffamp/`'s
as-drawn tail doubled to the 400 uA `tail=4` means (gain ~21.3 -> ~19.8
V/V; its README and `tools/check_diffamp_sim.py` are re-measured), while
the inverter, SR latch and ring oscillator are unchanged to the last
digit. Every design sheet needs exactly one generator: two halve the
reference, none leaves `ibias` with no DC path, which does not simulate.
Testbenches now give each instance its own bias source
(`Ibias_drawn`/`Ibias_routed`, both `'ibias_amps'`) for the same reason
both probe capacitors are `'cprobe'`.

Also closed on 2026-08-28: **`xschem -n -q` exits non-zero (10) on any
sheet using the `extra` body/bias pins** -- its connectivity check cannot
see those -- while writing a perfectly good netlist. Under `set -e` that
stopped `tools/regenerate_routed.sh` and the `tools/check_*_sim.sh`
scripts before they reached ngspice, so the diff amp CI job could never
have passed. They now check what came out (netlist written, no
`IS MISSING`) instead of the exit code.

Closed on 2026-08-27, so don't re-open any of the three: **pad loading is
finished business.** (a) *The analog muxes were never missing.* Upstream's
`pad_model.sch` already contains them -- one transmission gate sized
exactly like `tt_asw_3v3.sch`'s own pass FETs (nfet W=60 nf=12, pfet W=180
nf=18) with its gates hard-tied to the rails, i.e. this project's mux slot
permanently selected, plus the same pair at `mult=15` held off, i.e. the 15
deselected slots' capacitance hanging on the same pad line. `simulate.py`
puts a `pad_model` on every `ua` pin a config actually uses, so the mux is
in every routed deck already. (b) *`ibias`/`ua[0]` deliberately has no pad,
and should not get one.* The demoboard drives it from the Raspberry Pi's
programmable current source, not a resistor (SPEC.md §3.4b), so the ideal
current source in the testbenches is the *correct* model of real hardware
-- and a current source is indifferent to the pad's series resistance, so
the whole analog half's operating point is identical with or without it.
The pad would add only ~5pF on the bias node, which nothing here measures,
against needing a new "is ibias in use" rule (the crosspoint test doesn't
apply to it) and breaking the port-name/net-name coincidence that makes the
config ties land. (c) *No `--pads full|none` flag.* It was proposed to make
the pad-vs-matrix split reproducible; the split was measured on the
inverter (the routed output carries ~10.8 pF more than the drawn one,
which is the bond pad, not the switch matrix -- the write-up was trimmed
out of `examples/inverter/README.md` on 2026-08-30 and is in git history),
and one-shot "change one physical assumption
and re-run" experiments already have a home in `tools/` (`run_ring_pad_loaded.sh`
and five siblings). A CLI flag would put a physically-impossible deck -- a
chip with no pads -- on the product path a beginner uses, and would need a
name of its own, since pads-off is not "as routed".

**There is one netlist directory, `build/`, and `xschemrc` at the repo root
is what makes that true.** Launch xschem from the top of the repo and it
reads that file, which puts sky130A *and* `xschem/mosbius_lib` on the symbol
path, pins the PDK variant to sky130A, and sets `netlist_dir` to `build/`. Netlist button, then point the
router straight at `build/<name>.spice`.

**Launch xschem from anywhere else and both halves of that break, silently
and together.** xschem looks for `xschemrc` in its current working directory
only — not the schematic's directory, and it does not search upwards. From
`examples/inverter/` you get the container's default instead: the netlist
lands in `simulations/` (note the plural) rather than `build/`, *and* every
device comes out as `*  M1 -  mosbius_nmos  IS MISSING !!!!` because our
library is not on the path. Verified 2026-08-21. The router rejects that
file for having no devices, which is the good case; ngspice would run it as
an empty circuit.

The history worth not repeating: earlier docs had you netlist twice, once
from the GUI and once via `docker run -o build/`, producing two copies that
nothing kept in sync — so the router happily re-routed a stale file and
reported success. One configured location, written by one tool, is the
fix.

## Ground rules

- `ttsky-mini-mosbius/` is a **read-only git submodule** (upstream, Apache-2.0).
  Never modify it. Nothing on the user path needs it: `mosbius/bitmap.py`
  and `mosbius/data/mosbius_device_library.spice` are derived from it but
  committed, so the CLI, `tests/` and the example simulations all run
  without it, and neither CI workflow checks it out. `git submodule
  update --init` is only for re-deriving those two
  (`tools/extract_bitmap.py`, `tools/rebuild_mosbius_device_library.sh`)
  or re-running the `tools/run_ringo_*` experiments, which netlist
  upstream's own testbench.
- This project is Apache-2.0.
- **The audience is beginners learning analog design** (§1.1). Every diagnostic
  states what happened, why the hardware behaves that way, and what to try
  instead. Terse error messages are a bug.
- **Picture their first five minutes.** They are already running xschem in the
  IIC-OSIC-TOOLS container -- that is how they got here -- they have just
  cloned this repo, and they have opened one of the examples. They have not
  read the READMEs, have not run any `mosbius` command, and have no `build/`
  directory yet. So: anything that only works after a step they haven't taken
  has to say so itself, in the place they meet it, and name the command that
  fixes it. Judge a change by what that person sees, not by what it looks
  like to someone who already knows the pipeline.
- **That rule covers the words themselves, not just the structure.** Anything
  a user reads -- diagnostics, `decode` output, role names, net names -- gets
  spelled out rather than abbreviated, and **matches the vocabulary the user
  already has**: role names echo the symbol that was drawn. `dpn+`/`mirn_a`/
  `otan` became `ndiffpair+`/`nsink_a`/`ota` on 2026-08-21 for exactly this
  reason -- "dp" and "mirn" are guessable only if you already know the
  answer, and a message saying "3 mosbius_nsink requested, the chip has 2
  (nsink_a, nsink_b)" connects to what the user drew in a way "(mirn_a,
  mirn_b)" did not.
  Internal hardware identifiers are the one exception: `xpt_dpn_outp` and
  `cfga_dpn_inp` are the chip's own signal names and must stay verbatim, so
  when one of those has to appear in a message, translate it first
  (`model.TERMINAL_BY_CROSSPOINT` exists for that). Prefer a longer sentence
  over a shorter one that assumes vocabulary.

- **There is no "Level 1" / "Level 2" in this project's vocabulary.** Say
  what the thing is: a design **as drawn** (your schematic, ideal wires, no
  switch matrix), the same design **as routed** (through the real configured
  switch matrix, with its parasitics and pads -- what `mosbius simulate`
  builds), and what was **measured on silicon**. Decided 2026-08-24, closing
  TODO.md's own question about it. Two reasons, either sufficient: SPEC.md
  §3.1b already uses "Level 1" and "Level 2" for the *hierarchy* -- the
  design block and the testbench that instantiates it -- so the fidelity
  sense collided with our own source of truth; and in SPICE itself `LEVEL=1`
  and `LEVEL=2` are MOSFET model levels, where 2 is the cruder 1970s model,
  so "a Level-2 simulation" reads to an analog engineer as *less* accurate
  than the BSIM4 models we actually run. Net and measurement names follow the
  same words: `out_drawn`/`out_routed`, `trise_drawn`/`trise_routed`. So do
  the blocks themselves: a design keeps its own name (`.subckt inverter` --
  that is what the design IS, and it is forced anyway, since a subcircuit's
  name follows its `schematic=` file), and what `mosbius simulate` generates
  from it is `<name>_routed` in `<name>_routed.spice`. Not `<name>_mosbius`:
  everything here is mosbius, so that suffix distinguished nothing, and it
  named the chip rather than what had been done to the design (renamed
  2026-08-24).

## Running the EDA tools

**Netlist from xschem's Netlist button, not from a container** -- with
xschem launched from the repo root, so it picks up `xschemrc`. It writes
`build/<name>.spice`, and that is the file to hand to `mosbius route` /
`mosbius watch` directly:

```bash
python3 -m mosbius.cli route build/ring.spice --out build/ring.mosbius.json
```

Batch netlisting is the same thing without the GUI, and needs no `-o`,
since `netlist_dir` already points at `build/`:

```bash
docker run --rm -v "$PWD:/work" -w /work hpretl/iic-osic-tools:latest \
  --skip bash -lc 'xschem -n -q examples/ringosc/ring.sch'
```

Nothing needs copying to `build/`; the router takes a path. Running xschem a
second time in a container to re-netlist a file you already have open is pure
redundancy, and it was the source of a whole class of stale-netlist bugs.

xschem and ngspice are not installed natively -- they live in the
IIC-OSIC-TOOLS container, which is also where you draw. `--skip` must be the
first argument to the image. Batch netlisting from that container is still
the right tool for CI, just not for a person mid-edit -- every example
schematic is hand-drawn now; `git log` has the exact
invocation if you need it.

Two option meanings that are easy to get backwards: xschem's `-q` is
`--quit` (exit when done), **not** quiet -- the symbol/schematic consistency
messages are missing from batch because they are emitted on the GUI path, not
because `-q` silences them. `--tcl` runs *before* the schematic loads;
`--command` is the one that runs after. `-l <file>` sets a log file.

Running ngspice (M2+) is separate from netlisting: sky130A's combined model
library takes **~2 minutes to load** regardless of circuit size (confirmed
upstream, not fixable from our side: [IIC-OSIC-TOOLS#262](https://github.com/iic-jku/IIC-OSIC-TOOLS/issues/262)).
`.spiceinit` at the repo root has the small free speedups that thread exposed;
copy it alongside wherever ngspice actually runs, since it only reads
`.spiceinit` from its own current directory. Budget for that load time before
concluding a simulation has hung.

This produces `build/mosbius.spice` — the authoritative switch-matrix
connectivity. `build/` is gitignored. Python tooling runs on the **host**, not in
the container (it needs USB serial for the demoboard).

## Traps — verified corrections, do not regress

These were all got wrong once. The sources that look authoritative are not.

1. **`info.yaml`'s `ua[1..5]` labels ("Bus 1A".."Bus 5A") are pin names, not
   segment identities.** The real mapping straddles both bus sides:
   `ua[1]`→`bus_A[1]`, `ua[2]`→`bus_A[3]`, `ua[3]`→`bus_A[5]`,
   `ua[4]`→`bus_B[2]`, `ua[5]`→`bus_B[4]`. Three on A, two on B. (§2.10)

2. **Block names in `ctrl_top.v` indicate physical placement, not logical
   function.** Bits 162/163 sit in `blk_pmos_cm` but drive the PMOS diff-pair
   tail; `cfg_bus_pwr` lives inside the diff-pair blocks. Take bit meanings from
   the configurator geometry, never from RTL block names. (§2.11)

3. **The diff-pair halves are usable as standalone FETs.** They share only a
   source, so with the tail tied to a rail each is an ordinary common-source FET.
   That makes **eight** usable single FETs, not four. (§2.12)

4. **Count transistors, not blocks: 7 NMOS, 7 PMOS, OTA (5).** The tails have no
   matrix terminals; mirror legs expose one terminal each. (§2.12)

5. **28 crosspoints**, not 37.

6. **Diff-pair and OTA *inputs* reach only bus rows 1–3.** Everything else reaches
   all six. (§2.12)

7. **Never set `ngbehavior=hsa` in `.spiceinit`.** It changes ngspice's default
   element scale factor, which breaks automatic bin selection for the PDK's
   binned HV FET models (`sky130_fd_pr__nfet_g5v0d10v5`, used by
   `mosbius_nmos.sch`/`mosbius_pmos.sch`) — every instance fails with "could not
   find a valid modelname". Found getting the M5 example simulations running.

   **"could not find a valid modelname" has a second, independent cause.**
   `mosbius_*.sym`'s format string used to omit `@spiceprefix`, so instances
   netlisted as `M1 ... mosbius_nmos` — an ngspice MOSFET primitive pointing
   at a `.subckt` — and failed identically. Fixed 2026-08-21: all five
   symbols now carry `@spiceprefix` and `spiceprefix=X`, and instances
   netlist as `XM1 ...`. Kept here because the message is still ambiguous
   if you meet it: seeing it does not by itself mean `.spiceinit` is at
   fault, and an old schematic netlisted with an old symbol library will
   still produce it.

8. **A subcircuit instance's `schematic=` attribute is resolved relative to
   the SYMBOL's directory, and a failed lookup falls back silently.**
   `xschem/mosbius_lib/mini_mosbius.sym` is one symbol for every design --
   the chip's nine pins -- and which design an instance stands for is its
   `schematic=`. Point it at a design in `examples/` with a bare
   `schematic=inverter` or a relative `schematic=inverter.sch` and xschem
   looks beside the *symbol*, in `xschem/mosbius_lib/`, finds nothing, and
   falls back to the symbol's own (empty) body -- emitting `.subckt inverter`
   with no transistors in it, which netlists and simulates perfectly happily
   and measures nothing. Use the absolute form,
   `schematic="tcleval([file normalize examples/inverter/inverter.sch])"`,
   whenever the design is not in the same directory as the symbol. The
   subcircuit name always follows the `schematic=` file, not the symbol's
   file name. Verified both ways 2026-08-24.

9. **A bare `"` inside a `code`/`code_shown` symbol's `value="..."` silently
   truncates the netlist there.** xschem ends the attribute string at the
   first unescaped double quote, and everything after it -- the rest of your
   prose, `.option`, the whole `.control`/`.endc` block, every `.meas` -- is
   dropped without a warning. The netlist still generates, so the failure
   surfaces two steps later as ngspice's `no control job`, which points at
   the netlist rather than at the schematic that produced it. The tell is in
   `build/<tb>.spice`: the user architecture code stops mid-sentence, right
   at the offending quote, and `**** end user architecture code` follows
   immediately. Quote prose with `'single quotes'` (a SPICE comment does not
   care) or escape as `\"`. Note this is only about quotes *inside* a value:
   the `descr="..."` and `tclcommand="..."` attributes on launcher symbols
   are fine, since those quotes are the delimiters themselves. Hit on
   `examples/ringosc/tb_ring.sch` and fixed 2026-08-24.

10. **An expression handed to a subcircuit must not name a parameter the
    callee also defines** -- and sky130's binned model subcircuits define
    `w`. `mosbius_nmos.sch`/`mosbius_pmos.sch` sized their FET as
    `W="10*w"`, where `w` is our own user-facing width attribute; ngspice
    re-evaluates that expression in the callee's scope, where `w` means
    the model subcircuit's own parameter, and **selects the wrong bin**.
    The final geometry is right (ngspice reports W=10u L=0.5u either way)
    and nothing warns; what changes is the model card, and with it the
    threshold: 0.535 V against 0.822 V, worth 200 mV of Vgs at 187 uA.
    Found 2026-08-29 as a 55% as-drawn/as-routed gain disagreement in
    `examples/pdiffamp/`, isolated in a three-device deck, and fixed by
    computing the size into a differently-named parameter
    (`.param wdev='10*w' nfdev='2*w'`, then `W=wdev nf=nfdev`), which
    changes no user-facing name and no design sheet. `ratio=` and `tail=`
    never collided, so the mirror, tail and OTA symbols were always fine,
    and `mosbius/data/mosbius_device_library.spice` writes literal widths,
    so the as-routed side was never affected -- which is exactly why the
    bug showed up as the two branches disagreeing. Every bitstream is
    byte-identical before and after. The as-drawn *numbers* published in
    the inverter, ring, SR latch and diff amp READMEs were all computed in
    the wrong bin, and all four were re-run and updated the same day
    (inverter `trise_drawn` 8.90 -> 8.16 ns and trip point 1.495 ->
    1.605 V, ring 2.083 -> 2.289 GHz, diff amp base 1.985 -> 2.012 V;
    otabuf and currentsource were inside tolerance, as their `ratio`/`tail`
    sizing predicts). The SR latch needed a design change with it, below.

## Useful facts

- **The generic-device symbols have no body or bias pin.** Both are
  hard-wired on silicon, so `mosbius_*.sym` supplies them through xschem's
  `extra` attribute (`extra="b"`, `template="... b=VGND"` for the FETs;
  `mosbius_nsink`/`mosbius_psource`/`mosbius_ota` do the same for `ibias`,
  and `mosbius_ntail`/`mosbius_ptail` for both gate and source), which
  appends the net to both the instance line and the `.subckt` port list.
  So the netlist still carries every connection and `DEVICE_PINS` still
  counts them, but there is nothing to draw. Inside the device schematics
  the bulk is likewise not a wire: they instantiate sky130's **3-terminal**
  `nfet3_*`/`pfet3_*` symbols and pass it as the `@body` parameter. Wiring
  it instead makes xschem's GUI netlist report `undriven node: b`, because
  `extra` ports are invisible to its connectivity check -- the same is true
  of a drawn `ibias`, verified 2026-08-22: it routed clean with no warning
  either way, which is exactly why TODO.md made it implicit.
- **The chip's bias generator is a symbol, `mosbius_bias`.** Three
  transistors -- `mirror_n.sch` M1 and M2, `mirror_p.sch` M4, at those
  sizes -- behind one block with a single drawn pin, wired to the design's
  ordinary `ibias` iopin. `ibias_p` and the two rails come in on `extra`,
  so `ibias_p` is a plain net of the design's subcircuit: made by the
  block, picked up by `mosbius_psource`/`mosbius_ptail` through their
  templates, never drawn. Every design sheet in the repo uses it, and
  `mini_mosbius.sch` carries one so a copied template already has it.
  Exactly one per design, enforced by check.py's **B1**, which also counts
  the older hand-drawn form (an NMOS with gate and drain both on `ibias`)
  so a sheet predating 2026-08-28 still passes. Getting the count wrong is
  quiet in both directions: two
  references halve the current between them (measured -99 uA a leg where
  -200 uA was right), none leaves every mirror gate wherever the solver
  puts it.
- **An xschem symbol can declare a port *and* emit devices** -- a
  `type=iopin` symbol whose `format` is `*.iopin @lab` followed by
  instance lines contributes both, verified 2026-08-28 standalone and
  instantiated, with the port list unchanged and identical measured
  currents. It was built and then dropped in favour of `mosbius_bias`: it
  put the generator behind a pin that then looked unlike the other eight,
  and hid three transistors where nothing on the canvas could be opened to
  find them. Recorded because the capability is worth knowing about and
  the experiment need not be repeated.
- **That blind spot used to make every netlist report errors, and
  `mosbius_implicit_port` is the fix.** A net reaching only a transistor
  gate, whose only other connection is an `extra` port the checker cannot
  see, was reported as `Error: undriven node: ibias`; a net with one
  connection and an `extra` port as `Warning: open net: b`. Both on
  designs that were correct. There is no switch for it -- the binary has
  only `erc_open_net_is_error` and `erc_shorted_output_is_error`, and
  neither covers the undriven case -- and a label declared `dir=out` or
  `dir=inout` does not count as a driver (both tried, 2026-08-28), while a
  real `ipin`/`iopin` makes xschem reject the schematic outright, since
  `extra` pins are not pin boxes. What works is `type=noconn`, which marks
  a net as deliberately left alone. `xschem/mosbius_lib/mosbius_implicit_port.sym`
  is our own symbol of that type, named and drawn to say the accurate
  thing, placed on all ten such nets across the six device schematics
  (`mosbius_bias` bp; `mosbius_nsink` and `mosbius_psource` ibias and b;
  `mosbius_ota` ibias; `mosbius_ntail` and `mosbius_ptail` g and s). A net
  needs one when it is drawn on the canvas *and* its only way out is
  `extra`, which is why `mosbius_nmos.sch`/`mosbius_pmos.sch` need none
  despite their symbols carrying `extra="b"`: they hand the bulk to the
  PDK's 3-terminal FET as the `body=` parameter, so `b` is never a net on
  those sheets at all. It emits one comment line (`* implicit port ibias`)
  and changes nothing electrical -- verified by diffing the netlists, and
  by every bitstream and measured current being unchanged.
- **xschem prints its ERC report only when the run contains at least one
  Error.** Warnings alone produce nothing at all, which is why silencing
  the errors above also removed the `open net: ua1/ua4/ua5/VDPWR` lines a
  design sheet gets for the chip pins it does not use. The exit code is
  the message count, so `xschem -n -q` on this library's designs went from
  10 to 0 the same day. Do not read that as "no warnings exist"; read it
  as "no errors, so nothing was printed". Batch runs are silent either way
  unless you pass `-l <logfile>`.
- 192-bit shift chain. Transmit **MSB first** (bit 191 first). 48 hex chars.
- `enable` (ui[1]) gates all switch outputs combinationally — **must be low
  throughout the shift**, or the chip walks through 192 arbitrary configurations.
  A supply short is reachable in 3 bits. (§3.1, §3.5)
- The configurator at https://people.osmocom.org/tnt/stuff/tt/mosbius.html is a
  **placeholder this project replaces**. Its SVG is the source of the bit map, so
  it is *not* an independent oracle for validating that map. (§6.1)
- Prior art for the full-size chip: https://github.com/peterkinget/MOSbiusCADFlow
  (§1.1).
