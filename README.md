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

All five milestones (M0-M4) are code-complete and tested, and **the whole
loop has run on real silicon.** On 2026-08-28 a TTDBv3 [3.2] demoboard
carrying a ttsky25a chip loaded `examples/inverter`'s bitstream with
`mosbius program --verify`, the readback matched (SPEC.md Sec 8.4's exit
criterion), and an Analog Discovery 3 then measured the inverter's transfer
curve through the real switch matrix.

Seven worked examples now carry that comparison through: each one is
simulated **as drawn** (your schematic, ideal wires) and **as routed**
(through the configured switch matrix, with its parasitics and pads -- what
`mosbius simulate` builds), and five of them are **measured on silicon**
as well, with the numbers and the disagreements written up in
`examples/README.md`. Every symbol in the device library appears in at
least one of them. Two independent
measurements -- a ring oscillator's frequency and the inverter's trip point
-- put this chip at the PDK's `ss` corner, where the routed decks land
within 0.3% and 4 mV of the bench.

Still open: `TODO.md`. The big ones are complete device coverage in the
examples, automating the hardware-in-the-loop measurements (today every one
asks a person to wire a rig), and a curve-tracer experiment.

## Quickstart

Nothing is installed natively -- xschem/ngspice run inside the
[IIC-OSIC-TOOLS](https://github.com/iic-jku/IIC-OSIC-TOOLS) Docker image;
the Python tooling runs on the host (it needs USB serial access for
`mosbius program`).

```bash
git submodule update --init   # first time only

# Install the command line (host, not the container). The routing/checking/
# bitstream/simulation half is pure standard library; the extras are only for
# talking to a demoboard and drawing comparison plots:
pip install -e .                     # gives you the `mosbius` command
pip install -e '.[hardware,plots]'   # + mpremote, matplotlib

# Draw a circuit: open xschem/mosbius_lib/mini_mosbius.sch (or copy
# it), wire up mosbius_nmos/mosbius_pmos/mosbius_nsink/mosbius_psource/
# mosbius_ota/mosbius_ntail/mosbius_ptail devices from mosbius_lib to the
# ports (ibias, ua1..ua5, VAPWR, VDPWR, VGND). examples/ has seven worked
# circuits -- inverter, ringosc, srlatch, diffamp, pdiffamp, otabuf,
# currentsource -- each simulated as drawn and as routed, and five of them
# measured on silicon too (see
# examples/README.md for the background they share), or follow TUTORIAL.md
# end to end.

# Netlist it: press xschem's Netlist button. It writes build/your_design.spice
# -- the repo-root xschemrc sets that up, so launch xschem from the top of
# the repo. build/ is gitignored; nothing needs copying anywhere.

# Route it (allocates devices onto real switch-matrix positions, checks for
# safety hazards, emits the 192-bit bitstream) -- runs on the host:
mosbius route build/your_design.spice \
  --out build/your_design.mosbius.json

# Upload it to a connected TT demoboard (needs the `hardware` extra above):
mosbius program <the bitstream printed above>

# ...which finishes by printing the bench wiring table: which PCB pad each
# connected pin comes out on, and what the configuration put there. Ask for
# it on its own any time with:
mosbius pads build/your_design.mosbius.json
```

Not installing is fine too: every `mosbius <subcommand>` in these docs is exactly
`python3 -m mosbius.cli <subcommand>` run from the repo root, which is the
form the tool's own error messages print, since it works whether or not you
have installed anything.

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
| xschem library | `xschem/mosbius_lib/` | Seven generic device symbols (`mosbius_nmos`, `mosbius_pmos`, `mosbius_nsink`, `mosbius_psource`, `mosbius_ota`, `mosbius_ntail`, `mosbius_ptail`) that netlist to the real sky130 transistor sizing behind each hardware block, plus `mini_mosbius.sym`/`mini_mosbius.sch` (the chip as a block: the nine real pins, one symbol for every design) and `tb_template.sch` for drawing and simulating a design. |
| Parser | `mosbius/netlist.py` | xschem-netlisted SPICE -> `MosbiusDesign` (the in-memory circuit request). |
| Router | `mosbius/route.py` | The forward path's hard part: allocates your devices onto real switch-matrix positions, assigns nets to bus rows, and emits the bitstream. Includes sticky routing (SPEC.md Sec 3.2b) -- an unchanged design reuses its exact prior routing instead of re-solving. |
| Watcher | `mosbius/watch.py` | Polls a netlist file and re-runs route+check on every change. |
| Bench wiring | `mosbius/pads.py` | Which PCB pad to clip a probe onto, per pin, per shuttle -- composed from the shuttle index and the board's pad lettering rather than hard-coded, since a design's `ua[k]` moves with its placement. |
| Hardware upload | `mosbius/program.py` | Shifts the 192 bits onto a TT demoboard via `mpremote`, with the safety checker as a mandatory pre-upload gate. |
| CLI | `mosbius/cli.py` | `decode` / `check` / `route` / `simulate` / `watch` / `program` / `pads` subcommands wrapping all of the above. |

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

## Testing

* Thread on TT discord: https://discord.com/channels/1009193568256135208/1502244680111362069
