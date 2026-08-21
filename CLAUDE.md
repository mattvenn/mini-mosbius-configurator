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

`TODO.md` holds deferred work. Still open: Level-2 simulation of the routed
design (§1), no way for a schematic to set a differential pair's tail
current (§2), device allocation decided by netlist order (§3), and findings
repeating their whole explanation once per offending device (§4). It is
renumbered from 1 whenever items are removed, and every citation of it in
this repo is updated in the same commit, so a `TODO.md` §number here is
always live.

Closed on 2026-08-21, so don't re-report them: a reversed drain/source is
now a `D2` hint that fires before the "DOESN'T FIT" it explains; a single
`mosbius_ota` routes (side is per *terminal* now -- the OTA is the one
device on both bus sides at once); `tail=` on a `mosbius_ota` reaches
`ctrl_otan_tail`; and a terminal asked for a bus row it has no switch to
raises a `RouteError` naming the device, the net and the rows it can
reach, instead of a `KeyError`.

**There is one netlist directory, `build/`, and `xschemrc` at the repo root
is what makes that true.** Launch xschem from the top of the repo and it
reads that file, which puts sky130A *and* `xschem/mosbius_lib` on the symbol
path and sets `netlist_dir` to `build/`. Netlist button, then point the
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

## Useful facts

- **The generic-device symbols have no body pin.** It is hard-wired to a rail
  on silicon, so `mosbius_*.sym` supplies it through xschem's `extra`
  attribute (`extra="b"`, `template="... b=VGND"`), which appends the net to
  both the instance line and the `.subckt` port list. So the netlist still
  carries 4 connections for a FET and `DEVICE_PINS` still counts them, but
  there is nothing to draw. Inside the device schematics the bulk is likewise
  not a wire: they instantiate sky130's **3-terminal** `nfet3_*`/`pfet3_*`
  symbols and pass it as the `@body` parameter. Wiring it instead makes
  xschem's GUI netlist report `undriven node: b`, because `extra` ports are
  invisible to its connectivity check.
- 192-bit shift chain. Transmit **MSB first** (bit 191 first). 48 hex chars.
- `enable` (ui[1]) gates all switch outputs combinationally — **must be low
  throughout the shift**, or the chip walks through 192 arbitrary configurations.
  A supply short is reachable in 3 bits. (§3.1, §3.5)
- The configurator at https://people.osmocom.org/tnt/stuff/tt/mosbius.html is a
  **placeholder this project replaces**. Its SVG is the source of the bit map, so
  it is *not* an independent oracle for validating that map. (§6.1)
- Prior art for the full-size chip: https://github.com/peterkinget/MOSbiusCADFlow
  (§1.1).
