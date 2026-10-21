"""Smoke check for the synthetic-data demo (docs/DEMO.md), used by CI after
scripts/demo-up.sh: a seeded clinic signs in and has two SIMULATED devices
and two simulated readings waiting for clinician review.

    python3 scripts/demo_check.py http://127.0.0.1:8000/api/v1 owner@sunrise-demo.example.com
"""
import json
import sys
import urllib.request

api, email = sys.argv[1], sys.argv[2]
def call(path, body=None, tok=None):
    req = urllib.request.Request(api + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {tok}"} if tok else {})})
    with urllib.request.urlopen(req) as r:
        return json.load(r)
tok = call("/auth/login", {"email": email, "password": "Demo-Sunrise-2026!"})["tokens"]["access_token"]
sims = sum(d["is_simulator"] for d in call("/devices", tok=tok))
encs = call("/encounters?status=open", tok=tok)["items"]
pending = sum(len(call(f"/device-readings?encounter_id={e['id']}&status=pending_review", tok=tok))
              for e in encs)
print(f"simulated devices={sims} pending readings={pending}")
assert (sims, pending) == (2, 2), "expected 2 simulated devices and 2 readings pending review"
