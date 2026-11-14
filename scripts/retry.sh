#!/usr/bin/env bash
# Run a network-dependent command a bounded number of times.
#   usage: scripts/retry.sh [--attempts N] [--backoff SECONDS] [--transient-only] [--stream] [--log FILE] -- COMMAND [ARGS...]
#
# Each attempt writes its output to the log file (default: a temp file, removed on exit); --stream also
# echoes it live. Sleeps SECONDS * attempt between attempts and exits with the last attempt's status.
# Without --transient-only every failure is retried. With it, a failure is retried only when its output
# matches a known transient error (HTTP 5xx or gateway timeouts, Gradle/Maven resolution errors, dropped
# connections), so a genuine test failure runs once. The exit status is never changed by the retry.
#
# Exit status is read from the command itself, so this script deliberately does not use errexit.
set -uo pipefail

TRANSIENT_RE='HTTP(/[0-9.]+)? (Error )?50[0-9]|Gateway Time-?out|Bad Gateway|Service Unavailable|Received status code 5[0-9][0-9]|Could not (resolve|GET|HEAD|download|transfer)|Read timed out|Connection (timed out|reset|refused)|Temporary failure in name resolution|Name or service not known|Remote host terminated the handshake|Premature end of Content-Length|RemoteDisconnected|Max retries exceeded|urlopen error|SocketTimeoutException|curl: \((6|7|28|35|52|56|92)\)'

attempts=3
backoff=30
transient_only=0
stream=0
log=""
while [ $# -gt 0 ]; do
  case "$1" in
    --attempts) attempts="${2:?--attempts needs a number}"; shift 2 ;;
    --backoff) backoff="${2:?--backoff needs seconds}"; shift 2 ;;
    --transient-only) transient_only=1; shift ;;
    --stream) stream=1; shift ;;
    --log) log="${2:?--log needs a file}"; shift 2 ;;
    --) shift; break ;;
    *) echo "error: unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ $# -gt 0 ] || { echo "usage: $0 [options] -- COMMAND [ARGS...]" >&2; exit 2; }
[[ "$attempts" =~ ^[1-9][0-9]*$ ]] || { echo "error: --attempts must be a positive integer" >&2; exit 2; }
[[ "$backoff" =~ ^[0-9]+$ ]] || { echo "error: --backoff must be a number of seconds" >&2; exit 2; }

if [ -z "$log" ]; then
  log="$(mktemp)"
  trap 'rm -f "$log"' EXIT
fi

attempt=1
while true; do
  echo "attempt $attempt/$attempts: $1"
  rc=0
  if [ "$stream" -eq 1 ]; then
    "$@" 2>&1 | tee "$log"
    rc=${PIPESTATUS[0]}
  else
    "$@" >"$log" 2>&1 || rc=$?
  fi
  if [ "$rc" -eq 0 ]; then
    echo "attempt $attempt/$attempts succeeded"
    exit 0
  fi
  if [ "$attempt" -ge "$attempts" ]; then
    echo "attempt $attempt/$attempts failed (exit $rc); no attempts left" >&2
    if [ "$stream" -eq 0 ]; then tail -n 80 "$log" >&2; fi
    exit "$rc"
  fi
  if [ "$transient_only" -eq 1 ] && ! grep -Eq "$TRANSIENT_RE" "$log"; then
    echo "attempt $attempt/$attempts failed (exit $rc) with a non-transient error; not retrying" >&2
    if [ "$stream" -eq 0 ]; then tail -n 80 "$log" >&2; fi
    exit "$rc"
  fi
  wait_s=$((backoff * attempt))
  echo "attempt $attempt/$attempts failed (exit $rc); retrying in ${wait_s}s" >&2
  sleep "$wait_s"
  attempt=$((attempt + 1))
done
