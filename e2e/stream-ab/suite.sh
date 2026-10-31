#!/bin/sh
# The full unattended suite (~90 min, stream tab closed):
#   1. A/B: h264-16 vs av1-30 on hotel + office, 2 repeats (latency, sharpness, load)
#   2. outage recovery: av1-30 through 3 s, 10 s and 30 s link drops
#   3. soak: av1-30 for 60 min (memory growth, crashes, watchdog)
cd "$(dirname "$0")" && mkdir -p results
python3 ab.py --variants h264-16,av1-30 --profiles hotel,office --repeats 2 > results/suite-ab.log 2>&1
python3 ab.py --variants av1-30 --profiles drop3,drop10,drop30 > results/suite-drop.log 2>&1
python3 soak.py --variant av1-30 --minutes 60 > results/suite-soak.log 2>&1
echo SUITE DONE > results/suite-done
