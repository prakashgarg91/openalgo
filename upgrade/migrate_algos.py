#!/usr/bin/env python3
"""
Migration: Regime algo catalogue

Adds the two tables behind /algos:

- algo_deployment  one algo a trader switched on, tied to the sm_strategy row that trades it
- algo_decision    what each algo decided each day and why (also the track record)

Both are new, so there is nothing to backfill. init_db() in database/algo_db.py
creates them on the next start; this script is what reaches an installation
upgraded with `git pull` and checked before it is started.

The DDL is taken from the ORM metadata so it cannot disagree with the models.

This migration is idempotent - safe to run multiple times.

Usage:
    cd upgrade
    uv run migrate_algos.py           # Apply migration
    uv run migrate_algos.py --status  # Report without changing anything
"""

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, PROJECT_ROOT)
# Same SQLite pragmas as the running app (GitHub issue #1726).
import _pragmas  # noqa: F401,E402
from sqlalchemy import create_engine, inspect  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

TABLES = ("algo_deployment", "algo_decision")


def resolve_sqlite_path(db_url):
    """Make a relative sqlite:/// path absolute against the project root."""
    prefix = "sqlite:///"
    if not db_url.startswith(prefix):
        return db_url
    path = db_url[len(prefix) :]
    if os.path.isabs(path):
        return db_url
    return prefix + os.path.join(PROJECT_ROOT, path).replace("\\", "/")


def get_database_url():
    """Read DATABASE_URL from the environment, with the project default."""
    from dotenv import load_dotenv

    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    return resolve_sqlite_path(os.getenv("DATABASE_URL", "sqlite:///db/openalgo.db"))


def missing_tables(engine):
    present = set(inspect(engine).get_table_names())
    return [t for t in TABLES if t not in present]


def status(engine):
    present = set(inspect(engine).get_table_names())
    print("\nAlgo table status")
    print("-" * 46)
    for table in TABLES:
        print(f"  {table:<22} {'present' if table in present else 'MISSING'}")
    print("-" * 46)
    absent = missing_tables(engine)
    if not absent:
        print("Up to date. Nothing to do.")
        return True
    print(f"Migration needed. Would create {len(absent)} table(s): {', '.join(absent)}")
    return False


def apply(engine):
    absent = missing_tables(engine)
    if not absent:
        print("  All algo tables already present.")
        return True

    from database.algo_db import Base

    Base.metadata.create_all(bind=engine, checkfirst=True)
    still_missing = missing_tables(engine)
    if still_missing:
        print(f"  [FAIL] These tables were not created: {', '.join(still_missing)}")
        return False
    for table in absent:
        print(f"  [OK] Created {table}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Algo catalogue schema migration")
    parser.add_argument("--status", action="store_true", help="Report without changing anything")
    args = parser.parse_args()

    db_url = get_database_url()
    shown = db_url if not db_url.startswith("sqlite") else "sqlite://..."
    print("\nAlgo Catalogue Migration")
    print("-" * 46)
    print(f"Database: {shown}")

    engine = create_engine(db_url, poolclass=NullPool)
    try:
        if args.status:
            status(engine)
            return 0
        print("\nApplying migration...")
        ok = apply(engine)
        print("-" * 46)
        print("Migration complete." if ok else "Migration failed. See the messages above.")
        return 0 if ok else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
