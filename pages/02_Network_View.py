# app.py  –  Streamlit network explorer for TEI inscriptions
# ⚙︎ requires: streamlit, lxml, pandas, networkx, pyvis

import streamlit as st
st.set_page_config(
    page_title="TEI Network Explorer",
    layout="wide",
    page_icon="🔗",
    initial_sidebar_state="expanded"
)

from pathlib import Path
import json
import re
from datetime import datetime
import pandas as pd
import networkx as nx
from lxml import etree
from pyvis.network import Network
import streamlit.components.v1 as components


###############################################################################
# 1. Config & helpers
###############################################################################


DATA_DIR = Path(__file__).resolve().parent.parent / "data"      # where the data files are 
TEI_DIR = DATA_DIR / "xmls"       # sample XMLs directory
AUTH_DIR = DATA_DIR / "authority"    # authority files directory

# authority lists ------------------------------------------------------------
def load_auth(filename: str, root_key: str, term_key: str = "term") -> dict:
    """Return dict {id: english_label} for a given authority .json"""
    path = AUTH_DIR / filename
    data = json.load(path.open(encoding='utf-8'))
    body = data[root_key]["body"]
    
    # Handle both list/item and listPlace/place structures
    if "list" in body:
        items = body["list"]["item"]
    elif "listPlace" in body:
        items = body["listPlace"]["place"]
    else:
        raise ValueError(f"Unknown structure in {filename}")
        
    mapping = {}
    for item in items:
        xml_id = item["_xml:id"]
        term = item.get(term_key, {})
        
        try:
            if isinstance(term, list):
                # multiple lang variants, pick the one with _xml:lang == "en"
                en_label = next(t["__text"] for t in term
                              if t.get("_xml:lang") == "en")
            else:
                # single term object
                if isinstance(term, dict):
                    if term.get("_xml:lang") == "en":
                        en_label = term["__text"]
                    else:
                        # try to get English from gloss if available
                        gloss = item.get("gloss", {})
                        if isinstance(gloss, dict) and gloss.get("_xml:lang") == "en":
                            en_label = gloss["__text"]
                        else:
                            # fallback to any available text
                            en_label = term.get("__text", "unknown")
                else:
                    en_label = "unknown"
        except (KeyError, TypeError, StopIteration):
            en_label = "unknown"
                
        mapping[xml_id] = en_label.strip()
    return mapping

MATERIALS = load_auth("materials.json", "materials")
OBJECTS   = load_auth("objects.json",   "objects")
ORIGLOCS  = load_auth("origloc.json",   "origloc", term_key="placeName")
PLACES    = load_auth("places.json",    "places",  term_key="placeName")


# XML utilities --------------------------------------------------------------
NS = {"tei": "http://www.tei-c.org/ns/1.0"}

def text_of(el):
    """Return the (stripped) text content of an element, incl. its children."""
    return "".join(el.itertext()).strip()

def pick_en(el_list):
    """Pick first child with @xml:lang='en', else fallback to bare element."""
    for el in el_list:
        if el.get("{http://www.w3.org/XML/1998/namespace}lang") == "en":
            return text_of(el)
    return text_of(el_list[0]) if el_list else ""


###############################################################################
# 2. Parse one TEI file
###############################################################################

