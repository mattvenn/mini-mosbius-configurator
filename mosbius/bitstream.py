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

from mosbius import messages

# tnt's chain length, which is what these functions assume unless a caller
# says otherwise. Andrew Kang's part has a 196-bit chain and so a 49-character
# bitstream; every call that could be about either part passes `num_bits` from
# the chip it is working on (see mosbius/chips/__init__.py).
NUM_BITS = 192
HEX_CHARS = NUM_BITS // 4  # 48


def hex_chars(num_bits: int) -> int:
    """How many hex characters a chain of this length packs into.

    Rounds up: a chain whose length is not a multiple of four still needs a
    whole final digit, so this is not always num_bits // 4.
    """
    return (num_bits + 3) // 4


class BitstreamError(ValueError):
    """A bitstream string doesn't have the shape a mini-MOSbius config needs."""


def pack(bits, num_bits: int = NUM_BITS) -> str:
    """Turn a set of closed-bit numbers into a bitstream.

    `bits` may contain any bit numbers 0..num_bits-1; unlisted bits are 0.
    Raises BitstreamError if a bit number is out of range.
    """
    width = hex_chars(num_bits)
    mask = 0
    for bit in bits:
        if not (0 <= bit < num_bits):
            raise BitstreamError(
                messages.BITSTREAM_BIT_OUT_OF_RANGE.format(
                    bit=bit, max_bit=num_bits - 1, num_bits=num_bits
                )
            )
        mask |= 1 << bit
    return format(mask, f"0{width}x")


def unpack(hexstr: str, num_bits: int = NUM_BITS) -> frozenset[int]:
    """Turn a bitstream into the set of closed-bit numbers.

    Raises BitstreamError if `hexstr` isn't exactly the expected number of hex
    characters -- that's almost always a truncated paste, the wrong string
    entirely, or a bitstream built for the other mini-MOSbius, and silently
    accepting a short or long string would hide all three.
    """
    width = hex_chars(num_bits)
    s = hexstr.strip()
    if s.lower().startswith("0x"):
        s = s[2:]
    if len(s) != width:
        raise BitstreamError(
            messages.BITSTREAM_WRONG_LENGTH.format(
                got=len(s),
                expected=width,
                num_bits=num_bits,
                longer_or_shorter="shorter" if len(s) < width else "longer",
            )
        )
    try:
        mask = int(s, 16)
    except ValueError as e:
        raise BitstreamError(
            messages.BITSTREAM_NON_HEX_CHARACTER.format(hexstr=hexstr, expected=width)
        ) from e
    return frozenset(i for i in range(num_bits) if (mask >> i) & 1)
