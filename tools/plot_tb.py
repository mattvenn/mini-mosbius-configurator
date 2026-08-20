# SPDX-License-Identifier: Apache-2.0
"""Render an ngspice `wrdata` output file as a PNG for the M5 example docs.

`wrdata` writes one (time, value) column pair per requested vector, in the
order they were named in the .control block -- not a single shared time
column. Usage: python3 tools/plot_tb.py <data.txt> <out.png> <title>
"label:column-index" ... (column-index is 0-based into the *value* columns,
i.e. skipping each vector's own time column).
"""

from __future__ import annotations

import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main(argv: list[str]) -> int:
    data_path, out_path, title, *series = argv[1:]
    raw = np.loadtxt(data_path)

    fig, ax = plt.subplots(figsize=(8, 4))
    for spec in series:
        label, col = spec.split(":")
        col = int(col)
        t = raw[:, col * 2]
        v = raw[:, col * 2 + 1]
        ax.plot(t * 1e9, v, label=label)

    ax.set_xlabel("time (ns)")
    ax.set_ylabel("voltage (V)")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
