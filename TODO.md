# TODO — deferred work

Raised during the first outside-user run through `TUTORIAL.md` (2026-08-20),
drawing an inverter and heading for a 3-stage ring oscillator. Each item has
the context needed to act on it without re-deriving anything.

## 1. Improve the xschem symbols

`xschem/mosbius_lib/mosbius_*.sym` are functional but plain. Worth a pass for
legibility while drawing: clearer terminal labelling, better visual distinction
between the five device kinds, and symbol shapes that read as what they are
(the mirrors and the OTA especially).

Constraint: the `B {}` box declaration order in each `.sym` **is** the netlist
pin order, and `mosbius/netlist.py`'s `DEVICE_PINS` table hardcodes a matching
copy. Reordering boxes silently breaks the router. Change both together, and
`tools/gen_example_schematic.py`'s `_PINS_BY_KIND` offsets too.

## 2. Level-2 simulation of the routed design

Today you can only simulate the *pre-route* schematic — SPEC.md §3.1b's
Level-1 "ideal" result, real sky130 device sizing but no switch-matrix
parasitics. `examples/inverter/README.md` quantifies the gap: 84.4 ns
simulated at `w=1` against tnt's ~50 ns on real silicon.

The mechanism for the accurate version already exists and is unused:
`mosbius/spice.py`'s `render_config_spice()` emits a tie for all 192 config
pins of `mosbius.sym`, so a routed `SwitchConfig` can be simulated through the
real switch matrix with no behavioural model of the shift register (SPEC.md
§3.7). What's missing is the workflow around it — generating a testbench from
a routed config and running it. Budget ~2 min of sky130A model load per run
(see CLAUDE.md).

## 3. Fix the unmatched pin-direction errors

Netlisting from the xschem GUI prints, once per device:

```
Error: Symbol mosbius_nmos.sym: Unmatched subcircuit schematic pin direction: g
    iopin <--> in
```

Cause: the `.sym` declares the pin `dir=in`, while the `.sch` wires it with
`devices/iopin.sym` (inout). Systematic across the library — every `dir=in`
pin is an `iopin` in its schematic: `g` on `mosbius_nmos`/`mosbius_pmos`,
`ibias` on `mosbius_nsink`/`mosbius_psource`, and `inp`/`inm`/`ibias` on
`mosbius_ota`.

Cosmetic, not blocking: the netlist is correct regardless, and the
hand-drawn inverter that triggered it routed to the exact reference bitstream
`080000004010000001000000000000000040000400000000`.

Fix: change those pins to `devices/ipin.sym`. The only netlist change is the
annotation `*.iopin g` -> `*.ipin g`, which nothing downstream reads
(`netlist.py` skips lines starting with `*`). **Unverified** — batch mode with
`-q` doesn't print these messages at all, so confirming the fix means
netlisting from the GUI and watching the log.

Separately, the `Warning: open net: ua3/ua4/ua5/VDPWR/ibias` lines in the same
output are expected, not a bug — the template places all nine chip ports and
most designs use a few. Worth saying so in `TUTORIAL.md`, since it reads as a
problem on a first run.

## 4. Let the Python CLI drive the container

Netlisting means hand-writing a long `docker run` with four paths that have to
agree (host mount, `-w`, `--rcfile`, `-o`). A `mosbius netlist <sch>`
subcommand should derive all of them from the repo root and the schematic's
location.

Points to fold in, both hit on the first run:

- **Library path.** Schematics reference symbols bare (`C {mosbius_nmos.sym}`),
  so they only resolve if `xschem/mosbius_lib` is on the library path. The
  sky130A xschemrc already honours `XSCHEM_USER_LIBRARY_PATH` and appends it
  ([iic-osic-tools#7](https://github.com/iic-jku/iic-osic-tools/issues/7)) —
  set it and designs netlist from anywhere, instead of only from inside
  `mosbius_lib`. `TUTORIAL.md` step 1 doesn't say where to save the file and
  step 2's `-w` only works if it landed in `mosbius_lib`; this removes the
  trap rather than documenting it.
- **No accidental pulls.** Pass `--pull=never` so a missing image fails
  loudly instead of starting a ~20 GB download.
