"""Database backup: pg_dump (custom format) -> checksum + manifest -> object storage (or a local folder).

  python scripts/backup.py --out /backups                 # local folder
  python scripts/backup.py --upload                       # S3-compatible bucket from STORAGE_* env (Cloudflare R2)
Environment: DATABASE_URL (asyncpg form is fine). Retention: --keep N newest backups are kept.
Run it daily from a Railway cron service. A backup that was never restored is not a backup: see restore_test.py.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

TABLES_SQL = "select relname, n_live_tup from pg_stat_user_tables order by relname"


def libpq_url(url: str) -> str:
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def psql(url: str, sql: str) -> list[str]:
    out = subprocess.run(["psql", url, "-At", "-F", "|", "-c", sql], capture_output=True, text=True, check=True).stdout
    return [ln for ln in out.splitlines() if ln]


def row_counts(url: str) -> dict[str, int]:
    tables = [r.split("|")[0] for r in psql(url, "select tablename from pg_tables where schemaname='public' order by 1")]
    return {t: int(psql(url, f'select count(*) from "{t}"')[0]) for t in tables}  # exact counts, not estimates


def alembic_revision(url: str) -> str | None:
    rows = psql(url, "select version_num from alembic_version")
    return rows[0] if rows else None


def make_backup(db_url: str, workdir: Path) -> tuple[Path, dict]:
    url = libpq_url(db_url)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dump = workdir / f"newsagent-{stamp}.dump"
    subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(dump), url], check=True)
    digest = hashlib.sha256(dump.read_bytes()).hexdigest()
    manifest = {
        "file": dump.name, "created_at": datetime.now(UTC).isoformat(), "bytes": dump.stat().st_size, "sha256": digest,
        "alembic_revision": alembic_revision(url), "row_counts": row_counts(url),
    }
    (workdir / f"{dump.name}.json").write_text(json.dumps(manifest, indent=2))
    return dump, manifest


def s3_client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3", endpoint_url=os.environ["STORAGE_ENDPOINT"], aws_access_key_id=os.environ["STORAGE_ACCESS_KEY"],
        aws_secret_access_key=os.environ["STORAGE_SECRET_KEY"], region_name="auto", config=Config(signature_version="s3v4"),
    )


def upload(dump: Path, bucket: str, prefix: str, keep: int) -> None:
    s3 = s3_client()
    for f in (dump, dump.with_name(dump.name + ".json")):
        s3.upload_file(str(f), bucket, f"{prefix}{f.name}")
    objs = sorted(
        (o["Key"] for o in s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", []) if o["Key"].endswith(".dump")),
        reverse=True,
    )
    for old in objs[keep:]:  # retention
        s3.delete_object(Bucket=bucket, Key=old)
        s3.delete_object(Bucket=bucket, Key=old + ".json")


def prune_local(folder: Path, keep: int) -> None:
    for old in sorted(folder.glob("newsagent-*.dump"), reverse=True)[keep:]:
        old.unlink()
        old.with_name(old.name + ".json").unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, help="local folder for backups")
    ap.add_argument("--upload", action="store_true", help="upload to the STORAGE_* bucket")
    ap.add_argument("--prefix", default=f"backups/db/{os.environ.get('ENVIRONMENT', 'local')}/")
    ap.add_argument("--keep", type=int, default=30)
    a = ap.parse_args()
    if not a.out and not a.upload:
        ap.error("give --out and/or --upload")
    db = os.environ["DATABASE_URL"]
    work = a.out or Path(tempfile.mkdtemp(prefix="newsagent-backup-"))
    work.mkdir(parents=True, exist_ok=True)
    dump, manifest = make_backup(db, work)
    print(json.dumps({k: manifest[k] for k in ("file", "bytes", "sha256", "alembic_revision")}))
    if a.upload:
        upload(dump, os.environ["STORAGE_BUCKET"], a.prefix, a.keep)
        print(f"uploaded to {a.prefix}")
    if a.out:
        prune_local(a.out, a.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
