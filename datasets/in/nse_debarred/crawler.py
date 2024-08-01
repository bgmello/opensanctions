from typing import Generator
from rigour.mime.types import XLS
from normality import stringify, slugify
from datetime import datetime
import xlrd

from zavod import Context, helpers as h

SEBI_DEBARRMENT_URL = "https://nsearchives.nseindia.com/content/press/prs_ra_sebi.xls"
OTHER_DEBARRMENT_URL = (
    "https://nsearchives.nseindia.com/content/press/prs_ra_others.xls"
)
CURRENT_ORDER_DATE = None
CURRENT_ORDER_PARTICULARS = None
CURRENT_NSE_CIRCULAR_NO = None


def parse_sheet(
    sheet,
) -> Generator[dict, None, None]:
    headers = None
    for row in sheet:
        cells = []
        for cell in row:
            if cell.ctype == xlrd.XL_CELL_DATE:
                # Convert Excel date format to Python datetime
                date_value = xlrd.xldate_as_datetime(cell.value, sheet.book.datemode)
                cells.append(date_value)
            else:
                cells.append(cell.value)
        if headers is None:
            headers = []
            for idx, cell in enumerate(cells):
                if not cell:
                    cell = f"column_{idx}"
                headers.append(slugify(cell, "_").lower())
            continue

        record = {}
        for header, value in zip(headers, cells):
            if isinstance(value, datetime):
                value = value.date()
            record[header] = stringify(value)
        if len(record) == 0:
            continue
        yield record


def crawl_item(input_dict: dict, context: Context):
    global CURRENT_ORDER_DATE
    global CURRENT_ORDER_PARTICULARS
    global CURRENT_NSE_CIRCULAR_NO

    name = input_dict.pop("entity_individual_name")
    pan = input_dict.pop("pan")
    # It's a target if it wasn't revoked
    target = (input_dict["period"] is None) or ("Revoked" not in input_dict["period"])
    topics = "sanction" if target else "reg.action"

    if name is None:
        return

    entity = context.make("LegalEntity")
    entity.id = context.make_id(name, pan)
    entity.add("name", name)
    entity.add("taxNumber", pan)
    entity.add("topics", topics)

    if input_dict.get("nse_circular_no"):
        CURRENT_NSE_CIRCULAR_NO = input_dict.pop("nse_circular_no")
    if input_dict.get("order_particulars"):
        CURRENT_ORDER_PARTICULARS = input_dict.pop("order_particulars")
    if input_dict.get("order_date"):
        CURRENT_ORDER_DATE = input_dict.pop("order_date")

    sanction = h.make_sanction(context, entity, key=CURRENT_NSE_CIRCULAR_NO)

    sanction.add("date", h.parse_date(CURRENT_ORDER_DATE, formats=["%Y-%m-%d"]))
    sanction.add("description", "Order Particulars: " + CURRENT_ORDER_PARTICULARS)

    sanction.add("duration", input_dict.pop("period"))

    context.emit(entity, target=target)
    context.emit(sanction)

    # There is some random data in the 17 and 18 columns
    context.audit_data(
        input_dict,
        ignore=[
            "din_cin_of_entities_debarred",
            "date_of_nse_circular",
            "column_17",
            "column_18",
            "column_9",
        ],
    )


def crawl(context: Context):

    path_sebi = context.fetch_resource("sebi.xls", SEBI_DEBARRMENT_URL)
    context.export_resource(path_sebi, XLS, title=context.SOURCE_TITLE)

    wb_sebi = xlrd.open_workbook(path_sebi)

    for item in parse_sheet(wb_sebi["Sheet 1"]):
        crawl_item(item, context)

    path_other = context.fetch_resource("other.xls", OTHER_DEBARRMENT_URL)
    context.export_resource(path_other, XLS, title=context.SOURCE_TITLE)

    wb_other = xlrd.open_workbook(path_other)

    for item in parse_sheet(wb_other["Sheet1"]):

        crawl_item(item, context)