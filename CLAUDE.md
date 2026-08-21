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

`TODO.md` holds deferred work raised by the first outside user running through
the tutorial (symbol polish, Level-2 simulation, pin-direction errors, wrapping
the `docker run` in the CLI, silently-dropped transistor widths, W2 false
alarms on internal nodes, and the missing `@spiceprefix` in the symbols).

**Netlists land in two different directories.** The xschem GUI's Netlist button
writes to `<schematic dir>/simulation/`; the `docker run` below writes wherever
`-o` points (the tutorial says `build/`). They are not the same file and
nothing syncs them — netlisting from the GUI leaves `build/` untouched, so the
router happily re-routes a stale netlist and reports success. `TODO.md` §4.

## Ground rules

- `ttsky-mini-mosbius/` is a **read-only git submodule** (upstream, Apache-2.0).
  Never modify it. `git submodule update --init` after cloning.
- This project is Apache-2.0.
- **The audience is beginners learning analog design** (§1.1). Every diagnostic
  states what happened, why the hardware behaves that way, and what to try
  instead. Terse error messages are a bug.

## Running the EDA tools

Nothing is installed natively. Use the IIC-OSIC-TOOLS container (`--skip` must be
the first argument):

```bash
docker run --rm -v "$PWD:/work" -w /work/ttsky-mini-mosbius/xschem \
  hpretl/iic-osic-tools:latest --skip bash -lc \
  'export PDK=sky130A PDK_ROOT=/foss/pdks
   xschem --rcfile $PDK_ROOT/sky130A/libs.tech/xschem/xschemrc -n -q -o /work/build mosbius.sch'
```

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
   `mosbius_*.sym`'s format string omits `@spiceprefix`, so instances netlist
   as `M1 ... mosbius_nmos` — an ngspice MOSFET primitive pointing at a
   `.subckt` — and fail identically. Seeing this message does not by itself
   mean `.spiceinit` is at fault. See `TODO.md` §7 for the one-line fix.

## Useful facts

- 192-bit shift chain. Transmit **MSB first** (bit 191 first). 48 hex chars.
- `enable` (ui[1]) gates all switch outputs combinationally — **must be low
  throughout the shift**, or the chip walks through 192 arbitrary configurations.
  A supply short is reachable in 3 bits. (§3.1, §3.5)
- The configurator at https://people.osmocom.org/tnt/stuff/tt/mosbius.html is a
  **placeholder this project replaces**. Its SVG is the source of the bit map, so
  it is *not* an independent oracle for validating that map. (§6.1)
- Prior art for the full-size chip: https://github.com/peterkinget/MOSbiusCADFlow
  (§1.1).
