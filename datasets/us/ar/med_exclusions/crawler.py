import re
from typing import Dict
import csv
from rigour.mime.types import CSV

from zavod import Context, helpers as h
from zavod.shed.zyte_api import fetch_resource

REGEX_AKA = re.compile(r"\baka\b", re.IGNORECASE)


def crawl_item(row: Dict[str, str], context: Context):
    zip_code = row.pop("Zip")
    division = row.pop("Division")

    address = h.format_address(
        city=row.pop("City"),
        state=row.pop("State"),
        postal_code=zip_code,
        country_code="us",
    )

    if provider_name := row.pop("Provider Name"):
        last_name, first_name = provider_name.split(",", 1)
        names = REGEX_AKA.split(last_name)

        person = context.make("Person")
        person.id = context.make_id(provider_name, zip_code)
        h.apply_name(person, last_name=names[0], alias=names[1:], first_name=first_name)
        person.add("country", "us")
        person.add("topics", "debarment")
        person.add("address", address)
        sanction = h.make_sanction(context, person)
        sanction.add("authority", division)

        context.emit(person, target=True)
        context.emit(sanction)

    if facility_name := row.pop("Facility Name"):
        entity = context.make("LegalEntity")  # Sometimes the person's name.
        entity.id = context.make_id(facility_name, zip_code)
        entity.add("name", facility_name)
        entity.add("country", "us")
        entity.add("topics", "debarment")
        entity.add("address", address)
        # The d/b/a is a person's name and then the company name
        if "d/b/a" in facility_name:
            dba = context.lookup_value("names", facility_name)
            dba_person_name, facility_name = dba[0], dba[1]
            entity.add("alias", dba_person_name)
            if not dba:
                context.log.warning("No names found for", facility_name)

        sanction = h.make_sanction(context, entity)
        sanction.add("authority", division)

        context.emit(entity, target=True)
        context.emit(sanction)

    if provider_name and facility_name:
        link = context.make("UnknownLink")
        link.id = context.make_id(person.id, entity.id)
        link.add("object", entity.id)
        link.add("subject", person.id)
        context.emit(link)

    context.audit_data(row, ignore=[None])


def crawl(context: Context) -> None:
    _, _, _, path = fetch_resource(
        context,
        "source.csv",
        context.data_url,
        expected_media_type=CSV,
        geolocation="us",
    )
    context.export_resource(path, CSV, title=context.SOURCE_TITLE)

    with open(path) as f:
        for item in csv.DictReader(f):
            crawl_item(item, context)
