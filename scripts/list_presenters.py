"""List the avatar looks on your HeyGen account with their ids (read-only, costs nothing).

    HEYGEN_API_KEY=... python scripts/list_presenters.py [search words] > presenters.csv

The `id` column is what goes in HEYGEN_DEFAULT_AVATAR_ID, or what the app's presenter picker stores for a project."""

import csv
import os
import sys

import httpx

key = os.environ.get("HEYGEN_API_KEY")
if not key:
    sys.exit("Set HEYGEN_API_KEY in the environment (do not paste it into chats or commit it).")
words = [w.lower() for w in sys.argv[1:]]
out = csv.writer(sys.stdout)
out.writerow(["id", "name", "gender", "orientation", "preview_image_url"])
token = None
with httpx.Client(base_url="https://api.heygen.com", headers={"x-api-key": key}, timeout=30) as c:
    while True:
        r = c.get("/v3/avatars/looks", params={"limit": 50, **({"token": token} if token else {})})
        r.raise_for_status()
        body = r.json()
        for it in body.get("data", []):
            if it.get("status", "completed") == "completed" and all(w in (it.get("name") or "").lower() for w in words):
                out.writerow([it["id"], it.get("name"), it.get("gender"), it.get("preferred_orientation"), it.get("preview_image_url")])
        token = body.get("next_token")
        if not body.get("has_more") or not token:
            break
