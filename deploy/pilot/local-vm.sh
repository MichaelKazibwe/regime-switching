#!/bin/sh
# Operate only the dedicated, loopback-only pilot in Colima's regime-pilot VM.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
task_config="$task_root/var/deployment/20261114/docker-cli"
task_env="$task_root/var/deployment/20261114/local.env"
task_socket="unix://$HOME/.colima/regime-pilot/docker.sock"
if [ ! -f "$task_env" ]; then
  echo 'Local image configuration is missing; finish the image build first.' >&2
  exit 1
fi
task_action=${1:-status}
if [ "$#" -gt 0 ]; then shift; fi
compose() {
  docker --config "$task_config" --host "$task_socket" compose \
    --project-name regime-pilot-local --env-file "$task_env" \
    -f "$task_root/deploy/pilot/compose.local.yaml" "$@"
}
case "$task_action" in
  start) compose up -d ;;
  stop) compose stop ;;
  status) compose ps ;;
  logs) compose logs --tail 100 ;;
  invite) compose exec pilot python pilot_admin.py add-user "$@" ;;
  users) compose exec pilot python pilot_admin.py list-users ;;
  revoke) compose exec pilot python pilot_admin.py revoke-user "$@" ;;
  preflight) compose exec pilot python pilot_preflight.py --output var/pilot/preflight.json ;;
  *) echo 'Usage: sh deploy/pilot/local-vm.sh {start|stop|status|logs|invite USER [--role tester|viewer]|users|revoke USER|preflight}' >&2; exit 2 ;;
esac
