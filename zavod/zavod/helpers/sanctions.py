from typing import Optional
from datetime import datetime

from zavod.context import Context
from zavod.entity import Entity
from zavod import helpers as h
from zavod import settings

ALWAYS_FORMATS = ["%Y-%m-%d", "%Y-%m", "%Y"]


def make_sanction(
    context: Context,
    entity: Entity,
    key: Optional[str] = None,
    program: Optional[str] = None,
    program_key: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Entity:
    """Create and return a sanctions object derived from the dataset metadata.

    The country, authority, sourceUrl, and subject entity properties
    are automatically set.

    Args:
        context: The runner context with dataset metadata.
        entity: The entity to which the sanctions object will be linked.
        key: An optional key to be included in the ID of the sanction.
        program: An optional program name.
        program_key: An optional key for looking up the program ID in the YAML configuration.
        start_date: An optional start date for the sanction.
        end_date: An optional end date for the sanction.

    Returns:
        A new entity of type Sanction.
    """
    assert entity.schema.is_a("Thing"), entity.schema
    assert entity.id is not None, entity.id
    dataset = context.dataset
    assert dataset.publisher is not None
    sanction = context.make("Sanction")
    sanction.id = context.make_id("Sanction", entity.id, key)
    sanction.add("entity", entity)
    if dataset.publisher.country != "zz":
        sanction.add("country", dataset.publisher.country)
    sanction.add("authority", dataset.publisher.name)
    sanction.add("sourceUrl", dataset.url)
    if program is not None:
        sanction.set("program", program)
    program_id = context.lookup_value("sanction.program", program_key)
    if program_id is not None:
        program_url = f"https://www.opensanctions.org/programs/{program_id}"
        sanction.add("programUrl", program_url)
        sanction.add("programId", program_id)
    else:
        context.log.warn(f"Program key '{program_key}' not found.", program=program)
    if start_date is not None:
        h.apply_date(sanction, "startDate", start_date)
    if end_date is not None:
        h.apply_date(sanction, "endDate", end_date)
        iso_end_date = max(sanction.get("endDate"))
        end_date_obj = datetime.strptime(iso_end_date, "%Y-%m-%d")
        is_active = end_date_obj >= settings.RUN_TIME
        sanction.add("status", "active" if is_active else "inactive")

    return sanction
