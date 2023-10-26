import logging
from sys import argv
from typing import Dict, List, Set, Optional
from collections import defaultdict
from followthemoney.cli.util import path_entities
from followthemoney.proxy import EntityProxy
from requests import Session
from zavod.entity import Entity
from zavod.meta import load_dataset_from_path
from zavod.runtime.cache import get_cache
from zavod.store import View, get_view
from nomenklatura.enrich.wikidata.props import PROPS_DIRECT
from nomenklatura.enrich.wikidata import WD_API
from nomenklatura.enrich.wikidata.model import Claim
from nomenklatura.util import normalize_url
import json
from nomenklatura.cache import Cache


log = logging.getLogger(__name__)

# quickstatements
# if we add the same property and value multiple times, each time with a different
# reference but no other differences, will they converge in one?


# can't use quickstatements for 'position held' because all qualifiers will end up
# on the same claim.
# https://github.com/everypolitician/position_statements/tree/master
# Not sure you can use the full vocabulary of quickstatements like CREATE and LAST
# using position_statements.


# def get_position_held(view, entity: EntityProxy) -> None:
#     position_occupancies = defaultdict(list)
#     wd_position_occupancies = defaultdict(list)
#
#     for person_prop, person_related in view.get_adjacent(entity):
#         if person_prop.name == "positionOccupancies":
#             occupancy = person_related
#             for occ_prop, occ_related in view.get_adjacent(person_related):
#                 if occ_prop.name == "post":
#                     position = occ_related
#                     if position.id.startswith("Q"):
#                         position_occupancies[position.id].append(occupancy)
#                         if "wd_peps" in occupancy.datasets:
#                             wd_position_occupancies[position.id].append(occupancy)
#
#     if position_occupancies and (wd_position_occupancies != position_occupancies):
#         for position_id in position_occupancies.keys():
#             occupancies = position_occupancies[position_id]
#             wd_occupancies = wd_position_occupancies.get(position_id, [])
#
#             if not occupancies:
#                 continue
#
#             wd_start_years = set()
#             wd_end_years = set()
#             for occupancy in wd_occupancies:
#                 for date in occupancy.get("startDate"):
#                     wd_start_years.add(date[:4])
#                 if len(occupancy.get("startDate")) == 0:
#                     wd_start_years.add(None)
#                 for date in occupancy.get("endDate"):
#                     wd_end_years.add(date[:4])
#                 if len(occupancy.get("endDate")) == 0:
#                     wd_end_years.add(None)
#
#             print("  ", position_id)
#             print("     Wikidata has:")
#             for occupancy in wd_occupancies:
#                 print("      ", occupancy.get("startDate"), occupancy.get("endDate"))
#
#             print("     We have:")
#             for occupancy in occupancies:
#                 start_years = {d[:4] for d in occupancy.get("startDate")}
#                 start_years.add(None) if len(occupancy.get("startDate")) == 0 else None
#                 end_years = {d[:4] for d in occupancy.get("endDate")}
#                 end_years.add(None) if len(occupancy.get("endDate")) == 0 else None
#                 if "wd_peps" in occupancy.datasets or start_years.issubset(wd_start_years) or end_years.issubset(wd_end_years):
#                     print("       skipping", occupancy.get("startDate"), occupancy.get("endDate"), occupancy.datasets)
#                 else:
#                     print("       CANDIDATE:", occupancy.get("startDate"), occupancy.get("endDate"), occupancy.datasets)


SPARQL_URL = "https://query.wikidata.org/sparql"
GIVEN_NAME_SPARQL = """
SELECT ?item ?itemLabel
WHERE
{
  ?item wdt:P31/wdt:P279* wd:Q202444 .
  ?item ?label "%s"@en .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}
"""


class Action:
    def __init__(self, quickstatement, human_readable):
        self.quickstatement = quickstatement
        self.human_readable = human_readable


class Assessment:
    def __init__(self, session: "EditSession", entity: Entity):
        self.session = session
        self.entity = entity
        self.item = None
        self.claims = defaultdict(list)
        self.actions = []
        wikidataIds = entity.get("wikidataId")
        self.qid = wikidataIds[0] if wikidataIds else None

    def fetch_item(self):
        params = {"format": "json", "ids": self.qid, "action": "wbgetentities"}
        self.item = (
            self.session.get_json(WD_API, params).get("entities", {}).get(self.qid)
        )
        self.claims = defaultdict(list)
        for wd_prop, claim_dicts in self.item.get("claims", {}).items():
            self.claims[wd_prop] = [Claim(c, wd_prop) for c in claim_dicts]

    def generate_actions(self):
        if self.qid:
            if self.item is None:
                self.fetch_item()
            self.assess_forename()

            # TODO: check if it has a label, other non-claim properties?
            # description
            # aliases
            # ... all the properties we care about ...
            # ... wd:everypolitition data model has hints ...

        # else: search for and propose adding a new item

    def assess_forename(self):
        stmts = self.entity.get_statements("firstName")
        wd_vals = self.claims.get("P735", [])
        if wd_vals:
            return
        for stmt in stmts:
            print(stmt.value, stmt.lang, stmt.dataset)
            lang = stmt.lang or "en"
            # TODO: use statement language, convert to 2-letter code.
            # TODO: watch out for gendered given names. Do we want to restrict ourselfs
            # just to cases where we find a non-gendered name for now?
            query = GIVEN_NAME_SPARQL % stmt.value
            r = self.session.get_json(
                SPARQL_URL, params={"format": "json", "query": query}
            )
            rows = r["results"]["bindings"]
            if len(rows) == 1:
                value_qid = rows[0]["item"]["value"].split("/")[-1]
                # TODO: consider adding reference to source dataset or sourceUrl added to entity by dataset.
                self.actions.append(
                    Action(
                        f"{self.qid}\tP735\t{value_qid}",
                        f"Add given name {value_qid} ({stmt.value}) to {self.qid}.",
                    )
                )
            if len(rows) > 1:
                log.info("More than one forename result %r", rows)
            # if len(rows) == 0: consider adding missing given names as new items.


class EditSession:
    def __init__(self, cache: Cache):
        self.cache = cache
        self.http_session = Session()

    def get_json(self, url, params, cache_days=2):
        url = normalize_url(url, params=params)
        response = self.cache.get(url, max_age=cache_days)
        if response is None:
            log.debug("HTTP GET: %s", url)

            resp = self.http_session.get(url)
            resp.raise_for_status()
            response = resp.text
            if cache_days > 0:
                self.cache.set(url, response)
        return json.loads(response)

    def assess_entity(self, entity: Entity) -> Assessment:
        assessment = Assessment(self, entity)
        assessment.generate_actions()
        return assessment


def generate_wd_statements(
    out_file: str, view: View, cache: Cache, focus_dataset: str
) -> None:
    session = EditSession(cache)

    with open(out_file, "w") as quickstatements_fh:
        for entity in view.entities():
            if not entity.schema.name == "Person":
                continue
            if focus_dataset and focus_dataset not in entity.datasets:
                continue

            assessment = session.assess_entity(entity)

            # todo: in interactive interface, offer the user the choice of adding all
            # actions, a selection, or none.
            for action in assessment.actions:
                quickstatements_fh.write(
                    f"{action.quickstatement}\t/* {action.human_readable} */\n"
                )

            quickstatements_fh.flush()
            cache.flush()
