# SPDX-License-Identifier: Apache-2.0
"""mosbius/model.py -- SwitchConfig and related data structures."""

from __future__ import annotations

import pytest

from mosbius import messages
from mosbius.model import SwitchConfig


def test_out_of_range_bit_is_refused():
    with pytest.raises(ValueError) as excinfo:
        SwitchConfig(bits=frozenset({192, 200}))
    assert str(excinfo.value) == messages.MODEL_BIT_OUT_OF_RANGE.format(
        bad=[192, 200], max_bit=191, num_bits=192,
    )
