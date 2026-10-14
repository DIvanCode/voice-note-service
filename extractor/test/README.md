# Benchmark commands

Start the local model first:

```fish
python app/main.py
```

Run the short quality cases:

```fish
python test/run_benchmark.py
```

Run the five-minute transcript:

```fish
python test/run_long_benchmark.py
```

Measure first and subsequent request latency:

```fish
python test/run_latency_benchmark.py
```

Compare sequential and concurrent requests:

```fish
python test/run_parallel_benchmark.py --workers 2 --cases 2
```

Configurations are stored in `test/test_configs/`. Reports are written to
`test/results/<test-name>/`. They are local measurements and
must not be used as production capacity settings until the target server is known.

The quality benchmark exits non-zero unless every case matches its expected JSON.
It also writes `results/quality_benchmark/quality-last-run.json` with per-field
accuracy and shape validity.
The long-transcript benchmark samples process RSS and GPU memory during generation
and reports peak values, not only before/after snapshots.
