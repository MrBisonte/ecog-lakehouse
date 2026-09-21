"""Synthetic ECoG files in the layout the synthetic adapter of convert_mat.py reads.

Each file mirrors a Stanford library file: `data` (samples x channels, amplifier units),
`stim` (one cue code per sample), `locs` (channels x 3, mm), `brain_area`, `srate`, plus
`experiment`, `subject` and `run`. Files are MATLAB v5, readable by scipy alone.
An existing file is kept, because the MATLAB header carries a creation time and a
regenerated file would carry a new sha256 and be ingested again.
"""

import argparse
import sys
import zlib

import numpy as np
from scipy.io import savemat

from pipeline.db import data_dir

# The last subject is the canary of spec 12.5, named in convert_mat.CANARY_SUBJECTS.
SUBJECTS = ["aa", "bb", "cc", "canary"]
# The full synthetic set covers two experiments; `--canary` can plant the canary of any
# experiment that has cue codes here, so a real build gets one per experiment (spec 12.5).
EXPERIMENTS = ["fingerflex", "motor_basic"]
CUE_CODES = {"fingerflex": 5, "motor_basic": 2, "faces_basic": 2}
SAMPLE_RATE_HZ = 1000
CUE_EVERY_S = 2
CUE_LENGTH_S = 1
NAN_BURST_SAMPLES = 500
AREAS = ["precentral", "postcentral", "supramarginal", "temporal"]


def generate(experiment: str, subject: str, seconds: int, channels: int) -> dict:
    """One file's arrays. Deterministic per experiment and subject."""
    rng = np.random.default_rng(zlib.crc32(f"{experiment}/{subject}".encode()))
    n = seconds * SAMPLE_RATE_HZ
    t = np.arange(n) / SAMPLE_RATE_HZ
    data = rng.normal(0.0, 200.0, size=(n, channels)).astype(np.float32)
    data += (500.0 * np.sin(2 * np.pi * 10.0 * t))[:, None].astype(np.float32)
    line = (300.0 * np.sin(2 * np.pi * 50.0 * t)).astype(np.float32)
    data[:, ::4] += line[:, None] * rng.uniform(0.2, 1.0, size=(channels + 3) // 4)
    if experiment == next(iter(CUE_CODES)):
        burst_at = n // 2
        data[burst_at : burst_at + NAN_BURST_SAMPLES, SUBJECTS.index(subject) % channels] = np.nan
    stim = np.zeros(n, dtype=np.int16)
    for k, onset in enumerate(range(0, n, CUE_EVERY_S * SAMPLE_RATE_HZ)):
        stim[onset : onset + CUE_LENGTH_S * SAMPLE_RATE_HZ] = 1 + k % CUE_CODES[experiment]
    side = int(np.ceil(np.sqrt(channels)))
    grid = np.array([(i % side, i // side) for i in range(channels)], dtype=np.float32)
    locs = np.column_stack([grid * 10.0, np.full(channels, 40.0, dtype=np.float32)])
    return {
        "experiment": experiment,
        "subject": subject,
        "run": 1,
        "srate": SAMPLE_RATE_HZ,
        "data": data,
        "stim": stim,
        "locs": locs,
        "brain_area": np.array([AREAS[i % len(AREAS)] for i in range(channels)], dtype=object),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--channels", type=int, default=64)
    parser.add_argument(
        "--canary", nargs="+", metavar="EXPERIMENT",
        help="write only the canary subject, for these experiments, next to a real build",
    )
    args = parser.parse_args(argv)
    root = data_dir() / "raw" / "synthetic"
    plan = (
        [(e, SUBJECTS[-1]) for e in args.canary if e in CUE_CODES]
        if args.canary
        else [(e, s) for e in EXPERIMENTS for s in SUBJECTS]
    )
    for experiment, subject in plan:
        (root / experiment).mkdir(parents=True, exist_ok=True)
        path = root / experiment / f"{subject}.mat"
        if path.exists():
            print(f"synth: keep {path}")
            continue
        savemat(path, generate(experiment, subject, args.seconds, args.channels))
        print(f"synth: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
