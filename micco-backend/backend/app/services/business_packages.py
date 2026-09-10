"""The package catalogue the portal may suggest from.

Two jobs, kept together because they are two views of the same rows:

- build the compact digest injected into the system prompt, so the model can
  pick packages inside the single answer call rather than a second round trip,
- turn a model-chosen id list into cards a customer may see.

The digest is deliberately small. It carries id, name, category, target
customer and the first sentence of the summary — enough to match a described
need, but not the whole catalogue, because it is prepended to every question.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_package import BusinessPackage

logger = logging.getLogger(__name__)

# At most this many cards reach the customer. More than three stops being a
# suggestion and starts being a catalogue dump.
MAX_RECOMMENDATIONS = 3

# Only the first sentence of each summary goes into the digest.
_SENTENCE_ENDINGS = (". ", "! ", "? ", ".\n")


async def get_active_packages(db: AsyncSession) -> list[BusinessPackage]:
    """The catalogue, in display order. Inactive offers are never returned."""
    result = await db.execute(
        select(BusinessPackage)
        .where(BusinessPackage.is_active.is_(True))
        .order_by(BusinessPackage.sort_order.asc(), BusinessPackage.id.asc())
    )
    return list(result.scalars().all())


def first_sentence(text: str | None, limit: int = 220) -> str:
    """First sentence of `text`, truncated. Empty string for no text."""
    if not text:
        return ""
    cleaned = " ".join(text.split())
    for ending in _SENTENCE_ENDINGS:
        index = cleaned.find(ending)
        if index != -1:
            cleaned = cleaned[: index + 1]
            break
    return cleaned[:limit].strip()


def build_catalog_digest(packages: list[BusinessPackage]) -> str:
    """One line per package, for the system prompt.

    Empty string for an empty catalogue, which is how the prompt builder knows
    to leave the suggestion contract out entirely.
    """
    lines: list[str] = []
    for package in packages:
        parts = [f"[{package.id}] {package.name}", package.category]
        if package.target_customer:
            parts.append(f"phù hợp với: {first_sentence(package.target_customer, 120)}")
        summary = first_sentence(package.summary)
        if summary:
            parts.append(summary)
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)


def resolve_recommendations(
    package_ids: list[int], packages: list[BusinessPackage]
) -> list[BusinessPackage]:
    """Turn the model's chosen ids into real, active packages.

    Default-deny, in the model's direction: an id that is not in the active
    catalogue is dropped rather than looked up. The model produced these ids
    from a digest, so it can hallucinate one, reuse a stale one, or repeat
    itself — none of which may become a card.
    """
    by_id = {package.id: package for package in packages}

    resolved: list[BusinessPackage] = []
    seen: set[int] = set()
    for package_id in package_ids:
        if package_id in seen:
            continue
        package = by_id.get(package_id)
        if package is None:
            logger.info(
                "business chat: dropping suggested package id %s "
                "(not in the active catalogue)",
                package_id,
            )
            continue
        seen.add(package_id)
        resolved.append(package)
        if len(resolved) == MAX_RECOMMENDATIONS:
            break
    return resolved


def to_card(package: BusinessPackage) -> dict:
    """The customer-facing projection of a package.

    Built field by field rather than dumping the row, so a column added later
    (an internal note, a margin) cannot reach a customer by default.
    """
    return {
        "id": package.id,
        "name": package.name,
        "category": package.category,
        "summary": package.summary,
        "target_customer": package.target_customer,
        "highlights": list(package.highlights or []),
        "price_note": package.price_note,
    }
