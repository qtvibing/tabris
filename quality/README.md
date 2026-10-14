# quality evaluation

optional uv project that measures tabris against 64-bit average, difference,
and dct hash baselines. it evaluates ~10,000 originals, all distinct-original
pairs, and 34 deterministic transformations per image, then writes reports to
`results/`. corpora are caltech-101 and pinned picsum (~330 MB of downloads).

```sh
uv sync
uv run python fetch.py
uv run python evaluate.py --quick   # 640 originals
uv run python evaluate.py           # full run
```

run the harness tests with `uv run python -m unittest`. the full run writes
`report.md`, `summary.json`, and `measurements.npz` under `results/`.
