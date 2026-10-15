#!/bin/sh
# Refresh the repo from the live code, then commit + push. Run from vincent:
#   pct exec 103 -- sh /root/reef-log/stage-code.sh    (mccrae copies its code to reef_lab/.code-drop)
#   pct exec 101 -- /opt/claude-reefer/publish.sh "message"
set -e
cd /opt/claude-reefer
cp -p /opt/reefcore/*.py /opt/reefcore/*.sh reefcore/ 2>/dev/null || true
cp /root/reef-lab/.code-drop/mccrae/* mccrae/ 2>/dev/null || true
for f in hydros-pull reefchem-pull reef-report; do cp -p /etc/cron.d/$f cron/$f 2>/dev/null || true; done
if grep -rIl -E "AAE[A-Za-z0-9_-]{30}|lsk_[A-Za-z0-9_-]{20}|sk-ant-|BEGIN (OPENSSH|RSA) PRIVATE|[0-9]{9,10}:AA[A-Za-z0-9_-]{30}" reefcore mccrae cron; then
  echo "SECRET-LOOKING TEXT FOUND, not committing"; exit 1; fi
git add -A
git -c user.name=ballhog -c user.email=ballhog@users.noreply.github.com commit -q -m "${1:-Update from live code}

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WkhS4K9euYdppVdkEd3d5z" || echo "nothing to commit"
git remote get-url origin >/dev/null 2>&1 && git push -q origin main 2>&1 || echo "no remote yet"
git log --oneline -1