def parse_tei(path: Path) -> dict:
    tree = etree.parse(str(path))
    root = tree.getroot()

    # file/inscription identifier (filename or <title xml:lang="en">)
    title_el = root.xpath(".//tei:titleStmt/tei:title[@xml:lang='en']", namespaces=NS)
    insc_id  = title_el[0].text if title_el else path.stem

    # materials ---------------------------------------------------------------
    mats = []
    for mat in root.xpath(".//tei:support/tei:material[@xml:lang='en']", namespaces=NS):
        mat_id = (mat.get("ref") or "").split("#")[-1]
        mats.append(MATERIALS.get(mat_id, text_of(mat)))

    # objects -----------------------------------------------------------------
    objs = []
    for obj in root.xpath(".//tei:support/tei:objectType[@xml:lang='en']", namespaces=NS):
        obj_id = (obj.get("ref") or "").split("#")[-1]
        objs.append(OBJECTS.get(obj_id, text_of(obj)))

    # original place ----------------------------------------------------------
    locs = []
    for op in root.xpath(".//tei:history/tei:origin/tei:origPlace", namespaces=NS):
        loc_id = (op.get("ref") or "").split("#")[-1]
        locs.append(ORIGLOCS.get(loc_id, pick_en(op.xpath("./tei:seg", namespaces=NS))))
    locs = [l for l in locs if l]            # drop blanks    # dating from value attribute or notBefore/notAfter --------------------------------
    od = root.find(".//tei:origin/tei:origDate", namespaces=NS)
    year = None
    if od is not None:
        try:
            # First try to get the value attribute
            value = od.get('value')
            if value:
                year = int(value)
            else:
                # Fall back to notBefore/notAfter if value is not present
                nb, na = int(od.get("notBefore", 0)), int(od.get("notAfter", 0))
                year = int((nb + na) / 2) if nb and na else nb or na
        except ValueError:
            # If numeric conversion fails, try to get year from the English text
            seg = od.find(".//tei:seg[@xml:lang='en']", namespaces=NS)
            if seg is not None and seg.text:
                try:
                    year = int(seg.text.strip())
                except ValueError:
                    pass
    decade = (year // 10) * 10 if year else None

    return {
        "inscription": insc_id,
        "materials":   mats or ["unknown"],
        "objects":     objs   or ["unknown"],
        "origlocs":    locs   or ["unknown"],
        "year":        year,
        "decade":      f"{decade}s" if decade else "undated",
        "src":         path.name
    }


###############################################################################
# 3. Streamlit UI
###############################################################################

st.title("📜 Epigraphic Network Explorer")

# --- Sidebar upload / directory selection -----------------------------------
st.sidebar.header("Data input")
use_uploader = st.sidebar.toggle("Upload XML", False)
if use_uploader:
    uploaded = st.sidebar.file_uploader(
        "Drop one or more TEI files", type=["xml"], accept_multiple_files=True)
    tei_files = [Path(f.name).with_suffix(".xml") for f in uploaded]
    # write to temp so that lxml can parse
    for stfile, tmp in zip(uploaded, tei_files):
        tmp.write_bytes(stfile.getvalue())
else:
    tei_files = sorted(TEI_DIR.glob("*.xml"))
    st.sidebar.write(f"Using **{len(tei_files)}** XML files in `tei_docs/`")

if not tei_files:
    st.warning("No TEI files found. Upload or place them in the folder and reload.")
    st.stop()

# --- Parse all TEI files -----------------------------------------------------
records = [parse_tei(p) for p in tei_files]
df = (
    pd.json_normalize(records, 
                      record_path=["materials"], 
                      meta=["inscription", "objects", "origlocs", "decade", "src", "year"])
    .rename(columns={0: "material_"})  # rename the materials column
    .explode("objects").rename(columns={"objects": "object"})
    .explode("origlocs").rename(columns={"origlocs": "origloc"})
)

###############################################################################
# 4. Sidebar filters
###############################################################################
decades   = sorted(df["decade"].unique())
materials = sorted(df["material_"].unique())
objects   = sorted(df["object"].unique())
origlocs  = sorted(df["origloc"].unique())

pick_decade   = st.sidebar.multiselect("Decade", decades, default=decades)
pick_material = st.sidebar.multiselect("Material", materials, default=materials)
pick_object   = st.sidebar.multiselect("Object type", objects, default=objects)
pick_origloc  = st.sidebar.multiselect("Original location", origlocs, default=origlocs)

mask = (
    df["decade"].isin(pick_decade) &
    df["material_"].isin(pick_material) &
    df["object"].isin(pick_object) &
    df["origloc"].isin(pick_origloc)
)
df_filt = df[mask]

###############################################################################
# 5. Build network
###############################################################################
G = nx.Graph()

for _, row in df_filt.iterrows():
    insc = f"🪧 {row.inscription}"
    mat  = f"🪨 {row.material_}"
    obj  = f"📐 {row.object}"
    loc  = f"📍 {row.origloc}"
    dec  = f"📅 {row.decade}"

    G.add_node(insc, type="inscription")
    for node in (mat, obj, loc, dec):
        G.add_node(node, type="attr")
        G.add_edge(insc, node)

###############################################################################
# 6. Visualise with PyVis
###############################################################################
try:
    # Create a temporary directory for the network file
    import tempfile
    import os
      # Initialize network
    net = Network(height="620px", width="100%", directed=False, notebook=True)
    net.barnes_hut()                      # nicer layout
      # Configure network options for larger labels
    net.set_options("""
    {
        "nodes": {
            "font": {
                "size": 20,
                "face": "arial",
                "bold": true
            },
            "size": 30
        },
        "edges": {
            "width": 2
        }
    }
    """)

    for n, d in G.nodes(data=True):
        color = "#F19C65" if d["type"] == "inscription" else "#3B738F"
        net.add_node(n, label=n, color=color, title=n)

    for s, t in G.edges():
        net.add_edge(s, t)

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.html') as f:
        net_html = f.name
        net.save_graph(net_html)
        
    # Read and display
    with open(net_html, 'r', encoding='utf-8') as f:
        html_content = f.read()
    components.html(html_content, height=650, scrolling=True)
    
    # Clean up
    try:
        os.unlink(net_html)
    except:
        pass
        
except Exception as e:
    st.error(f"Error generating network visualization: {str(e)}")
    st.write("Displaying fallback table view of the network data:")

###############################################################################
# 7. Data & download
###############################################################################
st.subheader("Edgelist")
edge_df = pd.DataFrame(G.edges(), columns=["source", "target"])
st.dataframe(edge_df, use_container_width=True)

@st.cache_data
def _to_csv(df): return df.to_csv(index=False).encode()
st.download_button("⬇️ Download CSV", _to_csv(edge_df), "edgelist.csv", "text/csv")

###############################################################################
# 8. Footnote
###############################################################################
st.markdown(
    """
    _Powered by JSON authority lists (materials, objects, orig-locs, places)  
    and TEI-EpiDoc XML_  
    """
)
