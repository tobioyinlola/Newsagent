"""Prove a backup can be restored: restore it into a throwaway database and check it against its manifest.

  python scripts/restore_test.py /backups/newsagent-20261022T101500Z.dump
Needs a Postgres you may create databases on: ADMIN_DATABASE_URL (default: the DATABASE_URL server, db 'postgres').
Checks: file checksum, restore succeeds, alembic revision, EVERY table's row count equals the manifest,
credit ledger sums to each workspace balance, no orphaned rows. Exit code 0 only if all pass.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backup import alembic_revision, libpq_url, psql, row_counts  # noqa: E402


def admin_and_target(db_url: str, name: str) -> tuple[str, str]:
    base = libpq_url(os.environ.get("ADMIN_DATABASE_URL") or db_url)
    admin = re.sub(r"/[^/?]+(\?|$)", r"/postgres\1", base, count=1)
    target = re.sub(r"/[^/?]+(\?|$)", rf"/{name}\1", base, count=1)
    return admin, target


def main(dump_path: str) -> int:
    dump = Path(dump_path)
    manifest = json.loads(dump.with_name(dump.name + ".json").read_text())
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))

    check("checksum matches manifest", hashlib.sha256(dump.read_bytes()).hexdigest() == manifest["sha256"])
    name = f"restore_test_{uuid.uuid4().hex[:8]}"
    admin, target = admin_and_target(os.environ["DATABASE_URL"], name)
    started = time.monotonic()
    subprocess.run(["createdb", "--maintenance-db", admin, name], check=True)
    try:
        r = subprocess.run(["pg_restore", "--no-owner", "--no-privileges", "--exit-on-error", "-d", target, str(dump)], capture_output=True, text=True)
        restore_s = time.monotonic() - started
        check("pg_restore completed", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            check("alembic revision matches", alembic_revision(target) == manifest["alembic_revision"], f"{alembic_revision(target)}")
            counts = row_counts(target)
            diff = {t: (manifest["row_counts"].get(t), counts.get(t)) for t in set(counts) | set(manifest["row_counts"]) if manifest["row_counts"].get(t) != counts.get(t)}
            check(f"row counts match for all {len(counts)} tables", not diff, str(diff))
            bad = psql(target, "select w.id from workspaces w left join (select workspace_id, sum(amount) s from credit_transactions group by 1) t on t.workspace_id=w.id where coalesce(t.s,0) <> w.credit_balance and exists (select 1 from credit_transactions c where c.workspace_id=w.id)")
            check("credit ledger sums to every balance", not bad, str(bad))
            orphans = psql(target, "select count(*) from assets a left join projects p on p.id=a.project_id where p.id is null")[0]
            check("no orphaned assets", orphans == "0", orphans)
            tk = psql(target, "select count(*) from takes t left join projects p on p.id=t.project_id where p.id is null")[0]
            check("no orphaned takes", tk == "0", tk)
    finally:
        subprocess.run(["dropdb", "--maintenance-db", admin, "--if-exists", name], check=False)
    for n, ok, detail in results:
        print(("PASS " if ok else "FAIL ") + n + ("" if ok or not detail else f"  [{detail}]"))
    print(f"restore took {restore_s:.1f}s for {dump.stat().st_size / 1024:.0f} KB")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
