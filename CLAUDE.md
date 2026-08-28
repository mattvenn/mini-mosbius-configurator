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
both load capacitors are `'cload'`.

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
the pad-vs-matrix split reproducible; the split is now written up in
`examples/inverter/README.md`, and one-shot "change one physical assumption
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
  Never modify it. `git submodule update --init` after cloning.
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
- 192-bit shift chain. Transmit **MSB first** (bit 191 first). 48 hex chars.
- `enable` (ui[1]) gates all switch outputs combinationally — **must be low
  throughout the shift**, or the chip walks through 192 arbitrary configurations.
  A supply short is reachable in 3 bits. (§3.1, §3.5)
- The configurator at https://people.osmocom.org/tnt/stuff/tt/mosbius.html is a
  **placeholder this project replaces**. Its SVG is the source of the bit map, so
  it is *not* an independent oracle for validating that map. (§6.1)
- Prior art for the full-size chip: https://github.com/peterkinget/MOSbiusCADFlow
  (§1.1).
