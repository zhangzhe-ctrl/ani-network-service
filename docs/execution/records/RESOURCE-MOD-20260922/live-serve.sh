#!/usr/bin/env bash
set -Eeuo pipefail
TASK_RUN=/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z
exec 9>/home/chabking/workspace/ani-network-service-runs/net05a-heavy.lock
flock -n 9 || exit 73
export GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1536MiB GOTOOLCHAIN=local GOWORK=off TZ=UTC
cd "$TASK_RUN/candidate"
main_pid= other_pid=
cleanup() {
 trap - EXIT INT TERM
 [[ -z $main_pid ]] || kill -TERM "$main_pid" 2>/dev/null || true
 [[ -z $other_pid ]] || kill -TERM "$other_pid" 2>/dev/null || true
 wait || true
}
trap cleanup EXIT INT TERM
python3 scripts/resource-rename-live runtime serve --directory "$TASK_RUN/private/runtime" &
main_pid=$!
tenant=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["tenants"]["b"])' "$TASK_RUN/private/runtime/plan.json")
"$TASK_RUN/private/runtime/bin/lb-api" serve -conf "$TASK_RUN/private/runtime/config.yaml" -database net_vpc_lb_02_a92201 -tenant "$tenant" -socket /home/chabking/.local/state/rsmod0922/b/tenant-a.sock > "$TASK_RUN/private/runtime/logs/tenant-b.log" 2>&1 &
other_pid=$!
wait -n "$main_pid" "$other_pid"
