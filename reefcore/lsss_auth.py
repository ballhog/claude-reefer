"""LSSS machine key for Claude Reefer (LSSS Group 7 sign-in, 2026-10-14).

Importing this module adds `Authorization: Bearer <key>` to every urllib request
this process makes to the LSSS, and to nothing else. The key lives in
/etc/reefcore/lsss.key (root, mode 600) and is read on each request, so a new key
takes effect without restarting nz-home. No key file = no header, which is fine
while the LSSS is in "Public view" (reads open); in "Sign-in only" the key is what
keeps the readings flowing.

Get or replace the key:  /opt/reefcore/lsss-key.py request   (then approve its code)
Check it:                /opt/reefcore/lsss-key.py check
"""
import os
import urllib.request

KEY_FILE = "/etc/reefcore/lsss.key"
LSSS_HOSTS = {h.strip() for h in os.environ.get(
    "LSSS_HOSTS", "10.0.0.228:8000,100.79.0.32:8000").split(",") if h.strip()}


def key():
    try:
        with open(KEY_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


class _LsssKey(urllib.request.BaseHandler):
    handler_order = 100          # before the default handlers send the request

    def http_request(self, req):
        if req.host in LSSS_HOSTS and not req.has_header("Authorization"):
            k = key()
            if k:
                req.add_unredirected_header("Authorization", f"Bearer {k}")
        return req

    https_request = http_request


urllib.request.install_opener(urllib.request.build_opener(_LsssKey()))
