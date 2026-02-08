import argparse
import asyncio
import csv
import logging
import os
import sys
from dataclasses import dataclass

import psycopg

# Add backend root to sys.path to allow imports from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.shared.config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class OrphanThread:
    thread_id: str
    title: str | None
    updated_at: str | None


@dataclass
class MigrationResult:
    thread_id: str
    owner_uid: str
    copied_checkpoints: int = 0
    copied_blobs: int = 0
    copied_writes: int = 0
    deleted_legacy_checkpoints: int = 0
    deleted_legacy_blobs: int = 0
    deleted_legacy_writes: int = 0
    updated_threads: int = 0


def load_mapping_csv(path: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "thread_id" not in reader.fieldnames or "owner_uid" not in reader.fieldnames:
            raise ValueError("CSV must contain 'thread_id' and 'owner_uid' columns")
        for row in reader:
            thread_id = (row.get("thread_id") or "").strip()
            owner_uid = (row.get("owner_uid") or "").strip()
            if not thread_id or not owner_uid:
                continue
            mapping[thread_id] = owner_uid
    return mapping


async def fetch_orphan_threads(conn: psycopg.AsyncConnection) -> list[OrphanThread]:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT thread_id, title, updated_at
            FROM threads
            WHERE owner_uid IS NULL
            ORDER BY updated_at DESC;
            """
        )
        rows = await cur.fetchall()
    return [
        OrphanThread(
            thread_id=row[0],
            title=row[1],
            updated_at=row[2].isoformat() if row[2] else None,
        )
        for row in rows
    ]


async def fetch_existing_uids(conn: psycopg.AsyncConnection, uids: set[str]) -> set[str]:
    if not uids:
        return set()
    async with conn.cursor() as cur:
        await cur.execute("SELECT uid FROM users WHERE uid = ANY(%s);", (list(uids),))
        rows = await cur.fetchall()
    return {row[0] for row in rows}


async def has_task_path_column(conn: psycopg.AsyncConnection) -> bool:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'checkpoint_writes'
              AND column_name = 'task_path'
            LIMIT 1;
            """
        )
        row = await cur.fetchone()
    return bool(row)


