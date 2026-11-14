#!/usr/bin/env bash
# Open an issue for a failed release run, or comment on the open issue for the same Firefox version.
# Runs in the report-failure job of release.yml. It never publishes anything.
#   env: GH_TOKEN, REPO (OWNER/REPO), RUN_ID, RUN_URL, FIREFOX_VERSION (empty when detection failed)
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

: "${REPO:?REPO is required}" "${RUN_ID:?RUN_ID is required}" "${RUN_URL:?RUN_URL is required}"
fx="${FIREFOX_VERSION:-}"
title="$(python3 -c 'import sys; from scripts.release.failure_report import issue_title; print(issue_title(sys.argv[1]))' "$fx")"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/logs"

gh api "repos/$REPO/actions/runs/$RUN_ID/jobs?per_page=100" >"$work/jobs.json"
python3 -m scripts.release.failure_report failed-ids --jobs "$work/jobs.json" >"$work/failed-ids.txt"
while read -r job_id; do
  [ -n "$job_id" ] || continue
  gh api "repos/$REPO/actions/jobs/$job_id/logs" >"$work/logs/$job_id.log" ||
    echo "warning: no log for job $job_id" >&2
done <"$work/failed-ids.txt"

python3 -m scripts.release.failure_report body --jobs "$work/jobs.json" --logs "$work/logs" \
  --firefox "$fx" --run-url "$RUN_URL" --out "$work/body.md"

gh issue list --repo "$REPO" --state open --limit 200 --json number,title >"$work/issues.json"
number="$(python3 -m scripts.release.failure_report find-issue --title "$title" <"$work/issues.json")"
if [ -n "$number" ]; then
  gh issue comment "$number" --repo "$REPO" --body-file "$work/body.md"
  echo "commented on open issue #$number: $title"
else
  gh issue create --repo "$REPO" --title "$title" --body-file "$work/body.md"
fi
