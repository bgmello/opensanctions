from lxml import etree

from zavod import Context, helpers as h

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Cookie": "__ddg2_=oODOe2gVFAHstFSz; __ddg5_=5VLoRhvMkPVMHI4H; __ddgid_=F69Zw7VH7FdLn3xt; __ddgmark_=C04rsUQPh6Z7r9Xw; _ym_d=1730798853; _ym_isad=2; _ym_uid=1730798853821838136; __ddg1_=FwX17Njle4Mnl9WOR8V5",
    "Host": "cbr.ru",
    "Referer": "https://cbr.ru/scripts/XML_bic2.asp",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
}

SOAP_URL = "http://www.cbr.ru/CreditInfoWebServ/CreditOrgInfo.asmx"
SOAP_HEADERS = {"Content-Type": "text/xml; charset=utf-8"}


def send_soap_request(context: Context, action, body, cache_days):
    """Sends a SOAP request and returns the parsed XML response."""
    headers = SOAP_HEADERS.copy()
    headers["SOAPAction"] = f"http://web.cbr.ru/{action}"

    response = context.fetch_text(
        SOAP_URL, method="POST", headers=headers, data=body, cache_days=cache_days
    )
    root = etree.fromstring(response.encode("utf-8"))
    return h.remove_namespace(root)


def bic_to_int_code(context: Context, bic):
    """Gets the internal code for a BIC."""
    # Formulate the SOAP request body
    body = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
        <soap:Body>
            <BicToIntCode xmlns="http://web.cbr.ru/">
                <BicCode>{bic}</BicCode>
            </BicToIntCode>
        </soap:Body>
    </soap:Envelope>"""

    tree = send_soap_request(context, "BicToIntCode", body, cache_days=30)

    # Extract the result
    result = tree.find(".//BicToIntCodeResult")
    if result is not None:
        return result.text
    else:
        print("Result not found in the response")
        return None


def crawl_details(context: Context, internal_code, entity):
    """Gets detailed credit information for an internal code."""
    # Create the SOAP request body
    body = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
        <soap:Body>
            <CreditInfoByIntCodeXML xmlns="http://web.cbr.ru/">
                <InternalCode>{internal_code}</InternalCode>
            </CreditInfoByIntCodeXML>
        </soap:Body>
    </soap:Envelope>"""

    result = send_soap_request(context, "CreditInfoByIntCodeXML", body, cache_days=0)

    # Locate co_data and lic_data
    co_data = result.find(".//CreditOrgInfo/CO")
    if co_data is not None:
        ssv_date = co_data.findtext("SSV_Date")
        reg_date = co_data.findtext("MainDateReg")
        en_names = co_data.findtext("encname")
        phones = co_data.findtext("phones")
        lic_withd_num = co_data.findtext("licwithdnum")
        lic_withd_date = co_data.findtext("licwithddate")
        entity.add("name", co_data.findtext("OrgName"))
        entity.add("name", co_data.findtext("OrgFullName"))
        entity.add("name", co_data.findtext("csname"))
        entity.add("ogrnCode", co_data.findtext("MainRegNumber"))
        entity.add("bikCode", co_data.findtext("BIC"))
        entity.add("registrationNumber", co_data.findtext("RegNumber"))
        entity.add("address", co_data.findtext("UstavAdr"))
        entity.add("address", co_data.findtext("FactAdr"))
        entity.add("amount", co_data.findtext("UstMoney"))
        entity.add("status", co_data.findtext("OrgStatus"))
        if en_names is not None:
            for name in en_names.split(","):
                entity.add("name", name, lang="eng")
        if phones is not None:
            phones = h.multi_split(phones, ",")
            for phone in phones:
                if phone.startswith("("):
                    phone = "+7" + phone
                entity.add("phone", phone)
        if ssv_date is not None:
            entity.add(
                "notes",
                f"Дата вынесения заключения (признак внесения КО в Систему страхования вкладов): {ssv_date[:10]}",
            )
        if reg_date is not None:
            entity.add(
                "notes",
                f"Дата присвоения государственного регистрационного номера: {reg_date[:10]}",
            )
        if lic_withd_num is not None and lic_withd_date is not None:
            entity.add(
                "status",
                f"Лицензия аннулирована: {lic_withd_num} от {lic_withd_date[:10]}",
            )
        h.apply_date(
            entity, "incorporationDate", co_data.findtext("DateKGRRegistration")
        )
    else:
        context.log.warning(f"No details found for BIC {internal_code}")

    lic_data = result.find(".//CreditOrgInfo/LIC")
    if lic_data is not None:
        license_date = lic_data.findtext("LDate")
        license_code = lic_data.findtext("LCode")
        entity.add("classification", lic_data.findtext("LT"))
        if license_date is not None and license_code is not None:
            entity.add(
                "status",
                f"Код лицензии: {license_code}, дата выдачи: {license_date[:10]}",
            )

    context.emit(entity)


def crawl(context: Context):
    path = context.fetch_resource("source.xml", context.data_url, headers=HEADERS)
    with open(path, encoding="windows-1251") as file:
        xml_content = file.read()
    doc = etree.fromstring(xml_content.encode("windows-1251"))
    records = doc.findall(".//Record")
    if not records:
        context.log.warning("No <Record> elements found in the XML.")
        return
    for record in records:
        bic = record.findtext("Bic")
        entity = context.make("Company")
        entity.id = context.make_slug(bic)
        int_code = bic_to_int_code(context, bic)
        crawl_details(context, int_code, entity)