async def migrate_one_thread(
    conn: psycopg.AsyncConnection,
    thread_id: str,
    owner_uid: str,
    *,
    writes_has_task_path: bool,
) -> MigrationResult:
    result = MigrationResult(thread_id=thread_id, owner_uid=owner_uid)
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO checkpoints (
                thread_id,
                checkpoint_ns,
                checkpoint_id,
                parent_checkpoint_id,
                type,
                checkpoint,
                metadata
            )
            SELECT
                thread_id,
                %s,
                checkpoint_id,
                parent_checkpoint_id,
                type,
                checkpoint,
                metadata
            FROM checkpoints
            WHERE thread_id = %s
              AND (checkpoint_ns = '' OR checkpoint_ns IS NULL)
            ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id) DO NOTHING;
            """,
            (owner_uid, thread_id),
        )
        result.copied_checkpoints = cur.rowcount

        await cur.execute(
            """
            INSERT INTO checkpoint_blobs (
                thread_id,
                checkpoint_ns,
                channel,
                version,
                type,
                blob
            )
            SELECT
                thread_id,
                %s,
                channel,
                version,
                type,
                blob
            FROM checkpoint_blobs
            WHERE thread_id = %s
              AND (checkpoint_ns = '' OR checkpoint_ns IS NULL)
            ON CONFLICT (thread_id, checkpoint_ns, channel, version) DO NOTHING;
            """,
            (owner_uid, thread_id),
        )
        result.copied_blobs = cur.rowcount

        if writes_has_task_path:
            await cur.execute(
                """
                INSERT INTO checkpoint_writes (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    task_id,
                    idx,
                    channel,
                    type,
                    blob,
                    task_path
                )
                SELECT
                    thread_id,
                    %s,
                    checkpoint_id,
                    task_id,
                    idx,
                    channel,
                    type,
                    blob,
                    task_path
                FROM checkpoint_writes
                WHERE thread_id = %s
                  AND (checkpoint_ns = '' OR checkpoint_ns IS NULL)
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, idx) DO NOTHING;
                """,
                (owner_uid, thread_id),
            )
        else:
            await cur.execute(
                """
                INSERT INTO checkpoint_writes (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    task_id,
                    idx,
                    channel,
                    type,
                    blob
                )
                SELECT
                    thread_id,
                    %s,
                    checkpoint_id,
                    task_id,
                    idx,
                    channel,
                    type,
                    blob
                FROM checkpoint_writes
                WHERE thread_id = %s
                  AND (checkpoint_ns = '' OR checkpoint_ns IS NULL)
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, idx) DO NOTHING;
                """,
                (owner_uid, thread_id),
            )
        result.copied_writes = cur.rowcount

        await cur.execute(
            """
            DELETE FROM checkpoint_writes
            WHERE thread_id = %s
              AND (checkpoint_ns = '' OR checkpoint_ns IS NULL);
            """,
            (thread_id,),
        )
        result.deleted_legacy_writes = cur.rowcount

        await cur.execute(
            """
            DELETE FROM checkpoint_blobs
            WHERE thread_id = %s
              AND (checkpoint_ns = '' OR checkpoint_ns IS NULL);
            """,
            (thread_id,),
        )
        result.deleted_legacy_blobs = cur.rowcount

        await cur.execute(
            """
            DELETE FROM checkpoints
            WHERE thread_id = %s
              AND (checkpoint_ns = '' OR checkpoint_ns IS NULL);
            """,
            (thread_id,),
        )
        result.deleted_legacy_checkpoints = cur.rowcount

        await cur.execute(
            """
            UPDATE threads
            SET owner_uid = %s, updated_at = NOW()
            WHERE thread_id = %s
              AND owner_uid IS NULL;
            """,
            (owner_uid, thread_id),
        )
        result.updated_threads = cur.rowcount

    return result


async def run() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill threads.owner_uid and migrate LangGraph checkpoints "
            "from legacy checkpoint_ns='' to checkpoint_ns=<owner_uid>."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Omit this flag to run report-only mode.",
    )
    parser.add_argument(
        "--mapping-csv",
        type=str,
        default=None,
        help="CSV file with columns: thread_id,owner_uid",
    )
    parser.add_argument(
        "--default-owner-uid",
        type=str,
        default=None,
        help="Fallback UID to assign when thread_id is not present in mapping CSV.",
    )
    parser.add_argument(
        "--unresolved-csv",
        type=str,
        default=None,
        help="Output unresolved orphan threads to CSV (thread_id,title,updated_at).",
    )
    args = parser.parse_args()

    conn_str = settings.connection_string
    if not conn_str:
        logger.error("POSTGRES_DB_URI is not set.")
        return 1

    mapping: dict[str, str] = {}
    if args.mapping_csv:
        mapping = load_mapping_csv(args.mapping_csv)
        logger.info("Loaded %s mapping rows from %s", len(mapping), args.mapping_csv)

    if args.apply and not mapping and not args.default_owner_uid:
        logger.error("--apply requires either --mapping-csv or --default-owner-uid.")
        return 1

    async with await psycopg.AsyncConnection.connect(conn_str, autocommit=False) as conn:
        orphans = await fetch_orphan_threads(conn)
        if not orphans:
            logger.info("No orphan threads found. Nothing to backfill.")
            return 0

        logger.info("Found %s orphan threads (owner_uid IS NULL).", len(orphans))

        assignments: dict[str, str] = {}
        unresolved: list[OrphanThread] = []
        for thread in orphans:
            owner_uid = mapping.get(thread.thread_id) or args.default_owner_uid
            if owner_uid:
                assignments[thread.thread_id] = owner_uid
            else:
                unresolved.append(thread)

        existing_uids = await fetch_existing_uids(conn, set(assignments.values()))
        invalid_uid_threads: list[tuple[OrphanThread, str]] = []
        valid_assignments: dict[str, str] = {}
        orphan_map = {t.thread_id: t for t in orphans}
        for thread_id, uid in assignments.items():
            if uid in existing_uids:
                valid_assignments[thread_id] = uid
            else:
                invalid_uid_threads.append((orphan_map[thread_id], uid))

        logger.info("Assignable threads: %s", len(valid_assignments))
        logger.info("Unresolved threads (no mapping): %s", len(unresolved))
        logger.info("Invalid UID mappings: %s", len(invalid_uid_threads))

        if unresolved and args.unresolved_csv:
            with open(args.unresolved_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["thread_id", "title", "updated_at"])
                for row in unresolved:
                    writer.writerow([row.thread_id, row.title or "", row.updated_at or ""])
            logger.info("Wrote unresolved threads to %s", args.unresolved_csv)

        for row, uid in invalid_uid_threads[:20]:
            logger.warning("Invalid UID mapping: thread_id=%s -> uid=%s", row.thread_id, uid)
        if len(invalid_uid_threads) > 20:
            logger.warning("... and %s more invalid mappings", len(invalid_uid_threads) - 20)

        if not args.apply:
            logger.info("Report mode only. Re-run with --apply to execute migration.")
            return 0

        writes_has_task_path = await has_task_path_column(conn)
        logger.info("checkpoint_writes.task_path exists: %s", writes_has_task_path)

        migrated = 0
        failed = 0
        for thread_id, owner_uid in valid_assignments.items():
            try:
                result = await migrate_one_thread(
                    conn,
                    thread_id,
                    owner_uid,
                    writes_has_task_path=writes_has_task_path,
                )
                await conn.commit()
                migrated += 1
                logger.info(
                    (
                        "Migrated thread=%s owner_uid=%s "
                        "(cp:%s blobs:%s writes:%s / deleted legacy cp:%s blobs:%s writes:%s / threads:%s)"
                    ),
                    result.thread_id,
                    result.owner_uid,
                    result.copied_checkpoints,
                    result.copied_blobs,
                    result.copied_writes,
                    result.deleted_legacy_checkpoints,
                    result.deleted_legacy_blobs,
                    result.deleted_legacy_writes,
                    result.updated_threads,
                )
            except Exception as e:
                await conn.rollback()
                failed += 1
                logger.exception("Failed to migrate thread_id=%s: %s", thread_id, e)

        logger.info("Backfill finished. migrated=%s failed=%s", migrated, failed)
        if unresolved:
            logger.warning("%s threads remain unresolved (owner mapping missing).", len(unresolved))
        if invalid_uid_threads:
            logger.warning("%s threads unresolved due to invalid uid mapping.", len(invalid_uid_threads))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run()))
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        raise SystemExit(130)
