import logging
from ..models.raw_event import RawEvent
from ..registry.extension_registry import ExtensionRegistry

logger = logging.getLogger(__name__)


class EventRouter:
    def __init__(self, registry: ExtensionRegistry) -> None:
        self.registry = registry

    def route(self, raw: RawEvent) -> str:
        """
        Returns the confirmed extension_id to use.
        Always returns a valid extension_id (falls back to 'generic').
        Never raises. Never returns None.
        """
        # Phase 0 — Explicit override
        if raw.ingestion.source_hint is not None:
            candidate = self.registry.get(raw.ingestion.source_hint)
            if candidate is not None:
                try:
                    if candidate.can_process(raw):
                        return raw.ingestion.source_hint
                except Exception as e:
                    logger.warning("can_process() on source_hint '%s' raised: %s", raw.ingestion.source_hint, e)
            logger.warning("source_hint '%s' did not match; continuing detection", raw.ingestion.source_hint)

        # Phase 1 — Cheap signal scoring (no regex, no parsing)
        candidates: list[tuple[str, int, int]] = []
        payload_prefix_window = raw.payload[:300]

        for ext_id, hints in self.registry.all_hints():
            # Transport filter (hard filter — skip if incompatible)
            if hints.transports and raw.ingestion.transport not in hints.transports:
                continue

            score = 0
            # Prefix check (fast O(1) string comparison)
            for prefix in hints.prefixes:
                if raw.payload.startswith(prefix):
                    score += 30
                    break

            # Contains check (substring in first 300 chars only)
            for substring in hints.contains:
                if substring in payload_prefix_window:
                    score += 20
                    break

            if score > 0:
                candidates.append((ext_id, score, hints.priority))

        # Sort candidates: lower priority first (vendor-specific priority 10 before generic 50),
        # then higher score first
        candidates.sort(key=lambda x: (x[2], -x[1]))

        # Phase 2 — can_process() confirmation (at most 5 candidates)
        for ext_id, _score, _prio in candidates[:5]:
            ext = self.registry.get(ext_id)
            if ext is None:
                continue
            try:
                if ext.can_process(raw):
                    return ext_id
            except Exception as e:
                logger.warning("can_process() on %s raised: %s", ext_id, e)
                continue

        # Phase 3 — Fallback
        return "generic"
