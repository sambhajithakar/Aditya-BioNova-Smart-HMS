"""Smoke check for the synthetic-data demo (docs/DEMO.md), used by CI after
scripts/demo-up.sh: a seeded clinic signs in and has two SIMULATED devices
and two simulated readings waiting for clinician review.

    python3 scripts/demo_check.py http://127.0.0.1:8000/api/v1 owner@sunrise-demo.example.com
"""
import json
import sys
import urllib.request

PASSWORD = "Demo-Sunrise-2026!"  # synthetic demo accounts only


def call(api: str, path: str, body: dict | None = None, tok: str | None = None):
    headers = {"Content-Type": "application/json"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    data = json.dumps(body).encode() if body else None
    with urllib.request.urlopen(urllib.request.Request(api + path, data=data,
                                                       headers=headers)) as r:
        return json.load(r)


def main(api: str, email: str) -> None:
    login = call(api, "/auth/login", {"email": email, "password": PASSWORD})
    tok = login["tokens"]["access_token"]
    sims = sum(d["is_simulator"] for d in call(api, "/devices", tok=tok))
    encounters = call(api, "/encounters?status=open", tok=tok)["items"]
    pending = sum(
        len(call(api, f"/device-readings?encounter_id={e['id']}&status=pending_review",
                 tok=tok))
        for e in encounters)
    print(f"simulated devices={sims} pending readings={pending}")
    if (sims, pending) != (2, 2):
        sys.exit("expected 2 simulated devices and 2 readings pending review")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
