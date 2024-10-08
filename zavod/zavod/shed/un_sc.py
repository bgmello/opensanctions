from enum import Enum
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from zavod import Context, Entity
from zavod.meta import load_dataset_from_path
from zavod.meta.dataset import Dataset
from zavod.util import ElementOrTree
from zavod import helpers as h


class Regime(Enum):
    SOMALIA = "SO"  #        SO - 751 (1992)
    DAESH_AL_QAIDA = "QD"  # non-State entity 1267/1989
    IRAQ = "IQ"  #           IQ - 1518 (2003)
    DRC = "CD"  #            CD - 1533 (2004)
    SUDAN = "SD"  #          SD - 1591 (2005)
    NORTH_KOREA = "KP"  #    KP - 1718 (2006)
    LIBYA = "LY"  #          LY - 1970 (2011)
    TALIBAN = "TA"  #        non-State entity - 1988 (2011)
    GUINEA_BISSAU = "GB"  #  GB - 2048 (2012)
    CAR = "CF"  #            CF - 2127 (2013)
    YEMEN = "YE"  #          YE - 2140 (2014)
    SOUTH_SUDAN = "SS"  #    SS - 2206 (2015)
    HAITI = "HT"  #          HT - 2653 (2022)


def get_persons(
    context: Context,
    prefix: str,
    doc: ElementOrTree,
    include_prefixes: Optional[List[Regime]] = None,
) -> Generator[Tuple[ElementOrTree, Entity], None, None]:
    yield from get_entities(
        context, prefix, doc, include_prefixes, "INDIVIDUAL", "Person"
    )


def get_legal_entities(
    context: Context,
    prefix: str,
    doc: ElementOrTree,
    include_prefixes: Optional[List[Regime]] = None,
) -> Generator[Tuple[ElementOrTree, Entity], None, None]:
    yield from get_entities(
        context, prefix, doc, include_prefixes, "ENTITY", "LegalEntity"
    )


def get_entities(
    context: Context,
    prefix: str,
    doc: ElementOrTree,
    include_prefixes: Optional[List[Regime]],
    tag: str,
    schema: str,
) -> Generator[Tuple[ElementOrTree, Entity], None, None]:
    for node in doc.findall(f".//{tag}"):
        perm_ref = node.findtext("./REFERENCE_NUMBER")
        if (
            include_prefixes is None
            or perm_ref is None
            or any(
                [perm_ref.startswith(un_prefix.value) for un_prefix in include_prefixes]
            )
        ):
            yield node, make_entity(context, prefix, schema, node)


def make_entity(
    context: Context, prefix: str, schema: str, node: ElementOrTree
) -> Entity:
    """Make an entity, set its ID, and add the name and sanction topic so that there is
    at least one property, making it useful and ready to emit."""
    entity = context.make(schema)
    entity.id = context.make_slug(node.findtext("./DATAID"), prefix=prefix)
    h.apply_name(
        entity,
        given_name=node.findtext("./FIRST_NAME"),
        second_name=node.findtext("./SECOND_NAME"),
        name3=node.findtext("./THIRD_NAME"),
        name4=node.findtext("./FOURTH_NAME"),
        quiet=True,
    )
    entity.add("topics", "sanction")
    return entity


def load_un_sc(context: Context) -> Tuple[Dataset, ElementOrTree]:
    un_sc_path = (
        Path(__file__).parent.parent.parent.parent
        / "datasets/_global/un_sc_sanctions/un_sc_sanctions.yml"
    )
    dataset = load_dataset_from_path(un_sc_path)
    if not (dataset and dataset.data and dataset.data.url):
        raise Exception("Could not look up un_sc_sanctions dataset or its data URL")
    path = context.fetch_resource("source.xml", dataset.data.url)
    context.export_resource(
        path, "text/xml", title="Source data - UN Security Council Consolidated list"
    )
    doc = context.parse_resource_xml(path)
    return dataset, doc
