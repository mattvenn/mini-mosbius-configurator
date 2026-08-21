# mini-mosbius-configurator

[![Made with Claude](https://img.shields.io/badge/Made%20with-Claude-D97757?logo=anthropic&logoColor=white)](https://claude.com/claude-code)

An xschem library and Python toolchain for [tnt's mini-MOSbius](https://tinytapeout.com/chips/ttsky25a/tt_um_tnt_mosbius)
(`tt_um_tnt_mosbius`, Sky130, Tiny Tapeout). Draw an analog circuit in xschem,
validate it, generate the 192-bit configuration bitstream, and upload it to
the taped-out chip.

Upstream leaves this exact gap open: "the software suite to generate [the
configuration bitstream] is yet to be written." There's a hand-built web
configurator (a clickable SVG) that works, but it isn't connected to
simulation and isn't a comfortable way to design a circuit. This project
closes the loop:

```
design in xschem  ->  validate (fits? safe?)  ->  generate bitstream  ->  upload
```

**Read `SPEC.md` first.** It's the signed-off source of truth for the
hardware model, the architecture, and the verified facts this tool is built
on. This README is a map of what exists and how to run it; `SPEC.md` is
where the *why* lives, and `TUTORIAL.md` is where the *how* lives for a
first circuit end to end.

Mini-MOSbius exists so people can learn analog design -- the audience here
is beginners, not people who already know the switch matrix. Every error
this tool produces is written to teach: what happened, why the hardware
behaves that way, and what to try instead.

## Status

All five milestones (M0-M4) are code-complete and tested; M5 (this
documentation, plus the two worked examples in `examples/`) closes out the
plan in `SPEC.md` Sec 5. The one thing that has *not* happened in this
environment, because it needs a physical demoboard: uploading a bitstream to
real silicon and reading it back. `mosbius/program.py` is built from the
real upstream SDK source and its logic is fully tested, but SPEC.md Sec 8.4's
"inverts on real silicon" / "`--verify` readback matches" exit criteria need
your own hardware bring-up session.

## Quickstart

Nothing is installed natively -- xschem/ngspice run inside the
[IIC-OSIC-TOOLS](https://github.com/iic-jku/IIC-OSIC-TOOLS) Docker image;
the Python tooling runs on the host (it needs USB serial access for
`mosbius program`).

```bash
git submodule update --init   # first time only

# Draw a circuit: open xschem/mosbius_lib/minimosbius_template.sch (or copy
# it), wire up mosbius_nmos/mosbius_pmos/mosbius_nsink/mosbius_psource/
# mosbius_ota devices from mosbius_lib to the ports (ibias, ua1..ua5,
# VAPWR, VDPWR, VGND). See examples/inverter/ and examples/srlatch/ for
# two worked circuits, or follow TUTORIAL.md end to end.

# Netlist it: press xschem's Netlist button. It writes build/your_design.spice
# -- the repo-root xschemrc sets that up, so launch xschem from the top of
# the repo. build/ is gitignored; nothing needs copying anywhere.

# Route it (allocates devices onto real switch-matrix positions, checks for
# safety hazards, emits the 192-bit bitstream) -- runs on the host:
python3 -m mosbius.cli route build/your_design.spice \
  --out build/your_design.mosbius.json

# Upload it to a connected TT demoboard (needs mpremote: pip install mpremote):
python3 -m mosbius.cli program <the bitstream printed above>
```

`mosbius watch build/your_design.spice` re-runs
route+check every time xschem re-netlists the file (polls the file's mtime, so it works across the
Docker bind mount) -- keep it running in a terminal while you iterate in
xschem, instead of re-running the netlist/route/check cycle by hand.

## The pipeline, module by module

| Stage | Module | What it does |
|---|---|---|
| Bit map | `mosbius/bitmap.py` | All 192 chain bits, mapped to their pin/crosspoint/bus meaning. Generated once by `tools/extract_bitmap.py`; everything else is built on top of it. |
| Core model | `mosbius/model.py` | `SwitchConfig` (the 192-bit set + ibias), the electrical graph the checker and decoder both walk. |
| Bitstream | `mosbius/bitstream.py` | Pack/unpack between the bit set and the 48-hex-char string the chip actually shifts in. |
| Safety checker | `mosbius/check.py` | Finds supply shorts, pin contention, floating nodes, and other hazards before anything reaches silicon (SPEC.md Sec 3.1). Runs as a mandatory gate before upload. |
| Decoder | `mosbius/decode.py` | Bitstream -> circuit. The reverse path: reads back what a config actually wires up. |
| xschem library | `xschem/mosbius_lib/` | Five generic device symbols (`mosbius_nmos`, `mosbius_pmos`, `mosbius_nsink`, `mosbius_psource`, `mosbius_ota`) that netlist to the real sky130 transistor sizing behind each hardware block, plus `minimosbius_template.sch`/`tb_template.sch` for drawing and simulating a design. |
| Schematic generator | `mosbius/schgen.py` | Decoded circuit -> xschem schematic, so a bitstream (yours, or someone else's) becomes something you can open and look at. |
| Parser | `mosbius/netlist.py` | xschem-netlisted SPICE -> `MosbiusDesign` (the in-memory circuit request). |
| Router | `mosbius/route.py` | The forward path's hard part: allocates your devices onto real switch-matrix positions, assigns nets to bus rows, and emits the bitstream. Includes sticky routing (SPEC.md Sec 3.2b) -- an unchanged design reuses its exact prior routing instead of re-solving. |
| Watcher | `mosbius/watch.py` | Polls a netlist file and re-runs route+check on every change. |
| Hardware upload | `mosbius/program.py` | Shifts the 192 bits onto a TT demoboard via `mpremote`, with the safety checker as a mandatory pre-upload gate. |
| CLI | `mosbius/cli.py` | `decode` / `check` / `route` / `watch` / `program` subcommands wrapping all of the above. |

## Running the test suite

The Python tooling has no external dependencies beyond pytest:

```bash
python3 -m pytest tests/ -q
```

## Ground rules

- `ttsky-mini-mosbius/` is a **read-only git submodule** (upstream,
  Apache-2.0). Never modify it.
- This project is Apache-2.0.
- `build/` is gitignored -- it holds the netlists xschem generates and the
  routing output, never hand-edited or committed.
- `xschemrc` at the repo root is what points xschem at both symbol
  libraries and sends netlists to `build/`. It only takes effect if xschem
  is launched from the repo root; xschem does not search upwards for it.

See `CLAUDE.md` for the full list of verified corrections ("traps") this
project's bit map and architecture depend on -- several look authoritative
from upstream sources but are wrong in ways that were expensive to find.
