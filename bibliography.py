# bibliography.py
import xml.etree.ElementTree as ET
from pathlib import Path

# TEI namespace
NS = {'tei': 'http://www.tei-c.org/ns/1.0', 'xml': 'http://www.w3.org/XML/1998/namespace'}

def load_bibliography(biblio_xml_path):
    """
    Parses a TEI listBibl file and returns a dict mapping xml:id -> formatted reference.
    """
    path = Path(biblio_xml_path)
    tree = ET.parse(path)
    root = tree.getroot()
    refs = {}

    for biblStruct in root.findall('.//tei:biblStruct', NS):
        # Grab the xml:id (could be xml:id or @xml:id)
        xmlid = biblStruct.get(f"{{{NS['xml']}}}id") or biblStruct.get('xml:id')
        if not xmlid:
            continue

        # 1) Authors
        authors = []
        for author in biblStruct.findall('.//tei:author', NS):
            surname = author.find("tei:surname[@xml:lang='en']", NS)
            forename = author.find("tei:forename[@xml:lang='en']", NS)
            if surname is not None and forename is not None:
                authors.append(f"{surname.text.strip()}, {forename.text.strip()}")
        author_str = '; '.join(authors)

        # 2) Title (monograph level="m" fallback to first title)
        title_el = biblStruct.find("tei:monogr/tei:title[@level='m'][@xml:lang='en']", NS) \
                   or biblStruct.find("tei:monogr/tei:title[@xml:lang='en']", NS)
        title = title_el.text.strip() if title_el is not None else ""

        # 3) Imprint data
        imp = biblStruct.find(".//tei:imprint", NS)
        vol = imp.find("tei:biblScope[@unit='volume']", NS)
        vol_text = vol.text.strip() if vol is not None and vol.text else ""
        place_el = imp.find("tei:pubPlace[@xml:lang='en']/tei:settlement", NS)
        place = place_el.text.strip() if place_el is not None else ""
        country_el = imp.find("tei:pubPlace[@xml:lang='en']/tei:country", NS)
        country = country_el.text.strip() if country_el is not None else ""
        date_el = imp.find("tei:date", NS)
        date = date_el.text.strip() if date_el is not None else ""

        # 4) Build a simple APA-style string (tweak as you wish)
        parts = []
        if author_str:
            parts.append(f"{author_str} ({date})")
        else:
            parts.append(f"({date})")
        if title:
            parts.append(title + '.')
        if vol_text:
            parts.append(f"Vol. {vol_text}.")
        if place and country:
            parts.append(f"{place} ({country}).")

        refs[xmlid] = ' '.join(parts).replace(' .', '.').strip()

    return refs
