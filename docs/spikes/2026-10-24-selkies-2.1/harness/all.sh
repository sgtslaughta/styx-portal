#!/bin/bash
S=$(cd "$(dirname "$0")/.." && pwd); cd $S/spike; export STYX_SPIKE_T=1
for i in 1 2 3; do
./run.sh $S/v2.0.0 base200 >/dev/null 2>&1; python3 tsum.py run-base200/gateway.out base200
./run.sh $S/v2.1.0 native4012 >/dev/null 2>&1; python3 tsum.py run-native4012/gateway.out native4012
STYX_SPIKE_ABORT=1 ./run.sh $S/v2.1.0 native1006h >/dev/null 2>&1; python3 tsum.py run-native1006h/gateway.out native1006h
done
