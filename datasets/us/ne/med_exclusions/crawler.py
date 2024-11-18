from typing import Dict
from rigour.mime.types import PDF

from zavod import Context, helpers as h
from zavod.shed.zyte_api import fetch_resource

PAGE_SETTINGS = {"join_y_tolerance": 2}


def crawl_item(row: Dict[str, str], context: Context):

    if organization_name := row.pop("organization_name"):
        entity = context.make("Company")
        entity.id = context.make_id(organization_name, row.get("npi"))
        entity.add("name", organization_name)
    else:
        entity = context.make("Person")
        entity.id = context.make_id(
            row.get("provider_first_name"),
            row.get("provider_middle_initial"),
            row.get("provider_last_name"),
            row.get("npi"),
        )
        h.apply_name(
            entity,
            first_name=row.pop("provider_first_name"),
            last_name=row.pop("provider_last_name"),
            middle_name=row.pop("provider_middle_initial"),
        )

    if row.get("npi"):
        entity.add("npiCode", row.pop("npi"))

    entity.add("topics", "debarment")
    entity.add("country", "us")

    sanction = h.make_sanction(context, entity)
    sanction.add("reason", row.pop("reason_for_action_code"))
    h.apply_date(sanction, "startDate", row.pop("effective_date"))
    sanction.add("provisions", row.pop("sanction_code"))

    context.emit(entity, target=True)
    context.emit(sanction)

    # Currently, all sanctions are permanent. If the sanction type isn't permanent we emit a warning
    if not row.get("sanction_type_code").startswith("Permanent"):
        context.log.warning("Sanction is not permanent")

    context.audit_data(
        row,
        ignore=[
            "id",
            "sanction_type_code",
        ],
    )


def crawl(context: Context) -> None:
    _, _, _, path = fetch_resource(
        context, "source.pdf", context.data_url, expected_media_type=PDF
    )
    context.export_resource(path, PDF, title=context.SOURCE_TITLE)

    for item in h.parse_pdf_table(
        context,
        path,
        headers_per_page=True,
        page_settings=lambda page: (page, PAGE_SETTINGS),
    ):
        crawl_item(item, context)
