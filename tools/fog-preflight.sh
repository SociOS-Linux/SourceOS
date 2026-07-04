#!/usr/bin/env bash
set -euo pipefail

FOG_ROOT="${FOG_ROOT:-/srv/fog}"
FOG_DEVICE_ALLOWLIST="${FOG_DEVICE_ALLOWLIST:-}"

required_dirs=(
  projects
  models
  datasets
  topics
  vector
  cache
  logs
  secrets
  tmp
)

failures=0

note() {
  printf '%s\n' "$*"
}

warn() {
  printf 'WARN: %s\n' "$*" >&2
}

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  failures=$((failures + 1))
}

note "Fog preflight: root=${FOG_ROOT}"

for dir in "${required_dirs[@]}"; do
  path="${FOG_ROOT}/${dir}"
  if [[ -d "${path}" ]]; then
    note "ok dir ${path}"
  else
    fail "missing dir ${path}"
  fi
done

if command -v vgs >/dev/null 2>&1; then
  if vgs >/dev/null 2>&1; then
    note "ok lvm vgs"
  else
    fail "vgs command failed"
  fi
else
  fail "missing lvm tool: vgs"
fi

if command -v podman >/dev/null 2>&1; then
  note "ok container host podman"
elif command -v docker >/dev/null 2>&1; then
  note "ok container host docker"
else
  fail "missing container host (expected podman or docker)"
fi

if [[ -n "${FOG_DEVICE_ALLOWLIST}" ]]; then
  IFS=',' read -r -a devs <<< "${FOG_DEVICE_ALLOWLIST}"
  for dev in "${devs[@]}"; do
    if [[ -b "${dev}" ]]; then
      note "ok allowlisted block device ${dev}"
    else
      fail "allowlisted device is not a block device: ${dev}"
    fi
  done
else
  warn "FOG_DEVICE_ALLOWLIST unset; storage bootstrap checks are limited"
fi

if [[ ${failures} -gt 0 ]]; then
  fail "fog preflight detected ${failures} failure(s)"
  exit 1
fi

note "Fog preflight passed"
