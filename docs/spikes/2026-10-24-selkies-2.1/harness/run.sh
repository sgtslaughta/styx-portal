#!/bin/bash
# run.sh <venv> <label> [gateway_py]  -> runs fake agent + probe, prints summary
S=$(cd "$(dirname "$0")/.." && pwd); V=$1; L=$2; G=${3:-/home/user/code/remote-access/agent/gateway.py}
R=$S/spike/run-$L; rm -rf $R; mkdir -p $R
python3 $S/spike/fake_agent.py $V $G $R & AG=$!
for i in $(seq 120); do grep -q ready $R/agent.log 2>/dev/null && break; sleep 0.5; done
grep -q ready $R/agent.log || { echo "agent not ready"; cat $R/agent.log; kill $AG; exit 1; }
sleep 1; (cd $S/spike && node probe.mjs $L $R 2>&1 | tail -3)
kill $AG; wait $AG 2>/dev/null; sleep 0.5
echo "== agent"; cat $R/agent.log; echo "== gateway"; grep -E "ws |refit|Error|Traceback" $R/gateway.out | tail -12
