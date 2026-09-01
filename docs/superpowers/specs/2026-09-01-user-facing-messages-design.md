# User-facing messages in one file

Status: approved design, not yet implemented.
Closes TODO.md item 4: "all user facing text will ultimately be in a
separate file, for internationalisation and for easy re-writing of all
messages."

## Motivation

This session needed to edit a handful of user-facing strings (a routing
report's pad-capacitance note, an error dialog's wording) and each one
required first finding which of several files it lived in and which
language it was written in. `mosbius/route.py` alone carries 15 `RouteError`
raises and three multi-line report formatters; `mosbius/check.py` has 18
findings; `mosbius/cli.py`, `pads.py`, `program.py`, `decode.py`,
`netlist.py`, `bitstream.py` and `model.py` each carry more. Centralizing
the text is a one-time cost that makes every future rewording (and any
future translation) a single-file edit instead of a hunt.

## Scope

**In scope** -- every `mosbius/*.py` module that raises an exception with a
human-written explanation, or builds a string a user reads on a terminal:
`cli.py`, `check.py`, `route.py`, `simulate.py`, `pads.py`, `program.py`,
`decode.py`, `netlist.py`, `bitstream.py`, `model.py`. Roughly 80 message
sites in total (raise sites plus the standalone `format_*()` functions).

**Out of scope, deliberately:**
- `mosbius/spice.py`, `mosbius/bitmap.py`, `mosbius/watch.py` -- no
  human-written prose of their own (watch.py reuses check.py/route.py's
  formatters).
- `xschemrc`'s two Tcl dialogs and `tools/regenerate_routed.sh`'s echo
  lines. A Python module can't be `import`ed from Tcl or `sh`, and at
  roughly 7 short strings total, a cross-language loader would be more
  code than the text it manages. They stay inline, in their own language,
  where an editor can already find and change them directly.
- `tests/`, and the one-shot `tools/run_*`/`tools/sweep_*` experiment
  scripts and the `tools/ad3/` bench scripts. Different audience
  (CLAUDE.md already keeps these separate): whoever runs those already
  knows the pipeline and is re-running a specific investigation, not
  meeting the tool for the first time.

## Design

**One flat module, `mosbius/messages.py`**, holding one named string
constant per message site -- plain triple-quoted Python strings with
`{placeholder}` spots for `.format()`, grouped under a comment banner per
source module (`# --- route.py ---`, `# --- check.py ---`, ...) in the
same order those modules currently define them, so the new file reads as
a table of contents for the old one.

Naming convention: `<MODULE>_<WHAT>`, e.g. `SIMULATE_STALE_ROUTED`,
`SIMULATE_XSCHEM_NETLIST_GIVEN`, `ROUTE_OK_NO_ISSUES`,
`PADS_SHUTTLE_NOT_ON_CHIP`, `CHECK_D1_REVERSED_TERMINALS`. Findings in
`check.py` (which already carry a short code like `D1`, `R2`) fold that
code into the constant name so the two stay easy to cross-reference.

**Only the text moves.** Every call site keeps its existing logic --
which message applies, which branch of singular/plural wording to use,
what values to interpolate -- and changes from an inline f-string to
`messages.KEY.format(...)`. No renderer functions, no message-id/metadata
dict, no pluralization engine. This is deliberately less structure than a
real i18n toolchain (gettext, etc.) would use: nothing in this project
asks for locales or plural-form rules today, and CLAUDE.md's own stance
against speculative abstraction argues against building that machinery
ahead of a need. A `.format()` call at the call site is exactly as much
code as a wrapper function that does the same `.format()` one level away
-- the wrapper would not make the next rewrite easier, only add a place
to look.

Where a function currently *assembles* a message from conditional pieces
(e.g. `route.py`'s `format_pad_note()` choosing "is"/"are", "it"/"they",
"adds"/"add"), the assembly logic stays in `route.py` and only the fixed
template text (`"{which} {are} connected to the chip's pads, so {they}
{add} extra capacitance."`) moves to `messages.py`.

Where a function returns a `list[str]` of report lines (`format_device_roles`,
`format_net_rows`, `_format_report`'s "OK -- no errors or warnings" line),
each literal line template moves; the loop that builds the list from
routed-design data stays put.

## Migration order

Module by module, running the full test suite after each, since 57
existing tests assert on substrings of these messages:

1. `simulate.py` -- most self-contained (`SimulateError` sites only,
   already touched this session).
2. `route.py` -- `RouteError` sites, then the three `format_*` report
   functions.
3. `check.py` -- the 18 findings, in code order (E1..B1).
4. `pads.py`, `program.py`, `decode.py` -- one module at a time, in that
   order (fewest sites first).
5. `netlist.py`, `bitstream.py`, `model.py` -- lowest-level, smallest
   count, last.
6. `cli.py` last -- it calls into every other module's formatters, so
   migrating it last means every helper it prints has already moved.

After each module: run `pytest`, and update any of the 57 substring
assertions that broke purely because wording now lives in a constant
(not because the rendered text changed) -- a rendered message should be
byte-identical before and after moving it, so a test failure here means
either a transcription slip in the move or an assertion that was already
coupled to incidental formatting; fix the former, tighten the latter.

## Testing

- No new test file. The existing test suite (`tests/test_*.py`) already
  exercises every raise site and formatter by triggering the condition
  and asserting on the resulting message; moving the string constants
  does not remove coverage.
- The migration's own correctness check is textual equality: every
  rendered message before the move must equal the same call's rendered
  message after, for every code path the existing tests already reach.
  No behavior changes, so no new test scenarios are needed -- this is a
  refactor of where text lives, not of what the tool does.

## Risks / open questions

- **Multi-line strings with meaningful leading whitespace** (several
  `RouteError`/`SimulateError` messages indent continuation lines by two
  spaces to read as a hanging paragraph under a heading line). Triple-quoted
  constants must preserve that indentation exactly, since it's part of
  the rendered message, not incidental formatting.
- **`check.py`'s `merge_findings()`** collapses several near-identical
  findings (e.g. two diff-pair halves both losing `w=`) into one block at
  print time. The template text for those findings needs to stay
  parameterized the same way it is today (device name substituted in),
  since merging happens after rendering, not before.
