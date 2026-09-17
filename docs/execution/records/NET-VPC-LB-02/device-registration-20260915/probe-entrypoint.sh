#!/bin/sh
# Isolated U09 workload. Only this container's PID 1 receives fault signals.
# SIGUSR1 closes the HTTP listener; SIGUSR2 restores the same Pod/IP backend.
backend_pid=
start_backend() {
    if [ -z "$backend_pid" ]; then
        /probe &
        backend_pid=$!
    fi
}
stop_backend() {
    if [ -n "$backend_pid" ]; then
        kill -TERM "$backend_pid" 2>/dev/null || true
        wait "$backend_pid" 2>/dev/null || true
        backend_pid=
    fi
}
trap stop_backend USR1
trap start_backend USR2
trap 'stop_backend; exit 0' TERM INT
start_backend
while true; do
    sleep 1 &
    wait "$!" || true
done
