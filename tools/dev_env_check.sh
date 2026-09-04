#!/usr/bin/env bash
set -u

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ps_script="$script_dir/dev_env_check.ps1"
ps_exe=$(command -v powershell.exe || true)

if [[ -z "$ps_exe" ]]; then
  printf '%s\n' '{"windows_interop":false,"error":"powershell.exe is not on PATH"}'
  exit 2
fi

windows_script=$(printf '%s' "$ps_script" | sed -E 's#^/mnt/([A-Za-z])/#\1:\\#; s#/#\\#g')
if ! "$ps_exe" -NoProfile -ExecutionPolicy Bypass -File "$windows_script"; then
  printf '%s\n' '{"windows_interop":false,"error":"Windows executable invocation failed from this WSL session; run tools/repair_wsl_host.ps1 on Windows, or use the Windows PowerShell health-check directly."}' >&2
  exit 3
fi
