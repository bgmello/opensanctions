from typing import Generator, Dict
from lxml.etree import _Element
from lxml import html
import re
from zavod import Context, helpers as h
from normality import collapse_spaces

from zavod.shed.zyte_api import fetch_html

REGEX_URLS = r"(https?://[^\s]+)"
TABLE_XPATH = ".//div[@class='article-content']//table"


def parse_table(table: _Element) -> Generator[Dict[str, str], None, None]:
    """
    Parse the table and returns the information as a list of dict

    Returns:
        A generator that yields a dictionary of the table columns and values. The keys are the
        column names and the values are the column values.
    Raises:
        AssertionError: If the headers don't match what we expect.
    """
    headers = [th.text_content() for th in table.findall(".//*/th")]
    for row in table.findall(".//*/tr")[1:]:
        cells = []
        for el in row.findall(".//td"):
            cells.append(collapse_spaces(el.text_content()))
        assert len(cells) == len(headers)

        # The table has a last row with all empty values
        if all(c == "" for c in cells):
            continue

        yield {hdr: c for hdr, c in zip(headers, cells)}


def crawl_item(input_dict: dict, context: Context):
    name = input_dict.pop("Name of unauthorised entities/individual")

    entity = context.make("LegalEntity")
    entity.id = context.make_id(name)

    entity.add("name", name)
    entity.add("topics", "poi")

    # There can be multiple websites for each entity
    properties_text = input_dict.pop("Website")
    for website in re.findall(REGEX_URLS, properties_text):
        entity.add("website", website.strip(","))
    entity.add("notes", properties_text)

    sanction = h.make_sanction(context, entity)

    # The date is always in the format %Y/%m/00%d %b %Y. For example: 2022/09/0029 Sep 2022
    sanction.add(
        "startDate",
        h.parse_date(
            input_dict.pop("Date Added to Alert List").split(" ")[0],
            formats=["%Y/%m/00%d"],
        ),
    )

    context.emit(entity, target=True)
    context.emit(sanction)

    context.audit_data(input_dict)


def unblock_validator(doc: html.HtmlElement) -> bool:
    return doc.find(TABLE_XPATH) is not None


def crawl(context: Context):
    actions = [
        {
            "action": "waitForSelector",
            "selector": {
                "type": "xpath",
                "value": "//select[@name='example_length']",
            },
            "timeout": 15,
        },
    ]
    doc = fetch_html(
        context,
        context.data_url,
        unblock_validator,
        actions=actions,
    )

    for item in parse_table(doc.find(TABLE_XPATH)):
        crawl_item(item, context)
