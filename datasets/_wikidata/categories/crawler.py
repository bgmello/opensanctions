import csv
from io import StringIO
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from nomenklatura.enrich.wikidata import WikidataEnricher
from nomenklatura.enrich.wikidata.model import Claim

from zavod import Context, Entity
from zavod import helpers as h
from zavod.shed.wikidata.position import wikidata_position
from zavod.shed.wikidata.human import wikidata_basic_human

URL = "https://petscan.wmcloud.org/"
QUERY = {
    "doit": "",
    "depth": 4,
    # "combination": "subset",
    "format": "csv",
    "wikidata_item": "with",
    "wikidata_prop_item_use": "Q5",
    "search_max_results": 1000,
    "sortorder": "ascending",
}


def title_name(title: str) -> str:
    return title.replace("_", " ")


def crawl_position(
    context: Context, enricher: WikidataEnricher, person: Entity, claim: Claim
) -> None:
    item = enricher.fetch_item(claim.qid)
    if item is None:
        return
    position = wikidata_position(context, enricher, item)
    if position is None:
        return

    start_date: Optional[str] = None
    for qual in claim.qualifiers.get("P580", []):
        start_date = qual.text(enricher).text

    end_date: Optional[str] = None
    for qual in claim.qualifiers.get("P582", []):
        end_date = qual.text(enricher).text

    occupancy = h.make_occupancy(
        context,
        person,
        position,
        no_end_implies_current=False,
        start_date=start_date,
        end_date=end_date,
        birth_date=person.first("birthDate"),
    )
    if occupancy is not None:
        context.log.info("  -> %s (%s)" % (position.first("name"), position.id))
        context.emit(position)
        context.emit(occupancy)


def crawl_person(
    context: Context,
    enricher: WikidataEnricher,
    row: Dict[str, Any],
) -> Optional[Entity]:
    qid = row.pop("Wikidata")
    item = enricher.fetch_item(qid)
    entity = wikidata_basic_human(context, enricher, item, strict=True)
    if entity is None:
        return None

    for claim in item.claims:
        if claim.property == "P39":
            crawl_position(context, enricher, entity, claim)

    if not entity.has("name"):
        name = title_name(row.pop("title"))
        entity.add("name", name)
    return entity


def crawl_category(
    context: Context, enricher: WikidataEnricher, category: Dict[str, Any]
) -> None:
    cache_days = int(category.pop("cache_days", 14))
    topics: List[str] = category.pop("topics", [])
    if "topic" in category:
        topics.append(category.pop("topic"))
    country: Optional[str] = category.pop("country", None)

    query = dict(QUERY)
    cat: str = category.pop("category", "")
    query["categories"] = cat.strip()
    query.update(category)
    context.log.info("Crawl category: %s" % cat)

    position_data: Dict[str, Any] = category.pop("position", {})
    position: Optional[Entity] = None
    if "name" in position_data:
        position = h.make_position(context, **position_data, id_hash_prefix="wd-cat")

    query_string = urlencode(query)
    # print(query_string)
    url = f"{URL}?{query_string}"
    data = context.fetch_text(url, cache_days=cache_days)
    wrapper = StringIO(data)
    results = 0
    emitted = 0
    for row in csv.DictReader(wrapper):
        results += 1
        entity = crawl_person(context, enricher, row)
        if entity is None:
            continue
        entity.add("topics", topics)
        entity.add("country", country)
        context.emit(entity)
        if position is not None:
            occupancy = h.make_occupancy(context, entity, position)
            if occupancy is not None:
                context.emit(occupancy)

        emitted += 1
        if emitted > 0 and emitted % 10000 == 0:
            context.cache.flush()

    if emitted > 0 and position is not None:
        context.emit(position)

    context.log.info(
        "PETScanning category: %s" % cat,
        topics=topics,
        results=results,
        emitted=emitted,
    )
    context.cache.flush()


def crawl(context: Context) -> None:
    enricher = WikidataEnricher(context.dataset, context.cache, context.dataset.config)
    categories: List[Dict[str, Any]] = context.dataset.config.get("categories", [])
    for category in categories:
        crawl_category(context, enricher, category)
