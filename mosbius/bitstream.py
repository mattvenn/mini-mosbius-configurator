# SPDX-License-Identifier: Apache-2.0
"""Pack/unpack the 192-bit config chain to/from the 48-hex-char bitstream.

See SPEC.md Sec 2.5. Bit *n* is `ctrl_out[n]`; the hex string is
`bitmask.toString(16).padStart(48, '0')` over a BigInt where bit *n* of the
mask is bit *n* of the chain -- i.e. the same encoding the web configurator's
`build()`/`parse()` functions use, so bitstreams remain interchangeable with
it (SPEC.md Sec 1.2).

Serial transmission is MSB-first (bit 191 first, SPEC.md Sec 2.1) -- that is
a property of *how the chain is shifted into the chip*, not of this hex
encoding, which is why it isn't reflected here. See mosbius/program.py (M4)
for the transmission order.
"""

from __future__ import annotations

NUM_BITS = 192
HEX_CHARS = NUM_BITS // 4  # 48


class BitstreamError(ValueError):
    """A bitstream string doesn't have the shape a mini-MOSbius config needs."""


def pack(bits) -> str:
    """Turn a set of closed-bit numbers into a 48-hex-char bitstream.

    `bits` may contain any bit numbers 0..191; unlisted bits are 0.
    Raises BitstreamError if a bit number is out of range.
    """
    mask = 0
    for bit in bits:
        if not (0 <= bit < NUM_BITS):
            raise BitstreamError(
                f"bit {bit} is out of range 0..{NUM_BITS - 1}\n"
                f"  The mini-MOSbius config chain is exactly {NUM_BITS} bits "
                f"(SPEC.md Sec 2.1) -- there is no bit {bit} to set."
            )
        mask |= 1 << bit
    return format(mask, f"0{HEX_CHARS}x")


def unpack(hexstr: str) -> frozenset[int]:
    """Turn a 48-hex-char bitstream into the set of closed-bit numbers.

    Raises BitstreamError if `hexstr` isn't exactly 48 hex characters --
    that's almost always a truncated paste or the wrong string entirely, and
    silently accepting a short/long string would hide that.
    """
    s = hexstr.strip()
    if s.lower().startswith("0x"):
        s = s[2:]
    if len(s) != HEX_CHARS:
        raise BitstreamError(
            f"bitstream is {len(s)} hex characters, expected exactly {HEX_CHARS}\n"
            f"  A mini-MOSbius config is {NUM_BITS} bits, written as "
            f"{HEX_CHARS} hex characters (SPEC.md Sec 2.5). This string is "
            f"{'shorter' if len(s) < HEX_CHARS else 'longer'} than that -- "
            f"check for a truncated copy-paste or a mismatched leading '0x'."
        )
    try:
        mask = int(s, 16)
    except ValueError as e:
        raise BitstreamError(
            f"{hexstr!r} contains a non-hex-digit character\n"
            f"  A mini-MOSbius bitstream is {HEX_CHARS} hex characters "
            f"(0-9, a-f) and nothing else."
        ) from e
    return frozenset(i for i in range(NUM_BITS) if (mask >> i) & 1)
