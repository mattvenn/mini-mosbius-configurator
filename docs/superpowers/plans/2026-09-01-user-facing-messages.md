# User-Facing Messages Centralization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every hand-written user-facing message in `mosbius/*.py` into one module, `mosbius/messages.py`, so a future rewording is a one-file edit, and rewrite the tests that check those messages to compare against the same constants instead of duplicating the prose.

**Architecture:** `mosbius/messages.py` holds one named string constant per message site (plain, often multi-line, triple-quoted strings with `{placeholder}` spots for `.format()`), grouped by source module. All decision logic -- which message applies, which word to use, what values to interpolate -- stays exactly where it is today; only the literal text moves. No renderer functions, no i18n framework.

**Tech Stack:** Plain Python (stdlib `str.format`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-01-user-facing-messages-design.md`

## Global Constraints

- Every rendered message must be **byte-identical** before and after it moves. This is the plan's only correctness criterion (spec "Testing" section) -- no wording changes ride along with this refactor.
- Naming convention: `<MODULE>_<WHAT>` (e.g. `SIMULATE_STALE_ROUTED`, `ROUTE_OK_NO_ISSUES`, `CHECK_D1_RAILS_SHORTED`). A `check.py` finding keeps its existing short code (`D1`, `R2`, ...) folded into the name.
- No renderer functions, no message-id/metadata dict structure, no pluralization engine (spec "Design" section) -- a call site changes from an inline f-string to `messages.KEY.format(...)`, nothing more.
- Every test that currently asserts on a hand-typed fragment of a message must be rewritten to assert against the same `mosbius.messages` constant (spec's "Tests assert against `messages.py`" section). A test may only keep a literal string assertion when it is checking a specific *interpolated fact* (a path, a count) that is easier to check directly than by reconstructing the whole template.
- Out of scope, do not touch: `xschemrc`'s two Tcl dialogs, `tools/regenerate_routed.sh`'s echo lines, `tests/`' own prose (only its assertions change), `tools/run_*`/`tools/sweep_*`/`tools/ad3/*`, `mosbius/spice.py`, `mosbius/bitmap.py`, `mosbius/watch.py` (no messages of their own).
- Also out of scope: `mosbius/program.py`'s two generated-script string templates (`generate_device_script`/`generate_identity_script`, and the `RuntimeError` string embedded inside them at line ~127 of `program.py`). Those are MicroPython source text that runs *on the RP2040 board*, not Python evaluated on the host -- they cannot `import mosbius.messages` because they never run under this package at all. Only `program.py`'s own host-side `raise ProgramError(...)` calls and `ibias_warning()` are in scope.
- Also out of scope: `mosbius/model.py`'s `setting_bit()` `KeyError` and `encode_cycler()`'s raw `ValueError`. Both are internal-invariant guards a user's schematic cannot trigger through the normal CLI path (a bad pin name in our own tables; a value `route.py`'s `_encode_setting` always catches and re-raises as a friendlier `RouteError`, whose text is migrated in Task 2). `SwitchConfig.__post_init__`'s `ValueError` (out-of-range bits) *is* in scope -- it validates data that can originate from a hand-edited or corrupted bitstream file, which a user can genuinely hit.
- Run `python3 -m pytest` (whole suite, not just the touched file) after every task, before committing. It must stay at 321 passed (the count may grow slightly if a task adds an assertion, but must never shrink).

## Migration Recipe (worked in full on the simplest site, Task 1's first step)

Every task below applies this same four-part transformation to each of its sites:

1. **Cut** the exact text out of the module (every character, including a interpolation's literal braces escaped as `{{`/`}}` where the original f-string had a real `{`/`}` that was not itself an interpolation).
2. **Paste** it into `mosbius/messages.py` as `<CONSTANT_NAME> = """..."""` (or `= "..."` for a one-liner), with `{name}` placeholders replacing each of the f-string's `{expr}` interpolations -- an interpolation that was an *expression* (e.g. `{'es' if n != 1 else ''}`) is computed at the call site first, into a plainly-named local variable, and the template references that variable's name.
3. **Replace** the call site's f-string with `messages.<CONSTANT_NAME>.format(name=..., ...)`.
4. **Rewrite** the site's test(s): replace `assert "<fragment>" in message` with `assert messages.<CONSTANT_NAME>.format(name=..., ...) in message` (or `== message` when the whole message is one template with no surrounding dynamic content), using the same values the test already computed to trigger the condition.

## File Structure

- Create: `mosbius/messages.py` -- the catalog. Grows one section per task; never restructured mid-plan.
- Modify (one task each, in this order): `mosbius/simulate.py`, `mosbius/route.py`, `mosbius/check.py`, `mosbius/pads.py`, `mosbius/program.py`, `mosbius/decode.py`, `mosbius/netlist.py`, `mosbius/bitstream.py`, `mosbius/model.py`, `mosbius/cli.py`.
- Modify (matching test file, same task): `tests/test_simulate.py`, `tests/test_route.py`, `tests/test_check.py` + `tests/test_check_design.py` + `tests/test_check_routing.py`, `tests/test_pads.py`, `tests/test_program.py` + `tests/test_cli.py`, `tests/test_decode.py`, `tests/test_netlist.py` + `tests/test_route.py`, `tests/test_bitstream.py` + `tests/test_cli.py`, (no test file for model.py's one site beyond what's already covered indirectly), `tests/test_cli.py`.

---

### Task 1: `mosbius/messages.py` (new) + migrate `mosbius/simulate.py`

**Files:**
- Create: `mosbius/messages.py`
- Modify: `mosbius/simulate.py:191-207` (`_route_hint`), `:210-259` (`check_routed_fresh`), `:262-339` (`simulate_from_routed_json`)
- Test: `tests/test_simulate.py`

**Interfaces:**
- Produces: `mosbius/messages.py` module with a `# --- simulate.py ---` section holding `SIMULATE_ROUTE_HINT`, `SIMULATE_STALE_ROUTED`, `SIMULATE_STALE_FIX_REGENERATE`, `SIMULATE_STALE_FIX_ROUTE_AND_SIMULATE`, `SIMULATE_UNREADABLE`, `SIMULATE_XSCHEM_NETLIST_GIVEN`, `SIMULATE_NOT_JSON`, `SIMULATE_NO_BITSTREAM_KEY`, `SIMULATE_BAD_BITSTREAM`.
- Consumes: nothing from an earlier task (this is the first).

- [ ] **Step 1: Read the current exact text of the two functions**

Confirm against the repo (do not retype from memory) that `mosbius/simulate.py` still reads as it did when this plan was written:

```bash
sed -n '191,339p' mosbius/simulate.py
```

- [ ] **Step 2: Create `mosbius/messages.py` with the simulate.py section**

```python
# SPDX-License-Identifier: Apache-2.0
"""Every hand-written user-facing message in mosbius/*.py, in one place.

TODO.md item 4: "all user facing text will ultimately be in a separate
file, for internationalisation and for easy re-writing of all messages."
See docs/superpowers/specs/2026-09-01-user-facing-messages-design.md.

Only the text lives here. Which message applies, which word to use, and
what values to interpolate all stay exactly where they were -- a call
site does `messages.KEY.format(...)`, nothing more. Grouped by the
module each message came from, in that module's own definition order.
"""

from __future__ import annotations


# --- simulate.py ------------------------------------------------------

SIMULATE_ROUTE_HINT = (
    "      python3 -m mosbius.cli route {netlist} --out {routed}\n"
    "      python3 -m mosbius.cli simulate {routed}"
)

SIMULATE_STALE_ROUTED = (
    "{routed_path} is out of date\n\n"
    "  These were changed after it was written:\n\n"
    "{what}\n\n"
    "  So this file still describes the circuit as it used to be routed.\n"
    "  Simulating it would build a routed netlist for that old circuit,\n"
    "  and a drawn-vs-routed testbench would then compare two different\n"
    "  designs -- which runs, and produces numbers, and means nothing.\n\n"
    "  To fix:\n\n"
    "{fix}"
)

SIMULATE_STALE_FIX_REGENERATE = "    sh tools/regenerate_routed.sh {sch}\n"

SIMULATE_STALE_FIX_ROUTE_AND_SIMULATE = (
    "    python3 -m mosbius.cli route {netlist} --out {routed_path}\n"
    "    python3 -m mosbius.cli simulate {routed_path}\n"
)

SIMULATE_UNREADABLE = (
    "{reason}\n"
    "  `mosbius simulate` reads a routed design: the JSON file that\n"
    "  `mosbius route --out <file>` writes. That file records which hardware\n"
    "  device and which bus row every part of your schematic became, which is\n"
    "  what a simulation of the real switch matrix needs to know.\n"
    "  If you haven't routed this design yet, route it first and simulate what\n"
    "  routing wrote:\n\n"
    "{route_hint}"
)

SIMULATE_XSCHEM_NETLIST_GIVEN = (
    "{path} is an xschem netlist, not a routed design\n"
    "  `mosbius simulate` starts from the JSON file that\n"
    "  `mosbius route --out <file>` writes, not from the netlist itself.\n"
    "  The netlist says what you drew; routing is the step that decides\n"
    "  which of the chip's hardware devices each drawn device becomes and\n"
    "  which bus row each net becomes, and the simulation is built out of\n"
    "  exactly those decisions -- it can't make them for you.\n"
    "  Route this netlist first, then simulate what routing wrote:\n\n"
    "{route_hint}"
)

SIMULATE_NOT_JSON = (
    "{path} is not a routed design: it isn't JSON at all\n"
    "  `mosbius simulate` reads the JSON file that\n"
    "  `mosbius route --out <file>` writes. Check you passed the path you\n"
    "  meant to -- a routed design is named <name>.mosbius.json and starts\n"
    "  with a '{{' character."
)

SIMULATE_NO_BITSTREAM_KEY = (
    "{path} is JSON, but not a routed design\n"
    "  A routed design is what `mosbius route --out <file>` writes, and it\n"
    "  always carries a \"bitstream\" entry (the 48 hex characters that\n"
    "  configure the chip) -- this file has no such entry, so there is no\n"
    "  configuration here to build a simulation from. Re-run `mosbius route`\n"
    "  with --out pointing at this path to write a real one."
)

SIMULATE_BAD_BITSTREAM = (
    "{path} has a \"bitstream\" entry that isn't a usable configuration\n"
    "{detail}\n"
    "  A routed design's bitstream is written by `mosbius route --out`, so a\n"
    "  broken one usually means the file was hand-edited. Re-run `mosbius\n"
    "  route` with --out pointing at this path to rewrite it."
)
```

Note the escaped `{{` in `SIMULATE_NOT_JSON`: the original f-string's `with a '{' character.` has a literal brace that is not a placeholder, so `.format()` needs it doubled or it will raise `KeyError`.

- [ ] **Step 3: Run a smoke check that the module imports**

```bash
python3 -c "from mosbius import messages; print(messages.SIMULATE_NOT_JSON)"
```

Expected: prints the message text ending in `with a '{' character.` (single brace in the printed output -- `{{` only appears in the source).

- [ ] **Step 4: Update `mosbius/simulate.py` to use the catalog**

Add the import near the top (alongside the existing `from __future__ import annotations` / stdlib imports):

```python
from mosbius import messages
```

Replace `_route_hint`'s body:

```python
def _route_hint(path: Path) -> str:
    """The two commands that get from `path` to a simulation, written out
    with this user's own filenames substituted in -- a beginner should be
    able to paste these rather than work out what to rename.

    `path` is whatever they actually passed, so it can be either half of
    the pair: a netlist (route it, then simulate the routing) or a routed
    design that doesn't exist yet (route the netlist it would have come
    from). Both name the same design, so either one gives us both names.
    """
    name = name_from_routed_path(path)
    netlist = path if path.suffix == ".spice" else path.with_name(f"{name}.spice")
    routed = path.with_name(f"{name}.mosbius.json")
    return messages.SIMULATE_ROUTE_HINT.format(netlist=netlist, routed=routed)
```

Replace `check_routed_fresh`'s `fix`-building and final `raise`:

```python
    what = "\n".join(f"    {kind:<10} {path}" for kind, path in newer)
    sch_for_cmd = next((p for kind, p in newer if kind == "schematic"), None)
    if sch_for_cmd is not None:
        fix = messages.SIMULATE_STALE_FIX_REGENERATE.format(sch=sch_for_cmd)
    else:
        fix = messages.SIMULATE_STALE_FIX_ROUTE_AND_SIMULATE.format(
            netlist=netlist, routed_path=routed_path,
        )
    raise SimulateError(
        messages.SIMULATE_STALE_ROUTED.format(routed_path=routed_path, what=what, fix=fix)
    )
```

Replace `simulate_from_routed_json`'s four raise sites:

```python
    try:
        text = path.read_text()
    except OSError as e:
        reason = (
            f"there is no file at {path}"
            if isinstance(e, FileNotFoundError)
            else f"{path} can't be read: {e.strerror.lower() if e.strerror else e}"
        )
        raise SimulateError(
            messages.SIMULATE_UNREADABLE.format(reason=reason, route_hint=_route_hint(path))
        ) from None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        if _looks_like_xschem_netlist(text):
            raise SimulateError(
                messages.SIMULATE_XSCHEM_NETLIST_GIVEN.format(
                    path=path, route_hint=_route_hint(path),
                )
            ) from None
        raise SimulateError(messages.SIMULATE_NOT_JSON.format(path=path)) from None

    if not isinstance(data, dict) or "bitstream" not in data:
        raise SimulateError(messages.SIMULATE_NO_BITSTREAM_KEY.format(path=path))

    try:
        config = SwitchConfig.from_bitstream(data["bitstream"], ibias=data.get("ibias", DEFAULT_IBIAS))
    except (BitstreamError, TypeError) as e:
        detail = "\n".join(
            line if line.startswith("  ") else f"  {line}" for line in str(e).splitlines()
        )
        raise SimulateError(
            messages.SIMULATE_BAD_BITSTREAM.format(path=path, detail=detail)
        ) from None
```

Leave every docstring, every comment, and every line of logic that is not itself the moved string exactly as it is (indentation-detection, JSON parsing, the `_looks_like_xschem_netlist` heuristic, etc.).

- [ ] **Step 5: Rewrite `tests/test_simulate.py`'s message assertions**

Add the import:

```python
from mosbius import messages
```

Replace the four "wrong file arrives" tests:

```python
def test_netlist_instead_of_routed_json_explains_the_difference(tmp_path):
    netlist = tmp_path / "inverter.spice"
    netlist.write_text(
        "** sch_path: /foss/designs/x/inverter.sch\n"
        ".subckt inverter ibias ua1 ua2 ua3 ua4 ua5 VAPWR VDPWR VGND\n"
        "XM1 ua1 ua2 VGND VGND mosbius_nmos w=1\n"
        ".ends\n"
    )

    with pytest.raises(SimulateError) as excinfo:
        simulate_from_routed_json(netlist)

    routed = tmp_path / "inverter.mosbius.json"
    route_hint = messages.SIMULATE_ROUTE_HINT.format(netlist=netlist, routed=routed)
    expected = messages.SIMULATE_XSCHEM_NETLIST_GIVEN.format(path=netlist, route_hint=route_hint)
    assert str(excinfo.value) == expected


def test_missing_file_says_how_to_produce_it(tmp_path):
    missing = tmp_path / "ring.mosbius.json"

    with pytest.raises(SimulateError) as excinfo:
        simulate_from_routed_json(missing)

    netlist = tmp_path / "ring.spice"
    route_hint = messages.SIMULATE_ROUTE_HINT.format(netlist=netlist, routed=missing)
    reason = f"there is no file at {missing}"
    expected = messages.SIMULATE_UNREADABLE.format(reason=reason, route_hint=route_hint)
    assert str(excinfo.value) == expected


def test_json_without_a_bitstream_is_not_a_routed_design(tmp_path):
    path = tmp_path / "notrouted.json"
    path.write_text(json.dumps({"device_roles": {}}))

    with pytest.raises(SimulateError) as excinfo:
        simulate_from_routed_json(path)

    assert str(excinfo.value) == messages.SIMULATE_NO_BITSTREAM_KEY.format(path=path)


def test_unreadable_bitstream_keeps_the_underlying_explanation(tmp_path):
    path = tmp_path / "ring.mosbius.json"
    path.write_text(json.dumps({"bitstream": "deadbeef"}))

    with pytest.raises(SimulateError) as excinfo:
        simulate_from_routed_json(path)

    message = str(excinfo.value)
    assert "isn't a usable configuration" in message
    # bitstream.py's own count-the-characters explanation survives -- not
    # yet migrated (Task 8), so still checked as a literal fragment here.
    assert "8 hex characters" in message
```

Replace the two staleness tests that check specific wording:

```python
def test_routing_older_than_its_netlist_is_refused(tmp_path):
    routed = _chain(tmp_path, netlist_mtime=2000, sch_mtime=500)
    with pytest.raises(SimulateError) as e:
        check_routed_fresh(routed)
    assert "netlist" in str(e.value)  # unchanged: checks the `what` table's row label, not prose


def test_routing_older_than_the_schematic_is_refused_even_if_the_netlist_is_old(tmp_path):
    routed = _chain(tmp_path, netlist_mtime=500, sch_mtime=2000)
    with pytest.raises(SimulateError) as e:
        check_routed_fresh(routed)
    assert "schematic" in str(e.value)
    assert "regenerate_routed.sh" in str(e.value)  # unchanged: checks messages.SIMULATE_STALE_FIX_REGENERATE fired, not its wording
```

These two are left as substring checks deliberately: they are testing *which fix branch fired* (the "schematic changed" row vs. the netlist-only row), not the wording of either template, so a literal fragment that names the distinguishing fact (`"netlist"`, `"schematic"`, the script name) is the right check per the Global Constraints' exception -- reconstructing the whole `SIMULATE_STALE_ROUTED` template here would mostly test string-formatting plumbing, not the behavior.

- [ ] **Step 6: Run this file's tests**

```bash
python3 -m pytest tests/test_simulate.py -v
```

Expected: all pass, same test count as before (no test added or removed, only rewritten).

- [ ] **Step 7: Run the full suite**

```bash
python3 -m pytest -q
```

Expected: `321 passed`.

- [ ] **Step 8: Commit**

```bash
git add mosbius/messages.py mosbius/simulate.py tests/test_simulate.py
git commit -m "Move simulate.py's user-facing messages into mosbius/messages.py"
```

---

### Task 2: Migrate `mosbius/route.py`

**Files:**
- Modify: `mosbius/route.py` (15 `RouteError` sites + `format_device_roles`/`format_net_rows`/`format_pad_note`)
- Test: `tests/test_route.py`

**Interfaces:**
- Consumes: `mosbius/messages.py` (Task 1).
- Produces: a `# --- route.py ---` section in `messages.py` (names below); `route.py`'s formatter functions unchanged in signature.

**Site table** (line numbers as read for this plan; re-`grep` before editing since Task 1 does not touch this file):

| Site (function, ~line) | Constant name | One-line description | Test |
|---|---|---|---|
| `_encode_setting`, 306 | `ROUTE_SETTING_NOT_VALID` | a `w=`/`ratio=`/`tail=` value isn't one of the 4 legal cycler settings | `test_route.py` |
| `_allocate_fets`, 787 | `ROUTE_NOT_ENOUGH_FETS` | too many FET requests of one polarity for the independent+pair slots | `test_route.py` |
| `allocate_devices`, 823 | `ROUTE_TOO_MANY_NTAIL` | more than one `mosbius_ntail` drawn | `test_route.py` |
| `allocate_devices`, 829 | `ROUTE_TOO_MANY_PTAIL` | more than one `mosbius_ptail` drawn | `test_route.py` |
| `allocate_devices`, 840 | `ROUTE_TOO_MANY_NSINK` | more than 2 `mosbius_nsink` drawn | `test_route.py` |
| `allocate_devices`, 849 | `ROUTE_TOO_MANY_PSOURCE` | more than 2 `mosbius_psource` drawn | `test_route.py` |
| `allocate_devices`, 858 | `ROUTE_TOO_MANY_OTA` | more than one `mosbius_ota` drawn | `test_route.py::test_two_ota_devices_reports_doesnt_fit` |
| `_matrix_bit`, 934-955 (port-net branch) | `ROUTE_PORT_NET_UNREACHABLE_ROW` | a `ua[k]` net's bonded row is outside a terminal's reach | `test_route.py` |
| `_matrix_bit`, 944-955 (internal-net branch) | `ROUTE_INTERNAL_NET_UNREACHABLE_ROW` | an internal net's chosen row is outside a terminal's reach | `test_route.py` |
| (shared wrapper) `_matrix_bit`, 948-955 | `ROUTE_CANNOT_REACH_ROW` | the outer "DOESN'T FIT -- ... cannot reach bus_X[N]" wrapper both branches above feed into | `test_route.py` |
| `_check_shared_source_is_reachable`, 1068 | `ROUTE_SHARED_SOURCE_TAKEN` (built via `_wrap`, keep as 5 paragraph constants -- see Step 2) | something else is wired to a diff pair's shared-source node | `test_route.py` |
| `format_device_roles`, 484 | `ROUTE_DEVICE_ROLE_LINE` | one line of the "Device roles:" table | `test_route.py` |
| `format_net_rows`, 512-513 | `ROUTE_NET_ROW_LINE` / `ROUTE_NET_ROW_PAD_NOTE` | one line of the "Bus rows:" table, with/without the pad-note suffix | `test_route.py` |
| `format_pad_note`, 532 | `ROUTE_PAD_NOTE` | "ua1, ua2 are connected to the chip's pads..." (already reworded this session) | `test_route.py::test_net_rows_report_flags_only_the_pin_bonded_nets` |

Two sites (`_wrap`'s multi-paragraph calls, `_check_shared_source_is_reachable`) build a message from several independently-wrapped paragraphs via `check.py`'s `_wrap()` helper (imported locally). Each paragraph is its own piece of fixed text with interpolations -- migrate each paragraph as its own constant (`ROUTE_SHARED_SOURCE_HEADLINE`, `ROUTE_SHARED_SOURCE_PROBLEM_PIN`, `ROUTE_SHARED_SOURCE_PROBLEM_OTHER`, `ROUTE_SHARED_SOURCE_WHAT_CAN_GO_THERE`, `ROUTE_SHARED_SOURCE_HOW_TO_MEASURE`), and keep the `_wrap(...)` call structure identical, only swapping each inline f-string argument for `messages.KEY.format(...)`.

- [ ] **Step 1: Worked example -- `_encode_setting` (the simplest site)**

Current (`mosbius/route.py:292-318`):

```python
def _encode_setting(value: int, step: int, *, device: str, prop: str) -> tuple[int, int]:
    try:
        return encode_cycler(value, step)
    except ValueError:
        valid = list(range(1, 5)) if step == 1 else list(range(2, 9, 2))
        options = ", ".join(str(v) for v in valid[:-1]) + f" or {valid[-1]}"
        raise RouteError(
            f"DOESN'T FIT -- {device}'s {prop}={value} is not a setting this "
            f"chip has\n\n"
            f"  {prop}= is stored as a 2-bit cycler: n = {step} * (1 + b_lsb + "
            f"2*b_msb)\n  (SPEC.md Sec 2.11). That gives exactly four settings, "
            f"{options},\n  and nothing in between.\n\n"
            f"  Nothing is rounded to the nearest one on your behalf: the chip "
            f"would\n  then be built to a different {prop} than your schematic "
            f"shows, which is\n  the kind of silent difference this tool exists "
            f"to prevent.\n\n"
            f"  To fix: set {prop}= to one of {options} on {device} in the "
            f"schematic,\n  and press Netlist again."
        ) from None
```

Add to `messages.py` (new `# --- route.py ---` section, after the simulate.py one):

```python
# --- route.py -----------------------------------------------------------

ROUTE_SETTING_NOT_VALID = (
    "DOESN'T FIT -- {device}'s {prop}={value} is not a setting this "
    "chip has\n\n"
    "  {prop}= is stored as a 2-bit cycler: n = {step} * (1 + b_lsb + "
    "2*b_msb)\n  (SPEC.md Sec 2.11). That gives exactly four settings, "
    "{options},\n  and nothing in between.\n\n"
    "  Nothing is rounded to the nearest one on your behalf: the chip "
    "would\n  then be built to a different {prop} than your schematic "
    "shows, which is\n  the kind of silent difference this tool exists "
    "to prevent.\n\n"
    "  To fix: set {prop}= to one of {options} on {device} in the "
    "schematic,\n  and press Netlist again."
)
```

New call site:

```python
def _encode_setting(value: int, step: int, *, device: str, prop: str) -> tuple[int, int]:
    try:
        return encode_cycler(value, step)
    except ValueError:
        valid = list(range(1, 5)) if step == 1 else list(range(2, 9, 2))
        options = ", ".join(str(v) for v in valid[:-1]) + f" or {valid[-1]}"
        raise RouteError(
            messages.ROUTE_SETTING_NOT_VALID.format(
                device=device, prop=prop, value=value, step=step, options=options,
            )
        ) from None
```

Add `from mosbius import messages` to `route.py`'s imports.

- [ ] **Step 2: Apply the same transformation to every remaining row in the site table above**

For each row: cut the f-string out of `route.py` at its listed location, paste it into `messages.py` under the listed constant name (turning each `{expr}` into a plain `{name}` and computing that name as a local variable at the call site if it wasn't one already), replace the `raise RouteError(...)` with `raise RouteError(messages.KEY.format(...)) from None` (keep `from None` wherever the original had it), and do the same for the three `format_*` functions (they return `list[str]`/`str`, not raise -- replace their literal per-line f-strings with `.format()` calls the same way, keeping the surrounding loop/`if` logic untouched).

For the multi-paragraph `ROUTE_SHARED_SOURCE_*` group specifically, the new call site keeps `_wrap`'s five-argument shape:

```python
        raise RouteError(_wrap(
            "DOESN'T FIT -- ",
            messages.ROUTE_SHARED_SOURCE_HEADLINE.format(net=net),
            messages.ROUTE_SHARED_SOURCE_EXPLAIN.format(
                halves=_join_and(halves), net=net,
                pair_roles=_join_and([roles[h] for h in halves]),
            ),
            problem,  # already built above from ROUTE_SHARED_SOURCE_PROBLEM_PIN / _OTHER
            messages.ROUTE_SHARED_SOURCE_WHAT_CAN_GO_THERE.format(
                rail=rail, tail_symbol=tail_symbol,
            ),
            messages.ROUTE_SHARED_SOURCE_HOW_TO_MEASURE,
        ))
```

with `problem`'s two branches (`is_pin` true/false) built from `ROUTE_SHARED_SOURCE_PROBLEM_PIN` / `ROUTE_SHARED_SOURCE_PROBLEM_OTHER` beforehand, mirroring the current `if is_pin: ... else: ...` structure exactly.

- [ ] **Step 3: Rewrite `tests/test_route.py`'s message assertions**

Add `from mosbius import messages`. For every existing `assert "<fragment>" in message` / `pytest.raises(RouteError, match="...")` that checks a site migrated above, replace it with the equivalent `messages.KEY.format(...)` comparison, following the same worked pattern as Task 1 Step 5 (full-template `==` comparison where the test already has every interpolated value in scope; keep a literal fragment only where the test is really distinguishing which branch/finding fired, e.g. `match="only one OTA"` naming which of the five `ROUTE_TOO_MANY_*` constants raised, not their exact wording).

- [ ] **Step 4: Run this file's tests**

```bash
python3 -m pytest tests/test_route.py -v
```

- [ ] **Step 5: Run the full suite**

```bash
python3 -m pytest -q
```

Expected: `321 passed` (or higher if a step added an assertion; never lower).

- [ ] **Step 6: Commit**

```bash
git add mosbius/messages.py mosbius/route.py tests/test_route.py
git commit -m "Move route.py's user-facing messages into mosbius/messages.py"
```

---

### Task 3: Migrate `mosbius/check.py`

**Files:**
- Modify: `mosbius/check.py` (18 findings across `_check_e1..e4`, `_check_w1..w3`, `_render_i1`/`_check_i1`, `_check_d1..d4`, `_render_r1`/`_render_r2`/`_render_r3`, `_check_b1`)
- Test: `tests/test_check.py`, `tests/test_check_design.py`, `tests/test_check_routing.py`

**Interfaces:**
- Consumes: `mosbius/messages.py` (Task 1).
- Produces: a `# --- check.py ---` section in `messages.py`.

**Site table** (function, code, ~line, description; every one of these builds its finding's `message` from an f-string or a `_wrap(...)` call whose paragraphs are fixed text):

| Function | Code | ~Line | Constant name(s) |
|---|---|---|---|
| `_check_e1_supply_short` | E1 | 223 | `CHECK_E1_SUPPLY_SHORT` |
| `_check_e2_ibias_short` | E2 | 245 | `CHECK_E2_IBIAS_SHORT` |
| `_check_e3_driven_pin_into_rail` | E3 | 267 | `CHECK_E3_PIN_INTO_RAIL` |
| `_check_e4_pin_contention` | E4 | 296 | `CHECK_E4_PIN_CONTENTION` |
| `_check_w1_shorted_channel` | W1 | 319 | `CHECK_W1_SHORTED_CHANNEL` |
| `_check_w2_floating_crosspoint` | W2 | 398-445 | `CHECK_W2_HEADLINE_ONE`, `CHECK_W2_HEADLINE_MANY`, `CHECK_W2_INTRO_ONE`, `CHECK_W2_INTRO_MANY`, `CHECK_W2_WHY_ALL_GATES`, `CHECK_W2_WHY_NOTHING_REACHES`, `CHECK_W2_HINT_UNTIED_TAIL`, `CHECK_W2_BODY` |
| `_check_w3_unconnected_terminal` | W3 | 458 | `CHECK_W3_PARTLY_WIRED` |
| `_render_i1` | I1 | 474-530 (see Step 1 below -- not yet fully read; re-read before migrating) | `CHECK_I1_*` (name split during Step 1's read) |
| `_check_d1_source_on_wrong_rail` | D1 | 658 (rails-shorted branch), 686 (wrong-rail-warning branch) | `CHECK_D1_RAILS_SHORTED`, `CHECK_D1_SOURCE_ON_WRONG_RAIL` |
| `_check_d2_drain_and_source_swapped` | D2 | 762 | `CHECK_D2_DRAIN_SOURCE_SWAPPED` |
| `_check_d3_tail_wrong_arity` | D3 | 854 | `CHECK_D3_TAIL_WRONG_ARITY` |
| `_check_d4_tail_on_rail` | D4 | 890 | `CHECK_D4_TAIL_ON_RAIL` |
| `_render_r1` | R1 | 911-957 (re-read before migrating) | `CHECK_R1_*` |
| `_render_r2` | R2 | 999-1029 (re-read before migrating) | `CHECK_R2_*` |
| `_render_r3` | R3 | 1065-1097 (re-read before migrating) | `CHECK_R3_*` |
| `_check_b1_bias_generator` | B1 | 1159 (no generator), 1174 (too many) | `CHECK_B1_NO_GENERATOR`, `CHECK_B1_TOO_MANY_GENERATORS` |

`_wrap`, `_join_and`, `format_path`, `_shortest_path`, `_name_list`, `_why_it_costs_the_pair`, `_biasing_graph`, `_terminal_name` are formatting/graph **infrastructure**, not message text -- they stay in `check.py` untouched. `_why_it_costs_the_pair` in particular returns a paragraph of fixed English with kind/rail interpolated; migrate *its* return value's text into `messages.py` too (`CHECK_D1_WHY_COSTS_PAIR`), since D1's WARN branch calls it.

- [ ] **Step 1: Read the sites not already seen in full during scoping**

This plan's author read E1-W3, D1-D2 start, D3-D4, and B1 in full while writing the spec and this table, but not `_render_i1`'s complete body past line 490, nor `_render_r1`/`_render_r2`/`_render_r3`. Before writing their `messages.py` entries:

```bash
sed -n '474,530p' mosbius/check.py   # _render_i1 + _check_i1_sparse_bus
sed -n '911,1030p' mosbius/check.py  # _render_r1, _check_r1, _render_r2, _check_r2
sed -n '1065,1122p' mosbius/check.py # _render_r3, _check_r3
```

Name each fixed-text piece found there following the same `CHECK_<CODE>_<WHAT>` convention as the rest of this table (e.g. if `_render_r1` picks between a "dropped" and a "not what you asked" sentence, that's `CHECK_R1_DROPPED` / `CHECK_R1_...`), and add a row to your own working copy of the table above so Step 3's test rewrite has names to reference.

- [ ] **Step 2: Worked example -- `_check_e1_supply_short` (the simplest finding)**

Current (`mosbius/check.py:218-236`):

```python
def _check_e1_supply_short(graph: Graph, comp: dict[str, int]) -> list[Finding]:
    if comp["VAPWR"] != comp["VGND"]:
        return []
    path = _shortest_path(graph, "VAPWR", "VGND")
    n = len(path)
    message = (
        f"DANGEROUS -- supply short\n\n"
        f"  VAPWR is joined to VGND through {n} closed switch{'es' if n != 1 else ''}:\n\n"
        f"{format_path(path)}\n\n"
        f"  This draws unlimited current from the 3.3V supply straight to ground.\n"
        f"  On real silicon that can damage the chip, so the upload is blocked.\n\n"
        f"  Why it happened: closing every switch on that path ties VAPWR and\n"
        f"  VGND together somewhere in the matrix -- often a bus_short switch\n"
        f"  joining a VAPWR-tapped row to a VGND-tapped one, or two rail taps\n"
        f"  landing on the same bus segment via different switches.\n\n"
        f"  To fix: open one of the switches on the path above -- moving the\n"
        f"  net to another row is usually enough."
    )
    return [Finding(code="E1", severity=ERROR, message=message)]
```

Add to `messages.py`:

```python
# --- check.py -------------------------------------------------------------

CHECK_E1_SUPPLY_SHORT = (
    "DANGEROUS -- supply short\n\n"
    "  VAPWR is joined to VGND through {n} closed switch{plural}:\n\n"
    "{path}\n\n"
    "  This draws unlimited current from the 3.3V supply straight to ground.\n"
    "  On real silicon that can damage the chip, so the upload is blocked.\n\n"
    "  Why it happened: closing every switch on that path ties VAPWR and\n"
    "  VGND together somewhere in the matrix -- often a bus_short switch\n"
    "  joining a VAPWR-tapped row to a VGND-tapped one, or two rail taps\n"
    "  landing on the same bus segment via different switches.\n\n"
    "  To fix: open one of the switches on the path above -- moving the\n"
    "  net to another row is usually enough."
)
```

New call site:

```python
def _check_e1_supply_short(graph: Graph, comp: dict[str, int]) -> list[Finding]:
    if comp["VAPWR"] != comp["VGND"]:
        return []
    path = _shortest_path(graph, "VAPWR", "VGND")
    n = len(path)
    message = messages.CHECK_E1_SUPPLY_SHORT.format(
        n=n, plural="es" if n != 1 else "", path=format_path(path),
    )
    return [Finding(code="E1", severity=ERROR, message=message)]
```

Add `from mosbius import messages` to `check.py`'s imports.

- [ ] **Step 3: Apply the same transformation to every remaining row in the site table**

Same recipe as Task 2 Step 2: cut, paste (turning `{expr}` into a plain `{name}` computed beforehand as a local, e.g. `plural = "es" if n != 1 else ""` for every `{'es' if n != 1 else ''}` occurrence -- this exact ternary repeats in E1-E4/W1, so name that local the same way, `plural`, at each site for consistency), replace the `message = (...)` assignment with `message = messages.KEY.format(...)`, or for `_wrap(...)`-built messages (`_check_b1_bias_generator`), replace each paragraph argument the same way Task 2 did for `ROUTE_SHARED_SOURCE_*`.

- [ ] **Step 4: Rewrite the three test files' message assertions**

Add `from mosbius import messages` to each. Replace hand-typed fragments with `messages.KEY.format(...)` comparisons, keeping a literal fragment only where a test distinguishes which finding/branch fired rather than checking wording (e.g. a test that only checks `finding.code == "D1"` and a device name appears needs no change beyond adding the constant-based check for the surrounding prose it was already asserting).

- [ ] **Step 5: Run these three files' tests**

```bash
python3 -m pytest tests/test_check.py tests/test_check_design.py tests/test_check_routing.py -v
```

- [ ] **Step 6: Run the full suite**

```bash
python3 -m pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add mosbius/messages.py mosbius/check.py tests/test_check.py tests/test_check_design.py tests/test_check_routing.py
git commit -m "Move check.py's 18 findings into mosbius/messages.py"
```

---

### Task 4: Migrate `mosbius/pads.py`

**Files:**
- Modify: `mosbius/pads.py:173-249` (6 `PadLookupError` sites), `:315-414` (`format_analog_header`, `format_pad_table`)
- Test: `tests/test_pads.py`

**Interfaces:**
- Consumes: `mosbius/messages.py` (Task 1).
- Produces: a `# --- pads.py ---` section.

**Site table:**

| ~Line | Constant name | Description |
|---|---|---|
| 173 | `PADS_PROJECT_NOT_ON_SHUTTLE` | shuttle index has no entry for this project |
| 182 | `PADS_CANT_FETCH_ENTRY_ANALOG` | can't fetch the shuttle index entry (ua->pin numbering context) |
| 190 | `PADS_CANT_FETCH_ENTRY_PCB` | can't fetch the shuttle index entry (PCB pad context) |
| 210 | `PADS_UNREADABLE_ENTRY` | cached/downloaded entry isn't readable JSON |
| 220 | `PADS_NO_ANALOG_PINS` | project has no analog pins at all |
| 247 | `PADS_INTERNAL_PIN_NOT_ON_CARRIER` | an internal analog pin the shuttle names isn't on this carrier's 12 |

- [ ] **Step 1: Read the six sites and the two `format_*` functions in full**

```bash
sed -n '141,262p' mosbius/pads.py
sed -n '315,414p' mosbius/pads.py
```

- [ ] **Step 2: Worked example -- `_check_e1`-equivalent, the shortest of the six (line 220, `has no analog pins`)**

Read its exact current text from the Step 1 output, then:

```python
# --- pads.py ---------------------------------------------------------

PADS_NO_ANALOG_PINS = (
    # <paste the exact text read in Step 1 here, converting its f-string
    # interpolations to {macro}/{shuttle}-style placeholders>
)
```

and change the call site the same way as every prior task's worked examples: `raise PadLookupError(messages.PADS_NO_ANALOG_PINS.format(...))`.

- [ ] **Step 3: Apply the same transformation to the other five raise sites and to `format_analog_header`/`format_pad_table`**

`format_analog_header` draws the physical ANALOG header (`pads.ANALOG_HEADER`, ASCII art) -- its literal layout characters (`-`, `|`, brackets) are formatting, not prose; only its English labels (if any -- re-check in Step 1's read) count as message text to migrate.

- [ ] **Step 4: Rewrite `tests/test_pads.py`**

Add `from mosbius import messages`; convert its `pytest.raises(pads.PadLookupError, match="...")` calls the same way as prior tasks.

- [ ] **Step 5: Run this file's tests, then the full suite**

```bash
python3 -m pytest tests/test_pads.py -v
python3 -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add mosbius/messages.py mosbius/pads.py tests/test_pads.py
git commit -m "Move pads.py's user-facing messages into mosbius/messages.py"
```

---

### Task 5: Migrate `mosbius/program.py`

**Files:**
- Modify: `mosbius/program.py:206-211` (`_run_mpremote`, no-mpremote), `:230-249` (`_run_mpremote`, no-result-line, including the two `port_hint` branches), `:306-312` (`read_board_identity`, no shuttle reported), `:316-341` (`ibias_warning`), `:364-371` (`program`, upload blocked), `:380-392` (`program`, upload didn't stick), `:394-401` (`program`, verify failed)
- Test: `tests/test_program.py`, `tests/test_cli.py` (both reference `ProgramError`)

**Interfaces:**
- Consumes: `mosbius/messages.py` (Task 1).
- Produces: a `# --- program.py ---` section.
- Note (Global Constraints): the `RuntimeError` embedded inside `generate_device_script`'s returned string (runs on the RP2040, not the host) is explicitly out of scope -- do not migrate it.

**Site table:**

| ~Line | Constant name | Description |
|---|---|---|
| 206 | `PROGRAM_MPREMOTE_NOT_INSTALLED` | `mpremote` isn't on PATH |
| 230-234 | `PROGRAM_PORT_HINT_AUTODETECT` | port hint when no `--port` was given |
| 236-238 | `PROGRAM_PORT_HINT_EXPLICIT` | port hint when `--port` was given explicitly |
| 240 | `PROGRAM_NO_RESULT_LINE` | mpremote ran but printed no result line (embeds one of the two port hints) |
| 306 | `PROGRAM_NO_SHUTTLE_REPORTED` | board answered but reported no shuttle |
| 328 | `PROGRAM_IBIAS_NOT_SET` | `ibias_warning`'s full text |
| 364 | `PROGRAM_UPLOAD_BLOCKED` | `check()` found errors and `force` wasn't set |
| 380 | `PROGRAM_UPLOAD_DIDNT_STICK` | `enable()` ran but the wrong design ended up selected |
| 394 | `PROGRAM_VERIFY_FAILED` | readback didn't match what was sent |

`_run_mpremote(what=...)`'s `f"{what} -- ..."` prefix (`what` defaults to `"CAN'T PROGRAM"`, is passed as `"CAN'T READ THE BOARD"` by `read_board_identity`) stays as an interpolated `{what}` in `PROGRAM_MPREMOTE_NOT_INSTALLED`/`PROGRAM_NO_RESULT_LINE`, not baked into two separate constants -- it is already parameterized in the source, and the recipe only converts *fixed* text, not existing parameters.

- [ ] **Step 1: Worked example -- `PROGRAM_MPREMOTE_NOT_INSTALLED` (the shortest)**

Current (`mosbius/program.py:205-211`):

```python
    if shutil.which("mpremote") is None:
        raise ProgramError(
            f"{what} -- mpremote isn't installed\n\n"
            "  program.py drives the demoboard through mpremote, the official\n"
            "  MicroPython tool. Install it with 'pip install mpremote' and try\n"
            "  again."
        )
```

Add to `messages.py`:

```python
# --- program.py ------------------------------------------------------

PROGRAM_MPREMOTE_NOT_INSTALLED = (
    "{what} -- mpremote isn't installed\n\n"
    "  program.py drives the demoboard through mpremote, the official\n"
    "  MicroPython tool. Install it with 'pip install mpremote' and try\n"
    "  again."
)
```

New call site:

```python
    if shutil.which("mpremote") is None:
        raise ProgramError(messages.PROGRAM_MPREMOTE_NOT_INSTALLED.format(what=what))
```

Add `from mosbius import messages` to `program.py`'s imports.

- [ ] **Step 2: Apply the same transformation to the remaining 8 rows**

For `PROGRAM_NO_RESULT_LINE`, build `port_hint` first from `PROGRAM_PORT_HINT_AUTODETECT` or `PROGRAM_PORT_HINT_EXPLICIT.format(port=port)` (mirroring the existing `if port is None else` branch), then `.format(what=what, returncode=..., port_hint=port_hint, stdout=..., stderr=...)` into `PROGRAM_NO_RESULT_LINE`.

For `PROGRAM_UPLOAD_BLOCKED`, keep `paths = "\n\n".join(f.message for f in report.errors)` as-is (it's already-migrated `check.py` finding text via Task 3, not new prose) and pass it as `{paths}`; keep the existing `"s" if len(report.errors) != 1 else ""` ternary computed into a local before `.format()`.

- [ ] **Step 3: Rewrite `tests/test_program.py` and `tests/test_cli.py`**

Add `from mosbius import messages` to both; convert their `pytest.raises(ProgramError, match="...")` assertions the same way as prior tasks.

- [ ] **Step 4: Run these files' tests, then the full suite**

```bash
python3 -m pytest tests/test_program.py tests/test_cli.py -v
python3 -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add mosbius/messages.py mosbius/program.py tests/test_program.py tests/test_cli.py
git commit -m "Move program.py's user-facing messages into mosbius/messages.py"
```

---

### Task 6: Migrate `mosbius/decode.py`

**Files:**
- Modify: `mosbius/decode.py:138-180` (`format_summary`)
- Test: `tests/test_decode.py`

**Interfaces:**
- Consumes: `mosbius/messages.py` (Task 1).
- Produces: a `# --- decode.py ---` section.

- [ ] **Step 1: Read `format_summary` in full**

```bash
sed -n '138,180p' mosbius/decode.py
```

- [ ] **Step 2: Migrate its literal English (headings, connective sentences) into `messages.py`, following the same cut/paste/replace/rewrite-test recipe as every prior task**

Name constants `DECODE_SUMMARY_<WHAT>` for each distinct heading or sentence found (e.g. a "Devices:" section header, a "no devices configured" empty-state line -- exact names depend on Step 1's read). Loop-generated per-device lines follow the `format_device_roles` pattern from Task 2: the line's fixed template moves, the loop stays.

- [ ] **Step 3: Rewrite `tests/test_decode.py`**

Add `from mosbius import messages`; convert its `format_summary` string assertions.

- [ ] **Step 4: Run this file's tests, then the full suite**

```bash
python3 -m pytest tests/test_decode.py -v
python3 -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add mosbius/messages.py mosbius/decode.py tests/test_decode.py
git commit -m "Move decode.py's user-facing messages into mosbius/messages.py"
```

---

### Task 7: Migrate `mosbius/netlist.py`

**Files:**
- Modify: `mosbius/netlist.py:218-230` (`check_netlist_fresh`, `StaleNetlistError`), `:278-282` (`parse_netlist`, routed-JSON-given-instead), `:300-311` (`parse_netlist`, pin-count mismatch), `:313-316` (`parse_netlist`, no devices found)
- Test: `tests/test_netlist.py`, `tests/test_route.py` (imports `NetlistError` too)

**Interfaces:**
- Consumes: `mosbius/messages.py` (Task 1).
- Produces: a `# --- netlist.py ---` section.

**Site table:**

| ~Line | Constant name | Description |
|---|---|---|
| 218 | `NETLIST_STALE` | netlist is older than the schematic it came from |
| 278 | `NETLIST_ROUTED_JSON_GIVEN` | a routed design JSON was handed to `route`/`watch` instead of a netlist (the mirror of `simulate.py`'s `SIMULATE_XSCHEM_NETLIST_GIVEN`) |
| 300 | `NETLIST_PIN_COUNT_MISMATCH` | an instance's pin count doesn't match its symbol's port list |
| 313 | `NETLIST_NO_DEVICES_FOUND` | no `mosbius_*` instances found anywhere in the netlist |

- [ ] **Step 1: Read all four sites in full**

```bash
sed -n '205,230p' mosbius/netlist.py
sed -n '268,317p' mosbius/netlist.py
```

- [ ] **Step 2: Worked example -- `NETLIST_STALE`**

Follow the same recipe as every prior task's first worked example: cut the text from `check_netlist_fresh`, paste as `NETLIST_STALE` in a new `# --- netlist.py ---` section of `messages.py`, replace the raise site with `.format(...)`, add `from mosbius import messages` to `netlist.py`'s imports.

- [ ] **Step 3: Apply the same transformation to the remaining three sites**

- [ ] **Step 4: Rewrite `tests/test_netlist.py` and the `NetlistError`-checking parts of `tests/test_route.py`**

Add `from mosbius import messages` to both; convert assertions the same way as prior tasks.

- [ ] **Step 5: Run these files' tests, then the full suite**

```bash
python3 -m pytest tests/test_netlist.py tests/test_route.py -v
python3 -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add mosbius/messages.py mosbius/netlist.py tests/test_netlist.py tests/test_route.py
git commit -m "Move netlist.py's user-facing messages into mosbius/messages.py"
```

---

### Task 8: Migrate `mosbius/bitstream.py`

**Files:**
- Modify: `mosbius/bitstream.py:35-42` (`pack`, bit out of range), `:55-63` (`unpack`, wrong length), `:65-70` (`unpack`, non-hex character)
- Test: `tests/test_bitstream.py`, `tests/test_cli.py` (embeds a `BitstreamError` via `simulate.py`'s composed `SIMULATE_BAD_BITSTREAM.detail` -- re-check `test_unreadable_bitstream_keeps_the_underlying_explanation` in `test_simulate.py` too, since Task 1 left its `"8 hex characters"` assertion as a literal fragment specifically because `bitstream.py` hadn't moved yet)

**Interfaces:**
- Consumes: `mosbius/messages.py` (Task 1).
- Produces: a `# --- bitstream.py ---` section.

**Site table:**

| ~Line | Constant name | Description |
|---|---|---|
| 35 | `BITSTREAM_BIT_OUT_OF_RANGE` | `pack()` given a bit index outside 0..191 |
| 55 | `BITSTREAM_WRONG_LENGTH` | `unpack()` given the wrong number of hex characters |
| 65 | `BITSTREAM_NON_HEX_CHARACTER` | `unpack()` given a non-hex-digit character |

- [ ] **Step 1: Read all three sites in full**

```bash
sed -n '26,70p' mosbius/bitstream.py
```

- [ ] **Step 2: Worked example -- `BITSTREAM_BIT_OUT_OF_RANGE`, then apply the same recipe to the other two**

Same cut/paste/replace pattern as every prior task. Add `from mosbius import messages` to `bitstream.py`'s imports.

- [ ] **Step 3: Rewrite `tests/test_bitstream.py` and the `BitstreamError` assertions in `tests/test_cli.py`**

Add `from mosbius import messages`; convert assertions.

- [ ] **Step 4: Revisit `tests/test_simulate.py`'s `test_unreadable_bitstream_keeps_the_underlying_explanation`**

Now that `bitstream.py`'s text lives in `messages.py`, tighten this test from the two literal-fragment checks Task 1 left in place:

```python
def test_unreadable_bitstream_keeps_the_underlying_explanation(tmp_path):
    path = tmp_path / "ring.mosbius.json"
    path.write_text(json.dumps({"bitstream": "deadbeef"}))

    with pytest.raises(SimulateError) as excinfo:
        simulate_from_routed_json(path)

    inner = messages.BITSTREAM_WRONG_LENGTH.format(got=8, expected=48)  # match unpack()'s actual kwargs
    detail = "\n".join(
        line if line.startswith("  ") else f"  {line}" for line in inner.splitlines()
    )
    assert str(excinfo.value) == messages.SIMULATE_BAD_BITSTREAM.format(path=path, detail=detail)
```

(Adjust the `BITSTREAM_WRONG_LENGTH.format(...)` kwargs to whatever names Step 2 actually gave that constant's placeholders.)

- [ ] **Step 5: Run these files' tests, then the full suite**

```bash
python3 -m pytest tests/test_bitstream.py tests/test_cli.py tests/test_simulate.py -v
python3 -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add mosbius/messages.py mosbius/bitstream.py tests/test_bitstream.py tests/test_cli.py tests/test_simulate.py
git commit -m "Move bitstream.py's user-facing messages into mosbius/messages.py"
```

---

### Task 9: Migrate `mosbius/model.py`

**Files:**
- Modify: `mosbius/model.py:328-335` (`SwitchConfig.__post_init__`, bits out of range)
- Test: whichever test(s) construct a `SwitchConfig` with an out-of-range bit directly -- locate with `grep -rn "SwitchConfig(bits=" tests/*.py` and `grep -rn "out of range" tests/*.py` before writing this task's test-rewrite step, since none was found by name during scoping (it may only be exercised indirectly today, in which case add one direct test rather than rewriting a nonexistent one).

**Interfaces:**
- Consumes: `mosbius/messages.py` (Task 1).
- Produces: a `# --- model.py ---` section with one constant, `MODEL_BIT_OUT_OF_RANGE`.
- Explicitly NOT touched (Global Constraints): `setting_bit()`'s `KeyError` and `encode_cycler()`'s `ValueError` -- internal-invariant guards, not user-reachable text.

- [ ] **Step 1: Read the site and check for existing test coverage**

```bash
sed -n '324,336p' mosbius/model.py
grep -rn "SwitchConfig(bits=" tests/*.py
grep -rn "out of range" tests/*.py
```

- [ ] **Step 2: Migrate the one site**

```python
# --- model.py --------------------------------------------------------

MODEL_BIT_OUT_OF_RANGE = (
    "bit(s) {bad} are out of range 0..{max_bit}\n"
    "  The mini-MOSbius config chain is exactly {num_bits} "
    "bits (SPEC.md Sec 2.1)."
)
```

```python
    def __post_init__(self):
        bad = [b for b in self.bits if not (0 <= b < bitstream.NUM_BITS)]
        if bad:
            raise ValueError(
                messages.MODEL_BIT_OUT_OF_RANGE.format(
                    bad=sorted(bad), max_bit=bitstream.NUM_BITS - 1, num_bits=bitstream.NUM_BITS,
                )
            )
```

Add `from mosbius import messages` to `model.py`'s imports. Watch for an import cycle: `messages.py` must not import anything from `model.py` (it doesn't -- it's pure string constants), so this is safe, but confirm `python3 -c "import mosbius.model"` still succeeds after the edit, since `model.py` is imported very early by nearly everything else.

- [ ] **Step 3: Add or rewrite the test found (or not found) in Step 1**

If Step 1 found no direct test, add one to `tests/test_model.py` if it exists, else create `tests/test_model.py` with just this one test (a new file is warranted here since none currently exists for this module -- check `ls tests/test_model.py` first):

```python
from mosbius import messages
from mosbius.model import SwitchConfig


def test_out_of_range_bit_is_refused():
    with pytest.raises(ValueError) as excinfo:
        SwitchConfig(bits=frozenset({192, 200}))
    assert str(excinfo.value) == messages.MODEL_BIT_OUT_OF_RANGE.format(
        bad=[192, 200], max_bit=191, num_bits=192,
    )
```

If Step 1 found an existing test, rewrite its assertion the same way instead of adding a new file.

- [ ] **Step 4: Run the relevant test(s), then the full suite**

```bash
python3 -m pytest tests/ -k "out_of_range or model" -v
python3 -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add mosbius/messages.py mosbius/model.py tests/
git commit -m "Move model.py's user-facing message into mosbius/messages.py"
```

---

### Task 10: Migrate `mosbius/cli.py`

**Files:**
- Modify: `mosbius/cli.py:73-107` (`_bitstream_arg`, 3 `ArgumentError` sites), `:110-127` (`_format_report`, the "OK -- no errors or warnings" line), `:140-186` (`_shuttle_for`, 2 `PadLookupError` sites), `:203-424` (every literal `print(f"...")` label across `cmd_check`/`cmd_route`/`cmd_simulate`/`cmd_watch`/`cmd_program`/`cmd_pads`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `mosbius/messages.py` (Task 1) and every other task's constants (this is deliberately last -- every formatter `cli.py` prints has already had its own text migrated by Tasks 1-9, so this task only touches `cli.py`'s own literal strings, not anything it calls into).
- Produces: a `# --- cli.py ---` section.

**Site table:**

| ~Line | Constant name | Description |
|---|---|---|
| 74 | `CLI_NO_FILE_AT_PATH` | bitstream arg looks like a path but no file is there |
| 89 | `CLI_UNRECOGNIZED_ARG` | bitstream arg is neither hex nor a readable routed-design path |
| 101 | `CLI_JSON_NO_BITSTREAM_KEY` | JSON given has no `"bitstream"` key (cli.py's own copy of this check, distinct from `simulate.py`'s `SIMULATE_NO_BITSTREAM_KEY` -- same idea, different wording/context, migrate separately, do not merge) |
| 122 | `CLI_REPORT_OK` | "OK -- no errors or warnings{note}." |
| 167 | `CLI_CANT_ASK_BOARD` | can't ask the board which chip is in the socket |
| 179 | `CLI_PROJECT_NOT_ON_SHUTTLE` | chip in socket doesn't have this project |
| 134/193/207/219/222/230/242/244/252-262/271/275/286/294/306/308/316/320/322/328/337/341/344/348 | `CLI_*` (one per distinct literal, per Step 1's read) | every `print(...)` label in `cmd_decode`/`cmd_pads`/`cmd_check`/`cmd_route`/`cmd_simulate`/`cmd_watch`/`cmd_program` |

- [ ] **Step 1: Read `cli.py` in full to enumerate every remaining `print()` literal precisely**

```bash
sed -n '1,424p' mosbius/cli.py
```

Build the final row list for the "every `print(f"...")` label" bucket above from this read -- some of these prints wrap another module's already-migrated formatter output (e.g. `print(_format_report(...))`, `print(format_pad_table(...))`) and need no change at all; only the literal strings `cli.py` itself owns (`"CAN'T READ THAT\n\n  {e}"`, `"OK -- uploaded to {args.project}"`, the `Device roles:`/`Bus rows:` section headers, etc.) are migration targets.

- [ ] **Step 2: Worked example -- `_bitstream_arg`'s three `ArgumentError` sites**

Current (`mosbius/cli.py:70-107`, already read earlier in this session):

```python
            raise ArgumentError(
                f"there is no file at {path}\n\n"
                f"  This looks like a path rather than a bitstream, and nothing is\n"
                ...
            )
```

Follow the same recipe as every prior task: cut, paste as `CLI_NO_FILE_AT_PATH` (and the other two) in a new `# --- cli.py ---` section, `.format(...)` at the call site, `from mosbius import messages` added to `cli.py`'s imports (it may already import from several `mosbius` submodules -- add `messages` alongside them).

- [ ] **Step 3: Apply the same transformation to every remaining row from Step 1's read**

Section headers like `print("Device roles:")` (line 254) and `print("Bus rows:")` (line 258) are one-line constants (`CLI_DEVICE_ROLES_HEADER = "Device roles:"`, `CLI_BUS_ROWS_HEADER = "Bus rows:"`) -- migrate them too, even though they're short, since the spec's scope is "every module with user-facing prose," not "every module with prose over N characters."

- [ ] **Step 4: Rewrite `tests/test_cli.py`**

Add `from mosbius import messages`; convert every remaining hand-typed fragment assertion the same way as all prior tasks.

- [ ] **Step 5: Run this file's tests, then the full suite**

```bash
python3 -m pytest tests/test_cli.py -v
python3 -m pytest -q
```

Expected: `321 passed` (or the running total after any tests added in Tasks 1-9).

- [ ] **Step 6: Manual smoke test -- confirm the CLI still reads right end to end**

```bash
python3 -m mosbius.cli route build/inverter.spice --out /tmp/smoke.mosbius.json 2>&1 | head -20
```

(Requires `build/inverter.spice` to exist -- if it doesn't, run `sh tools/regenerate_routed.sh examples/inverter/inverter.sch` first, or skip this step and rely on the CLI's own test coverage; this step exists to eyeball that a real end-to-end run still reads exactly as it did before Task 10, not to add new coverage.)

- [ ] **Step 7: Commit**

```bash
git add mosbius/messages.py mosbius/cli.py tests/test_cli.py
git commit -m "Move cli.py's user-facing messages into mosbius/messages.py"
```

---

## Final check (after Task 10)

- [ ] Confirm every module named in the spec's scope now imports `mosbius.messages` and no longer builds a multi-line user-facing string inline: `grep -rLn "from mosbius import messages" mosbius/cli.py mosbius/check.py mosbius/route.py mosbius/simulate.py mosbius/pads.py mosbius/program.py mosbius/decode.py mosbius/netlist.py mosbius/bitstream.py mosbius/model.py` should print nothing (an empty result means every file has the import).
- [ ] `python3 -m pytest -q` passes in full.
- [ ] Reread `TODO.md` item 4 and remove it (renumbering the rest, per `TODO.md`'s own convention) in a final commit, since this plan closes it.
