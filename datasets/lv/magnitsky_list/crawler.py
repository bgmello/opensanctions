import csv
from typing import Dict
import zavod.helpers as h
from zavod import Context
from datetime import datetime

# Define constants for date parsing
DATE_FORMATS = ["%Y-%m-%d", "%Y"]

# Normalized country names
NORMALIZED_COUNTRIES = {
    "Krievijas Federācija": "Russia",
    # Add more mappings as needed
}


def parse_date(date_str: str, formats: list) -> str:
    """Parse a date string into a standardized format"""
    for date_format in formats:
        try:
            return datetime.strptime(date_str, date_format).isoformat()
        except ValueError:
            continue
    return None


def normalize_country(country: str) -> str:
    """Normalize the country name to a standard format"""
    return NORMALIZED_COUNTRIES.get(country, country)


def crawl_row(context: Context, row: Dict[str, str]):
    """Process one row of the CSV data"""
    # Create a Person entity
    original_name = row.get("Original Name")
    name_in_brackets = row.get("Name in Brackets")
    birth_date = parse_date(row.get("Birth Date"), DATE_FORMATS)
    country = normalize_country(row.get("Country"))
    source_url = row.get("Source URL")

    entity = context.make("Person")
    entity.id = context.make_slug(original_name)

    # Add names
    entity.add("name", original_name, lang="lav")
    entity.add("name", row.get("name"), lang="eng")
    entity.add("alias", name_in_brackets, lang="lav")

    # Add birth date
    if birth_date:
        entity.add("birthDate", birth_date)

    # Add nationality if present
    if country:
        entity.add("country", country, lang="lav")

    # Create a Sanction entity
    sanction = h.make_sanction(context, entity)

    # Add source URL
    if source_url:
        entity.add("sourceUrl", source_url.strip())
        sanction.add("sourceUrl", source_url.strip())

    # Emit entities
    context.emit(entity, target=True)
    context.emit(sanction)


def crawl(context: Context):
    path = context.fetch_resource("source.csv", context.data_url)
    with open(path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            crawl_row(context, row)
