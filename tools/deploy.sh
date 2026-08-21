#!/usr/bin/env bash
# Deploya arbetsträdet till Pi:n och starta om tjänsten — så Mac och Pi kör
# SAMMA version. Stämplar git-commit på Pi:n (DEPLOYED_VERSION) och verifierar
# att den matchar Macen. Kör ett snabbt testsvep på Pi:n innan omstart.
#
#   tools/deploy.sh                 # → pi@discopi.local
#   tools/deploy.sh pi@192.168.68.66
set -euo pipefail
PI="${1:-pi@discopi.local}"
DEST="/home/pi/discovery2-diag"
cd "$(dirname "$0")/.."

commit="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
dirty=""
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
  dirty="+dirty"
fi
stamp="${commit}${dirty}"
echo "→ deployar ${stamp} till ${PI}:${DEST}"
[ -n "$dirty" ] && echo "  ⚠ OCOMMITTADE ändringar deployas — committa för en ren version"

# --delete på src så borttagna moduler försvinner även på Pi:n (exakt spegling).
rsync -az --delete src/ "${PI}:${DEST}/src/"
rsync -az tools/ "${PI}:${DEST}/tools/"
rsync -az tests/ "${PI}:${DEST}/tests/"
rsync -az pyproject.toml "${PI}:${DEST}/pyproject.toml" 2>/dev/null || true

# Testa på Pi:n → stämpla version → starta om tjänsten.
ssh "$PI" "set -e
  cd ${DEST}
  python3 -m pytest tests/test_web.py tests/test_transport.py -q 2>&1 | tail -1
  echo '${stamp}' > DEPLOYED_VERSION
  sudo systemctl restart d2diag.service
  sleep 3
  echo \"Pi: \$(cat DEPLOYED_VERSION) · tjänst \$(systemctl is-active d2diag.service)\""

remote="$(ssh "$PI" cat "${DEST}/DEPLOYED_VERSION" 2>/dev/null || echo '?')"
if [ "$remote" = "$stamp" ]; then
  echo "✓ Mac ${stamp} = Pi ${remote}"
else
  echo "✗ VERSIONER SKILJER: Mac ${stamp} ≠ Pi ${remote}"; exit 1
fi
