"""
Async audit event queue and background drain worker.

The chat handler puts AuditEvent ORM instances onto the queue (non-blocking).
The worker drains the queue in batches every second and persists them to the DB.
If all DB retries fail, events are written to a local fallback JSONL file so
nothing is permanently lost.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Optional

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

FALLBACK_LOG_PATH = "audit_fallback.jsonl"
BATCH_SIZE = 50
DRAIN_INTERVAL_SECONDS = 1.0
MAX_RETRIES = 3

# The queue is module-level so any part of the app can import and use it.
audit_queue: asyncio.Queue = asyncio.Queue(maxsize=10_000)


def _event_to_dict(event) -> dict:
    """Serialise an AuditEvent ORM object to a plain dict for the fallback log."""
    return {
        "id": event.id,
        "timestamp": event.timestamp.isoformat() if isinstance(event.timestamp, datetime) else str(event.timestamp),
        "user_id": event.user_id,
        "user_role": event.user_role,
        "department": event.department,
        "session_id": event.session_id,
        "prompt_hash": event.prompt_hash,
        "prompt_length": event.prompt_length,
        "threats_detected": event.threats_detected,
        "sanitization_applied": event.sanitization_applied,
        "blocked": event.blocked,
        "block_reason": event.block_reason,
        "security_level_used": event.security_level_used,
        "confidence_score": event.confidence_score,
        "processing_time_ms": event.processing_time_ms,
        "vetting_time_ms": event.vetting_time_ms,
        "llm_time_ms": event.llm_time_ms,
        "model_used": event.model_used,
        "tokens_used": event.tokens_used,
        "action": event.action,
    }


def _write_fallback(batch: list) -> None:
    """Append failed events to a local JSONL file as a last resort."""
    try:
        with open(FALLBACK_LOG_PATH, "a", encoding="utf-8") as f:
            for event in batch:
                f.write(json.dumps(_event_to_dict(event)) + "\n")
        logger.warning(f"Wrote {len(batch)} audit events to fallback log: {FALLBACK_LOG_PATH}")
    except Exception as e:
        logger.error(f"Failed to write fallback audit log: {e}")


async def audit_worker(session_factory) -> None:
    """
    Long-running coroutine that drains audit_queue and batch-writes to the DB.
    Start with asyncio.create_task() in the app lifespan.
    """
    logger.info("Audit worker started")
    batch: list = []

    while True:
        # Collect events until batch is full or drain interval elapses
        try:
            event = await asyncio.wait_for(audit_queue.get(), timeout=DRAIN_INTERVAL_SECONDS)
            batch.append(event)

            # Drain any additional events that are already waiting
            while not audit_queue.empty() and len(batch) < BATCH_SIZE:
                batch.append(audit_queue.get_nowait())

        except asyncio.TimeoutError:
            pass  # No new events within the interval — flush what we have

        if not batch:
            continue

        # Attempt DB write with exponential backoff retries
        persisted = False
        for attempt in range(MAX_RETRIES):
            try:
                async with session_factory() as session:
                    session.add_all(batch)
                    await session.commit()
                persisted = True
                logger.debug(f"Persisted {len(batch)} audit events")
                break
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"Audit DB write attempt {attempt + 1} failed: {e}. Retrying in {wait}s")
                await asyncio.sleep(wait)

        if not persisted:
            logger.error(f"All {MAX_RETRIES} audit write attempts failed — writing to fallback log")
            _write_fallback(batch)

        batch = []
