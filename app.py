"""
Main application file for the TEI XML visualization application.
"""
import os
import base64
from io import BytesIO
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

# Basic data manipulation libraries
import pandas as pd
import json
import numpy as np

# Plotting and visualization libraries
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import folium
from streamlit_folium import st_folium
from PIL import Image
import networkx as nx

# Streamlit
from lxml import etree
from pyvis.network import Network
import streamlit.components.v1 as components
import streamlit as st
from streamlit import session_state
import streamlit.web.bootstrap as bootstrap

# Local imports
from map_view import *
from bibliography import load_bibliography

# ...


def get_xml_references(xml_string):
    """Parses the XML string and returns a set of all 'ref' attribute values."""
    if not xml_string:
        return set()
    try:
        ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
        cleaned_xml_string = xml_string.strip()
        root = ET.fromstring(cleaned_xml_string)
        refs = {elem.attrib['ref'] for elem in root.findall('.//*[@ref]', ns)}
        return refs
    except ET.ParseError as e:
        st.error(f"Error parsing XML file: {e}")
        return set()

def get_english_place_name(place):
    """Extracts the English place name from a place object."""
    if isinstance(place, dict) and 'placeName' in place:
        for name in place.get('placeName', []):
            if isinstance(name, dict) and name.get('_xml:lang') == 'en':
                return name.get('__text')
    return None

def extract_referenced_places(json_data, source_name, xml_refs, doc_id=None):
    """
    Extracts places from a JSON object that are referenced in the XML.
    Returns a list of dictionaries for map plotting and a list for textual display.
    """
    map_points = []
    text_points = []
    
    # Navigate to the list of places in the JSON structure
    try:
        places_list = json_data.get(next(iter(json_data)))['body']['listPlace']['place']
    except (KeyError, TypeError, StopIteration):
        st.warning(f"Could not find a list of places in '{source_name}.json'. Please check the file structure.")
        return [], []

    # Define how to check for references from each source file
    ref_prefixes = {
        'Origin': 'origloc.xml#',
        'Findspot': 'findsp.xml#',
        'Current': 'currentloc.xml#',
        'General': 'places.xml#'
    }
    ref_prefix = ref_prefixes.get(source_name, '')

    for place in places_list:
        if not isinstance(place, dict):
            continue

        place_id = place.get('_xml:id')
        if not place_id:
            continue
        
        ref_string_to_check = f"{ref_prefix}{place_id}"

        if ref_string_to_check in xml_refs:
            english_name = get_english_place_name(place)
            if not english_name:
                continue
            
            # Add to the textual list regardless of coordinates
            text_points.append({'name': english_name, 'id': place_id})
            
            # For the map, we need coordinates
            geo_coords = place.get('note', {}).get('geo')
            if geo_coords:
                try:
                    lat, lon = map(float, str(geo_coords).split(','))           
                    map_points.append({
                        'name': english_name,
                        'lat': lat,
                        'lon': lon,
                        'source': source_name,
                        'document': doc_id
                    })
                except (ValueError, TypeError):
                    continue # Ignore if geo format is incorrect
                    
    return map_points, text_points

# Configure Streamlit page
st.set_page_config(
    page_title="TEI EpiDoc Visualization",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Helper function to ensure temp directory exists
def ensure_temp_dir():
    temp_dir = Path(tempfile.gettempdir()) / "streamlit_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir

# Configure base paths - handle both local and Hugging Face environments
if os.getenv('SPACE_ID'):  # We're running on HuggingFace
    BASE_DIR = Path('/app/src')
    STATIC_DIR = BASE_DIR / 'static'
    DATA_DIR = BASE_DIR / 'data'
    TEMP_DIR = ensure_temp_dir()
else:  # We're running locally
    BASE_DIR = Path(__file__).resolve().parent
    STATIC_DIR = BASE_DIR / 'static'
    DATA_DIR = BASE_DIR / 'data'
    TEMP_DIR = ensure_temp_dir()

# Define TEI XML namespace
NS = {
    'tei': 'http://www.tei-c.org/ns/1.0',
    'xml': 'http://www.w3.org/XML/1998/namespace'
}

# Add custom font support
@st.cache_data
def load_font(font_path: str) -> str:
    """Reads a font file and returns its base64 encoded version for CSS."""
    try:
        font_file = Path(font_path)
        if not font_file.is_file():
            st.error(f"Font file not found at {font_path}")
            return None
        font_data = font_file.read_bytes()
        encoded_font = base64.b64encode(font_data).decode("utf-8")
        return encoded_font
    except Exception as e:
        st.error(f"Error loading font: {str(e)}")
        return None

def set_font_style(font_name: str, encoded_font: str):
    """Generates the CSS to embed and use the custom font."""
    font_css = f"""
    <style>
        @font-face {{
            font-family: '{font_name}';
            src: url(data:font/truetype;charset=utf-8;base64,{encoded_font}) format('truetype');
            font-weight: normal;
            font-style: normal;
        }}
        .custom-font {{
            font-family: '{font_name}', sans-serif;
            font-size: 22px; /* Adjust font size as needed */
        }}
    </style>
    """
    st.markdown(font_css, unsafe_allow_html=True)

# Add custom fonts (Cyrillic Bulgarian and Roboto)
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
    /* Default fonts */
    * {
        font-family: 'Roboto', sans-serif;
        font-size: 16px; /* Default font size */
        line-height: 1.6; /* Default line height */
    }
    
    /* Church Slavonic specific elements */
    .custom-font,
    .apparatus-text,
    .ocs-text {
        font-family: 'CyrillicaBulgarian10U', sans-serif !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Load and Apply Font ---
FONT_NAME = "CyrillicaBulgarian10U"
FONT_FILE = STATIC_DIR / "CB10U.ttf"


encoded_font = load_font(FONT_FILE)
if encoded_font:
    set_font_style(FONT_NAME, encoded_font)
# Configure base paths
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / 'static'
DATA_DIR = BASE_DIR / 'data'

# Define TEI XML namespace
NS = {
    'tei': 'http://www.tei-c.org/ns/1.0',
    'xml': 'http://www.w3.org/XML/1998/namespace'
}

def safe_find_text(elem, xpath, default="", lang=None):
    """
    Safely find and extract text from an XML element, providing a default if not found.
    Also handles language-specific elements.
    """
    if elem is None:
        return default
    try:
        if lang:
            xpath = f"{xpath}[@xml:lang='{lang}']"
        found = elem.find(xpath, NS)
        if found is not None and found.text:
            return found.text.strip()
        return default
    except Exception as e:
        st.warning(f"Error extracting text using xpath {xpath}: {str(e)}")
        return default

def safe_get_attr(elem, attr_name, default=""):
    """
    Safely get an attribute from an XML element, providing a default if not found.
    """
    if elem is None:
        return default
    try:
        return elem.get(attr_name, default)
    except Exception as e:
        st.warning(f"Error getting attribute {attr_name}: {str(e)}")
        return default

def parse_tei(file):
    try:
        # Make sure we're at the start of the file
        file.seek(0)
        tree = ET.parse(file)
        root = tree.getroot()
        
        # Validate basic TEI structure
        if root.tag != "{http://www.tei-c.org/ns/1.0}TEI":
            st.warning(f"Warning: File doesn't appear to be a valid TEI document. Root element is {root.tag}")
            return None, ""
            
        return root, ET.tostring(root, encoding="unicode")
    except ET.ParseError as e:
        st.error(f"XML Parsing Error: {str(e)}")
        return None, ""
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return None, ""

# Removed old XML authority file loading in favor of JSON



def load_precoded_xmls(folder_path: str) -> list:
    """Load all XML files from the specified folder."""
    xml_files = []
    try:
        for file_name in os.listdir(folder_path):
            if file_name.endswith('.xml'):
                file_path = os.path.join(folder_path, file_name)
                with open(file_path, 'rb') as f:
                    root, raw_xml = parse_tei(f)
                    if root is not None:
                        xml_files.append({
                            'name': file_name,
                            'root': root,
                            'raw_xml': raw_xml                        })
    except Exception as e:
        st.error(f"Error loading XML files from {folder_path}: {str(e)}")
    return xml_files

def load_authority_files():
    """Load authority files from JSON format"""
    try:
        authority_files = {}
        
        # Load materials
        materials_data = {
            "materials": {
                "text": {
                    "body": {
                        "list": {
                            "item": [
                                {
                                    "term": [
                                        {"_xml:lang": "bg", "__text": "камък-други"},
                                        {"_xml:lang": "en", "__text": "stone-other"}
                                    ],
                                    "_xml:id": "st"
                                },
                                # More items here from materials.json
                            ]
                        }
                    }
                }
            }
        }
        
        # Load objects
        objects_data = {
            "objects": {
                "text": {
                    "body": {
                        "list": {
                            "item": [
                                {
                                    "term": [
                                        {"_xml:lang": "bg", "__text": "надгробен паметник"},
                                        {"_xml:lang": "en", "__text": "funerary monument"}
                                    ],
                                    "_xml:id": "funerary-monument"
                                },
                                # More items here from objects.json
                            ]
                        }
                    }
                }
            }
        }
        
        # Load persons
        persons_data = {
            "persons": {
                "text": {
                    "body": {
                        "listPerson": {
                            "person": [
                                {
                                    "persName": [
                                        {"_xml:lang": "bg", "__text": "Калоян"},
                                        {"_xml:lang": "en", "__text": "Kaloyan"}
                                    ],
                                    "_xml:id": "Kalo"
                                },
                                # More persons here from persons.json
                            ]
                        }
                    }
                }
            }
        }
        
        # Load from files if available, otherwise use the hardcoded data
        try:
            authority_path = DATA_DIR / 'authority'
            with open(authority_path / "materials.json", "r", encoding="utf-8") as f:
                materials_data = json.load(f)
            with open(authority_path / "objects.json", "r", encoding="utf-8") as f:
                objects_data = json.load(f)
            with open(authority_path / "persons.json", "r", encoding="utf-8") as f:
                persons_data = json.load(f)
        except Exception as e:
            st.warning(f"Using default authority data: {str(e)}")
        
        authority_files = {
            "materials": materials_data,
            "objects": objects_data,
            "persons": persons_data
        }
        
        return authority_files
    except Exception as e:
        st.error(f"Error loading authority files: {str(e)}")
        return {}

def get_authority_name(ref_id, authority_type, authority_files):
    """Extract English name from authority files based on reference ID"""

     
# Load authority files from JSON

pass
# Load pre-coded XMLs
precoded_xmls = load_precoded_xmls(str(DATA_DIR / 'xmls'))

# Set default renderer for Plotly
# path to your TEI listBibl file
BIBLIO_XML = DATA_DIR / 'bibliography.xml'
biblio_refs = {}
if BIBLIO_XML.exists():
    biblio_refs = load_bibliography(str(BIBLIO_XML))
else:
    st.warning(f"Could not find bibliography file at {BIBLIO_XML}")

# --- Map Helper Functions ---
  
# Create sidebar
with st.sidebar:
    st.image(str(STATIC_DIR / 'imgs/logo.jpg'), width=300, caption="Old Church Slavonic Inscriptions")
    st.header("Project Information")
    
    st.markdown("""
    **Epigraphic Database Viewer-Generic EpiDoc** is a tool designed to visualize and analyze inscriptions.
    
    **Features**:
    - Upload and view XML inscriptions data
    - Explore inscriptions in various formats
    - Visualize geographical origins on an interactive map - not implemented yet
    - Analyze inscriptions with basic statistics
    
    **Developed by**:
    Kristiyan Simeonov, Sofia University
    """)    # Add navigation buttons
   

def safe_find_text(elem, xpath, default="", lang=None):
    """
    Safely find and extract text from an XML element, providing a default if not found.
    Also handles language-specific elements.
    """
    if elem is None:
        return default
    try:
        if lang:
            xpath = f"{xpath}[@xml:lang='{lang}']"
        found = elem.find(xpath, NS)
        if found is not None and found.text:
            return found.text.strip()
        return default
    except Exception as e:
        st.warning(f"Error extracting text using xpath {xpath}: {str(e)}")
        return default

def safe_get_attr(elem, attr_name, default=""):
    """
    Safely get an attribute from an XML element, providing a default if not found.
    """
    if elem is None:
        return default
    try:
        return elem.get(attr_name, default)
    except Exception as e:
        st.warning(f"Error getting attribute {attr_name}: {str(e)}")
        return default

def validate_dimensions(dimensions_elem):
    """
    Validate and extract dimensions from a dimensions element.
    Returns a tuple of (height, width, depth) with appropriate warnings for missing values.
    """
    if dimensions_elem is None:
        return ("", "", "")
    
    height = width = depth = ""
    warnings = []
    
    try:
        height_elem = dimensions_elem.find("tei:height", NS)
        if height_elem is not None and height_elem.text:
            height = height_elem.text.strip()
        else:
            warnings.append("height")
            
        width_elem = dimensions_elem.find("tei:width", NS)
        if width_elem is not None and width_elem.text:
            width = width_elem.text.strip()
        else:
            warnings.append("width")
            
        depth_elem = dimensions_elem.find("tei:depth", NS)
        if depth_elem is not None and depth_elem.text:
            depth = depth_elem.text.strip()
        else:
            warnings.append("depth")
            
        if warnings:
            st.warning(f"Missing dimension values: {', '.join(warnings)}")
            
    except Exception as e:
        st.error(f"Error processing dimensions: {str(e)}")
        return ("", "", "")
        
    return (height, width, depth)

def get_text(elem, xpath, lang=None):
    """
    Helper function to fetch text content for a given XPath.
    Optionally filters by xml:lang attribute.
    """
    if lang:
        xpath = f"{xpath}[@xml:lang='{lang}']"
    found = elem.find(xpath, NS)
    if found is not None and found.text:
        return found.text.strip()
    return ""

def parse_tei(file):
    try:
        # Make sure we're at the start of the file
        file.seek(0)
        tree = ET.parse(file)
        root = tree.getroot()
        
        # Validate basic TEI structure
        if root.tag != "{http://www.tei-c.org/ns/1.0}TEI":
            st.warning(f"Warning: File {file.name} doesn't appear to be a valid TEI document. Root element is {root.tag}")
            return None, ""
            
        # Check for required major sections
        tei_header = root.find("tei:teiHeader", NS)
        text_elem = root.find("tei:text", NS)
        
        if tei_header is None:
            st.warning(f"Warning: File {file.name} is missing teiHeader section")
        if text_elem is None:
            st.warning(f"Warning: File {file.name} is missing text section")
            
        return root, ET.tostring(root, encoding="unicode")
    except ET.ParseError as e:
        st.error(f"XML Parsing Error in file {file.name}: {str(e)}")
        return None, ""
    except Exception as e:
        st.error(f"Error processing file {file.name}: {str(e)}")
        return None, ""

def format_leiden_text(elem):
    """
    Recursively traverse the element tree to create a plain text version of the
    Greek text (edition) with Leiden+ style formatting, covering full EpiDoc cases.
    """
    text = ''
    if elem.text:
        text += elem.text

    for child in elem:
        tag = child.tag.split('}')[-1]

        # Line break without split
        if tag == 'lb' and child.attrib.get('break') == 'no':
            pass
        # Line break
        elif tag == 'lb':
            text += '\n'

        # Text divisions
        elif tag == 'div' and child.attrib.get('type') == 'textpart':
            n = child.attrib.get('n') or ''
            inner = format_leiden_text(child)
            text += f'<D=.{n} {inner} =D>'

        # Unclear letters
        elif tag == 'unclear':
            for ch in (child.text or ''):
                text += f'{ch}\u0323'        # Original letters
        elif tag == 'orig':
            text += f'<span class="orig-text">{child.text or ""}</span>'        # Supplied text
        elif tag == 'supplied':
            reason = child.attrib.get('reason')
            cert = child.attrib.get('cert')
            # Recursively process the content (including nested elements like <g>)
            sup = format_leiden_text(child)
            if reason == 'lost':
                text += f'[{sup}{"?" if cert == "low" else ""}]'
            elif reason == 'undefined':
                text += f'_[{sup}]_'
            elif reason == 'omitted':
                text += f'<{sup}>'
            elif reason == 'subaudible':
                text += f'({sup})'
            else:
                text += sup

         # Abbreviation expansions (handles multiple abbr–ex pairs)
        elif tag == 'expan':
            abbrs = child.findall('tei:abbr', NS)
            exs   = child.findall('tei:ex',   NS)
            for abbr_el, ex_el in zip(abbrs, exs):
                abbr_text = abbr_el.text or ''
                exp_text  = ex_el.text or ''
                # only add parentheses if there's actually expansion text
                if exp_text:
                    cert   = ex_el.attrib.get('cert')
                    suffix = '?' if cert == 'low' else ''
                    text += f"{abbr_text}({exp_text}{suffix})"
                else:
                    text += abbr_text        # Gaps
        elif tag == 'gap':
            # Ellipsis
            if child.attrib.get('reason') == 'ellipsis':
                text += '...'
            else:
                unit = child.attrib.get('unit')
                qty = child.attrib.get('quantity') or ''
                extent = child.attrib.get('extent')
                precision = child.attrib.get('precision')
                cert = child.attrib.get('cert')
                at_least = child.attrib.get('atLeast')
                at_most = child.attrib.get('atMost')

                if unit == 'character':
                    if extent == 'unknown':
                        text += '[.?]'
                    elif at_least and at_most:
                        # Handle range gaps like atLeast="2" atMost="3"
                        cert_marker = '?' if cert == 'low' else ''
                        text += f'[{at_least}-{at_most}{cert_marker}]'
                    elif at_least:
                        # Handle minimum gaps like atLeast="2"
                        cert_marker = '?' if cert == 'low' else ''
                        text += f'[{at_least}+{cert_marker}]'
                    elif at_most:
                        # Handle maximum gaps like atMost="3"
                        cert_marker = '?' if cert == 'low' else ''
                        text += f'[≤{at_most}{cert_marker}]'
                    elif precision == 'low':
                        text += f'[.{qty}]'
                    else:
                        text += '[' + '.' * int(qty or 0) + ']'
                elif unit == 'line':
                    if extent == 'unknown':
                        text += '(Lines: ? non transcribed)'
                    else:
                        text += f'(Lines: {qty} non transcribed)'

        # Deletions
        elif tag == 'del':
            inner = ''.join(child.itertext())
            if child.attrib.get('rend') == 'erasure':
                text += f'〚{inner}〛'
            else:
                text += inner

        # Additions
        elif tag == 'add':
            place = child.attrib.get('place')
            inner = child.text or ''
            if place == 'overstrike':
                text += f'《{inner}》'
            elif place == 'above':
                text += f'`{inner}´'
            elif place == 'below':
                text += f'/{inner}\\'
            else:
                text += inner

        # Corrections and regularizations
        elif tag == 'choice':
            corr = child.find('tei:corr', NS)
            sic = child.find('tei:sic', NS)
            reg = child.find('tei:reg', NS)
            orig = child.find('tei:orig', NS)
            if corr is not None and sic is not None:
                text += f'<{corr.text}|corr|{sic.text}>'
            elif reg is not None and orig is not None:
                text += f'<{orig.text}|reg|{reg.text}>'
            else:
                text += ''.join(child.itertext())

        # Highlighting
        elif tag == 'hi':
            rend = child.attrib.get('rend')
            inner = child.text or ''
            if rend == 'apex':
                text += f'{inner}(΄)'
            elif rend == 'supraline':
                text += f'{inner}¯'
            elif rend == 'ligature':
                text += f'{inner}\u0361'
            else:
                text += inner

        # Abbreviation expansions
        elif tag == 'expan':
            abbr = child.find('tei:abbr', NS)
            ex = child.find('tei:ex', NS)
            if abbr is not None and ex is not None:
                cert = ex.attrib.get('cert')
                text += f"{abbr.text}({ex.text}{'?' if cert=='low' else ''})"

        # Abbreviations, expansions, numerals
        elif tag in ('abbr', 'ex', 'num'):
            text += child.text or ''        # Symbols
        elif tag == 'g':
            type_ = child.attrib.get('type')
            if type_ == 'cross':
                text += '♱'  # EAST SYRIAC CROSS
            elif type_ == 'dipunct':
                text += '։'  # ARMENIAN FULL STOP (U+0589)
            elif type_ == 'dot':
                text += '⸱'  # WORD SEPARATOR MIDDLE DOT
            elif type_:
                text += f'*{type_}*'  # Fallback for other types

        # Superfluous letters
        elif tag == 'surplus':
            text += f'{{{child.text or ""}}}'

        # Notes
        elif tag == 'note':
            note = child.text or ''
            if note in ('!', 'sic', 'e.g.'):
                text += f'/*{note}*/'
            else:
                text += f'({note})'

        # Spaces on stone
        elif tag == 'space':
            unit = child.attrib.get('unit')
            qty = child.attrib.get('quantity')
            extent = child.attrib.get('extent')
            if unit == 'character':
                text += 'vac.?' if extent=='unknown' else f'vac.{qty}'
            elif unit == 'line':
                text += 'vac.?lin' if extent=='unknown' else f'vac.{qty}lin'

        # Word containers
        elif tag == 'w':
            text += format_leiden_text(child)

        # Fallback
        else:
            text += format_leiden_text(child)

        # Tail text
        if child.tail:
            text += child.tail

    return text


def extract_english_text(div, child_tag):
    """
    Extract and join text from all elements with the given child_tag that have xml:lang="en".
    This function works for translation and commentary sections.
    """
    texts = []
    if div is None:
        return ""
    for elem in div.findall(f".//tei:{child_tag}", NS):
        if elem.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") == "en":
            # First try to get text from a note element if it exists
            note = elem.find("tei:note", NS)
            if note is not None and note.text:
                texts.append(note.text.strip())
            # If no note element or no text in note, try the element's direct text
            elif elem.text:
                texts.append(elem.text.strip())
    return "\n".join(texts)

def extract_apparatus_english(div):
    """
    Extract apparatus text from <app> elements in the apparatus section.
    First tries to find the English header, then extracts all notes from app elements.
    """
    texts = []
    if div is None:
        return ""
        
    # First try to get the English header
    head = div.find(".//tei:head[@xml:lang='en']", NS)
    if head is not None and head.text:
        texts.append(head.text.strip())
        
    # Then get all app elements and their notes
    for app in div.findall(".//tei:app", NS):
        if 'loc' in app.attrib:
            line_num = app.attrib['loc']
            notes = []
            for note in app.findall("tei:note", NS):
                if note.text:
                    notes.append(note.text.strip())
            if notes:
                texts.append(f"Line {line_num}: {', '.join(notes)}")
    
    return "\n".join(texts)

def extract_bibliography(div):
    """
    For each <bibl>, if it has @sameAs="bib:ID", lookup the full reference
    in biblio_refs; then, if the element has inner text (the page),
    append ", p.<page>".
    Otherwise fall back to plain <bibl> text.
    """
    texts = []
    if div is None:
        return ""

    for bibl in div.findall(".//tei:bibl", NS):
        same = bibl.get('sameAs', '')
        page = (bibl.text or "").strip()
        entry = None

        # if it's a bib reference, look it up
        if same.startswith('bib:'):
            ref_id = same.split(':', 1)[1]
            entry = biblio_refs.get(ref_id)

        # if we found a lookup entry, use it
        if entry:
            # append page if present
            if page:
                texts.append(f"{entry}, p.{page}")
            else:
                texts.append(entry)
        else:
            # fallback: just output whatever is inside <bibl>
            if page:
                texts.append(page)

    return "\n".join(texts)


def display_monument_images(root, image_data, monument_id):
    """
    Displays monument images from TEI facsimile elements in a modern grid.
    Clicking a thumbnail opens the full-size image in a modal dialog.

    Args:
        root (ET.Element): The root element of the parsed TEI XML.
        image_data (dict): A dictionary where keys are image URLs and values
                           are dictionaries containing image data.
        monument_id (str): Unique identifier for the monument to create unique session state keys.
    """
    facsimile = root.find("tei:facsimile", NS)
    if facsimile is None:
        return

    graphics = facsimile.findall("tei:graphic", NS)
    if graphics is None:
        return

    # Use a subheader for a clear visual separation without nesting expanders.
    st.subheader("Monument Images")    # --- Thumbnail Grid ---
    num_cols = 4  # Adjust the number of columns as you see fit
    cols = st.columns(num_cols)

    for i, graphic in enumerate(graphics):
        url = graphic.get("url")
        # Look for image by filename in our hardcoded images
        image_filename = None
        for img_name in image_data.keys():
            if url and (url in img_name or img_name in url):
                image_filename = img_name
                break
        
        if not image_filename:
            continue

        with cols[i % num_cols]:
            # Display the thumbnail image
            st.image(
                image_data[image_filename]["data"],
                caption=f"Image {i + 1}",
                use_container_width=True
            )
            # Button to trigger the dialog for the full-size image with unique key
            dialog_key = f"dialog_image_url_{monument_id}"
            if st.button("🔍 View", key=f"view_dialog_{monument_id}_{image_filename}_{i}"):
                st.session_state[dialog_key] = image_filename    # --- Modal Logic ---
    # This part will activate when a "View" button is clicked.
    dialog_key = f"dialog_image_url_{monument_id}"
    if dialog_key in st.session_state and st.session_state[dialog_key]:
        image_filename = st.session_state[dialog_key]
        modal = st.container()
        modal.image(
            image_data[image_filename]["data"],
            caption=f"Full-size view of {image_filename}",
            use_container_width=True
        )
        if modal.button("Close", key=f"close_dialog_{monument_id}_{image_filename}"):
            # To close the modal, we remove the trigger from session state
            # and rerun the script.
            del st.session_state[dialog_key]
            st.rerun()


# Network analysis functions
def prepare_network_data(all_data, parsed_files):
    """Prepare network data for visualization in the Network View page."""
    if not all_data or not parsed_files:
        st.warning("No data loaded. Please upload and process XML files first.")
        return

    # Store the processed data in session state for the network visualization page
    network_data = []
    df = pd.DataFrame(all_data)
    for _, row in df.iterrows():
        # Store all the data we will need for network visualization
        node_data = {
            "inscription": row["Title"] if row.get("Title") else row["ID"],
            "decade": row.get("Date", "Unknown"),
            "material_": row.get("Material", "Unknown"),
            "object": row.get("Type", "Unknown"),
            "origloc": row.get("Origin", "Unknown")
        }
        network_data.append(node_data)
    
    # Store data in session state for the network visualization page
    st.session_state['network_data'] = pd.DataFrame(network_data)
    st.session_state['processed_files'] = parsed_files

    # Show instructions to use the Network View page
    st.info("Network visualization is now available in the Network View page! 🔗\n\nClick on 'Network View' in the sidebar to explore interactive network visualizations of your data.")

    # Create graph
  
precoded_xmls = load_precoded_xmls(str(DATA_DIR / 'xmls'))

st.title("TEI Monument Visualization (Plain Text Versions)")

st.markdown("""
This application displays scholarly records of ancient Greek inscriptions from pre-loaded TEI XML files.
The application automatically loads XML files from the data/xmls folder and images from the images folder.
For the apparatus, translation, commentary, and bibliography sections only the English text is extracted and displayed as plain text.
""")

def load_hardcoded_images():
    """Load all images from the hardcoded images folder."""
    image_data = {}
    images_dir = BASE_DIR / 'images'
    
    if not images_dir.exists():
        st.warning(f"Images directory not found at {images_dir}")
        return image_data
    
    try:
        # Look for common image file extensions
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.tiff']
        
        for extension in image_extensions:
            for img_path in images_dir.glob(extension):
                try:
                    with open(img_path, 'rb') as f:
                        img_bytes = f.read()
                    
                    # Create a BytesIO object that behaves like an uploaded file
                    image_bytes = BytesIO(img_bytes)
                    
                    # Verify the image can be opened
                    with Image.open(image_bytes) as pil_img:
                        # Reset BytesIO for storing
                        image_bytes.seek(0)
                        image_data[img_path.name] = {
                            'data': image_bytes,
                            'type': img_path.suffix.lower()
                        }
                except Exception as e:
                    st.warning(f"Could not process image {img_path.name}: {str(e)}")
                    continue
        
        if image_data:
            st.info(f"Loaded {len(image_data)} images from the images folder")
        else:
            st.info("No images found in the images folder")
            
    except Exception as e:
        st.error(f"Error loading images from directory: {str(e)}")
    
    return image_data

# Load pre-coded XML files and hardcoded images
working_files = []
working_files.extend(precoded_xmls)

# Load hardcoded images
image_data = load_hardcoded_images()

# Continue with file processing only if we have files to work with
if working_files:
    # Create tabs for visualization, querying, analytics, and map view
    viz_tab, query_tab, analytics_tab, map_tab = st.tabs(["Data Visualization", "Search & Query", "Analytics", "Map View"])
    
    # Create data structures for analytics, search, and file storage
    all_data = []
    unique_types = set()
    unique_materials = set()
    unique_categories = set()
    parsed_files = []  # Store parsed file data
    
    # Process all working files (both pre-coded and uploaded)
    for file_data in working_files:
        root = file_data['root']
        if root is not None:
            # Store the parsed data
            parsed_files.append(file_data)
            ms_desc = root.find(".//tei:msDesc", NS)
            if ms_desc is not None:
                # Collect monument type
                object_type = get_text(ms_desc, ".//tei:objectType", lang="en")
                if object_type:
                    unique_types.add(object_type.lower())
                
                # Collect material
                material = get_text(ms_desc, ".//tei:material", lang="en")
                if material:
                    unique_materials.add(material.lower())
                
                # Collect category
                summary = ms_desc.find(".//tei:summary", NS)
                if summary is not None:
                    category = get_text(summary, ".//tei:seg", lang="en")
                    if category:
                        unique_categories.add(category.lower())
    
    # Prepare network data after processing all files
    if all_data:
        prepare_network_data(all_data, parsed_files)
    
    # --- Data Visualization Tab ---
    with viz_tab:
        st.header("Monument Documents")
        st.info("Click on each monument to view its details")
        
        for file_data in parsed_files:
            # Get monument ID first
            root = file_data['root']
            publication_stmt = root.find("tei:teiHeader/tei:fileDesc/tei:publicationStmt", NS)
            mon_id = get_text(publication_stmt, "tei:idno[@type='filename']")
            
            with st.expander(f"Monument {mon_id if mon_id else file_data['name']}"):
                st.markdown("---")  # Separator between documents
                
                # Get the title from the XML and use it as the main header
                title_element = root.find(".//tei:title[@xml:lang='en']", NS)
                document_title = title_element.text if title_element is not None and title_element.text else f"Document: {file_data['name']}"
                
                # Display the title in a larger, more prominent format
                st.markdown(f"<h1 style='text-align: center; font-size: 32px; margin-bottom: 30px;'>{document_title}</h1>", unsafe_allow_html=True)
                
                raw_xml = file_data['raw_xml']

                # --- Extract key sections from the TEI header ---
                tei_header = root.find("tei:teiHeader", NS)
                file_desc = tei_header.find("tei:fileDesc", NS) if tei_header is not None else None
                title_stmt = file_desc.find("tei:titleStmt", NS) if file_desc is not None else None
                publication_stmt = file_desc.find("tei:publicationStmt", NS) if file_desc is not None else None
                source_desc = file_desc.find("tei:sourceDesc", NS) if file_desc is not None else None
                ms_desc = source_desc.find("tei:msDesc", NS) if source_desc is not None else None

                # Monument Title using the idno from publicationStmt.
                mon_id = get_text(publication_stmt, "tei:idno[@type='filename']")
                monument_title = f"Monument {mon_id}" if mon_id else "Monument"

                # Editor(s) from titleStmt (English preferred if available).
                editors = title_stmt.findall("tei:editor/tei:persName[@xml:lang='en']", NS) if title_stmt is not None else []
                editor_names = [ed.text.strip() for ed in editors if ed.text]
                editor_str = ", ".join(editor_names) if editor_names else "Not available"

                # --- Extract information from physDesc ---
                phys_desc = ms_desc.find("tei:physDesc", NS) if ms_desc is not None else None
                object_desc = phys_desc.find("tei:objectDesc", NS) if phys_desc is not None else None
                support_desc = object_desc.find("tei:supportDesc", NS) if object_desc is not None else None
                support = support_desc.find("tei:support", NS) if support_desc is not None else None
                object_type = get_text(support, "tei:objectType", lang="en")
                material = get_text(support, "tei:material", lang="en")

                # Institution and Inventory (from msIdentifier - English variant).
                ms_identifier = ms_desc.find("tei:msIdentifier", NS) if ms_desc is not None else None
                alt_identifier = ms_identifier.find("tei:altIdentifier[@xml:lang='en']", NS) if ms_identifier is not None else None
                institution = ""
                repository = alt_identifier.find("tei:repository", NS) if alt_identifier is not None else None
                if repository is not None:
                    ref = repository.find("tei:ref", NS)
                    if ref is not None and ref.text:
                        institution = ref.text.strip()
                inventory = get_text(alt_identifier, "tei:idno")                # Dimensions (height, width, depth).
                dimensions = support.find("tei:dimensions", NS) if support is not None else None
                # In case dimensions are in layoutDesc instead of dimensions
                layout_desc = object_desc.find("tei:layoutDesc/tei:layout", NS) if object_desc is not None else None
                  # Try to get dimensions from either dimensions or layout elements
                height = ""
                width = ""
                depth = ""
                diameter = ""
                
                if dimensions is not None:
                    height_elem = dimensions.find("tei:height", NS)
                    width_elem = dimensions.find("tei:width", NS)
                    depth_elem = dimensions.find("tei:depth", NS)
                    # Look for diameter using dim element with type="diameter"
                    diameter_elem = dimensions.find("tei:dim[@type='diameter']", NS)
                      # Extract text safely from elements
                    if height_elem is not None:
                        height_text = height_elem.text
                        height = height_text.strip() if height_text is not None else ""
                    
                    if width_elem is not None:
                        width_text = width_elem.text
                        width = width_text.strip() if width_text is not None else ""
                    
                    if depth_elem is not None:
                        depth_text = depth_elem.text
                        depth = depth_text.strip() if depth_text is not None else ""
                    
                    if diameter_elem is not None:
                        diameter_text = diameter_elem.text
                        diameter = diameter_text.strip() if diameter_text is not None else ""
                  # If dimensions not found in dimensions element, try layout
                if not any([height, width, depth, diameter]) and layout_desc is not None:
                    # Look for lenght/length (handle both spellings), width, height in layout
                    height_elem = layout_desc.find("tei:lenght|tei:length", NS)
                    width_elem = layout_desc.find("tei:width", NS)
                    depth_elem = layout_desc.find("tei:depth", NS)
                    # Also look for diameter in layout
                    diameter_elem = layout_desc.find("tei:dim[@type='diameter']", NS)
                    
                    # Extract text safely from layout elements
                    if height_elem is not None:
                        height_text = height_elem.text
                        height = height_text.strip() if height_text is not None else ""
                    
                    # If there are multiple width elements, take the first one
                    if width_elem is not None:
                        width_text = width_elem.text
                        width = width_text.strip() if width_text is not None else ""
                    
                    if depth_elem is not None:
                        depth_text = depth_elem.text
                        depth = depth_text.strip() if depth_text is not None else ""
                    
                    if diameter_elem is not None:
                        diameter_text = diameter_elem.text
                        diameter = diameter_text.strip() if diameter_text is not None else ""

                # Letter size from hand description - extract safely
                hand_desc = phys_desc.find("tei:handDesc", NS) if phys_desc is not None else None
                hand_note = hand_desc.find("tei:handNote", NS) if hand_desc is not None else None
                letter_size = ""
                if hand_note is not None:
                    height_elem = hand_note.find("tei:height", NS)
                    if height_elem is not None and height_elem.text is not None:
                        letter_size = height_elem.text.strip()

                # Layout description (English).
                layout_desc = object_desc.find("tei:layoutDesc", NS) if object_desc is not None else None
                layout = get_text(layout_desc, "tei:layout", lang="en")

                # Find Place from history -> provenance (type="found").
                history = ms_desc.find("tei:history", NS) if ms_desc is not None else None
                provenance_found = None
                if history is not None:
                    for prov in history.findall("tei:provenance", NS):
                        if prov.attrib.get("type", "") == "found":
                            provenance_found = prov
                            break
                find_place = ""
                if provenance_found is not None:
                    seg = provenance_found.find("tei:seg[@xml:lang='en']", NS)
                    if seg is not None and seg.text:
                        find_place = seg.text.strip()

                # Extract origin, dating and provenance information
                origin_info = {}
                dating_info = {}
                provenance_info = {'found': {}, 'observed': {}}
                
                if history is not None:
                    origin_elem = history.find("tei:origin", NS)
                    if origin_elem is not None:
                        # Get origPlace information with reference
                        orig_place = origin_elem.find("tei:origPlace", NS)
                        if orig_place is not None:
                            origin_info['ref'] = orig_place.get('ref', '')
                            # Get English and Bulgarian text
                            for lang in ['en', 'bg']:
                                seg = orig_place.find(f"tei:seg[@xml:lang='{lang}']", NS)
                                if seg is not None and seg.text:
                                    origin_info[lang] = seg.text.strip()
                        
                        # Get dating information
                        orig_date = origin_elem.find("tei:origDate", NS)
                        if orig_date is not None:
                            dating_info['notBefore'] = orig_date.get('notBefore', '')
                            dating_info['notAfter'] = orig_date.get('notAfter', '')
                            dating_info['evidence'] = orig_date.get('evidence', '')
                            # Get English and Bulgarian text
                            for lang in ['en', 'bg']:
                                seg = orig_date.find(f"tei:seg[@xml:lang='{lang}']", NS)
                                if seg is not None and seg.text:
                                    dating_info[lang] = seg.text.strip()
                    
                    # Get provenance information
                    for prov_type in ['found', 'observed']:
                        prov = history.find(f"tei:provenance[@type='{prov_type}']", NS)
                        if prov is not None:
                            provenance_info[prov_type]['when'] = prov.get('when', '')
                            # Get English and Bulgarian place names
                            for lang in ['en', 'bg']:
                                seg = prov.find(f"tei:seg[@xml:lang='{lang}']/tei:placeName", NS)
                                if seg is not None:
                                    provenance_info[prov_type][lang] = {
                                        'text': seg.text.strip() if seg.text else '',
                                        'ref': seg.get('ref', '')
                                    }

                # Category of inscription from msContents -> summary (English).
                ms_contents = ms_desc.find("tei:msContents", NS) if ms_desc is not None else None
                summary = ms_contents.find("tei:summary", NS) if ms_contents is not None else None
                inscription_category = ""
                if summary is not None:
                    seg = summary.find("tei:seg[@xml:lang='en']", NS)
                    if seg is not None and seg.text:
                        inscription_category = seg.text.strip()

                # --- Extract textual content from the body element ---
                text_elem = root.find("tei:text", NS)
                body_elem = text_elem.find("tei:body", NS) if text_elem is not None else None

                # We will look for each <div> element by its type.
                edition_div = None  # Greek text (edition) remains as-is.
                apparatus_div = None
                translation_div = None
                commentary_div = None
                biblio_div = None

                if body_elem is not None:
                    for div in body_elem.findall("tei:div", NS):
                        div_type = div.attrib.get("type", "")                # Check for edition in Greek or Church Slavonic
                        if div_type == "edition" and div.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") in ["grc", "chu"]:
                            edition_div = div
                        elif div_type == "apparatus":
                            apparatus_div = div
                        elif div_type == "translation":
                            translation_div = div
                        elif div_type == "commentary":
                            commentary_div = div
                        elif div_type == "bibliography":
                            biblio_div = div

                # Format the Greek edition text using Leiden+ formatting.
                if edition_div is not None:
                    leiden_text = format_leiden_text(edition_div)
                else:
                    leiden_text = "No Greek edition text available."

                # Extract plain text for apparatus, translation, commentary using only English segments.
                apparatus_text = extract_apparatus_english(apparatus_div)
                translation_text = extract_english_text(translation_div, "seg")
                commentary_text = extract_english_text(commentary_div, "seg")
                bibliography_text = extract_bibliography(biblio_div)

                # --- Display the information ---
                st.subheader("Monument Information")
                st.markdown(f"- **Editor(s):** {editor_str}")
                st.markdown(f"- **Type of monument:** {object_type if object_type else 'Not available'}")
                st.markdown(f"- **Material:** {material if material else 'Not available'}")

                # Display find spot information properly
                if provenance_info and 'found' in provenance_info and provenance_info['found']:
                    found_info = provenance_info['found']
                    st.markdown("##### Find Spot Information")
                    if 'when' in found_info:
                        st.markdown(f"- **Found in year:** {found_info['when']}")
                    if 'en' in found_info:
                        st.markdown(f"- **Location:** {found_info['en']['text']}")
                        if found_info['en']['ref']:
                            st.markdown(f"- **Reference:** {found_info['en']['ref']}")
                          # Display origin and dating information
                if origin_info:
                    st.markdown("##### Origin Information")
                    if 'en' in origin_info:
                        st.markdown(f"- **Location:** {origin_info['en']}")
                    if 'ref' in origin_info:
                        st.markdown(f"- **Reference:** {origin_info['ref']}")
                  # Display basic information
                st.markdown(f"- **Institution and Inventory:** {institution} No {inventory}")
                
                # Build dimensions string dynamically based on available values
                dimensions_parts = []
                if height:
                    dimensions_parts.append(f"Height {height} cm")
                if width:
                    dimensions_parts.append(f"width {width} cm")
                if depth:
                    dimensions_parts.append(f"depth {depth} cm")
                if diameter:
                    dimensions_parts.append(f"diameter {diameter} cm")
                
                if dimensions_parts:
                    dimensions_str = ", ".join(dimensions_parts)
                    st.markdown(f"- **Dimensions:** {dimensions_str}")
                else:
                    st.markdown("- **Dimensions:** Not available")
                
                st.markdown(f"- **Letter size:** Height {letter_size} cm")
                st.markdown(f"- **Layout description:** {layout if layout else 'Not available'}")
                st.markdown("- **Decoration description:** (appears to be blank)")
                st.subheader("Dating and Location Information")
                st.markdown(f"- **Category of inscription:** {inscription_category}")
                
                # Display facsimile images if available
                display_monument_images(root, image_data, mon_id)                # Original Text Section with Old Church Slavonic Font
                st.subheader("Original Text (Old Church Slavonic)")
                st.markdown("""
                <style>
                    .ocs-text {
                        background-color: #f5f5f5;
                        padding: 20px;
                        border-radius: 5px;
                        font-size: 24px;
                        line-height: 1.6;
                        margin: 10px 0;
                    }
                    .orig-text {
                        font-style: italic;
                        background: #fff4e5;
                        font-family: 'CyrillicaBulgarian10U';
                        font-size: 24px;
                    }
                </style>
                """, unsafe_allow_html=True)

                if edition_div is not None:
                    # Format the text using Leiden+ conventions
                    formatted_text = format_leiden_text(edition_div)
                    # Clean up extra newlines while preserving intentional line breaks
                    formatted_text = "\n".join(line for line in formatted_text.splitlines() if line.strip())
                    # Display the text with the custom font and styling
                    st.markdown(
                        f'<div class="ocs-text custom-font">{formatted_text.replace(chr(10), "<br>")}</div>', 
                        unsafe_allow_html=True
                    )
                else:
                    st.write("No Church Slavonic text available.")

                # Translation Section
                st.subheader("Translation (English)")
                if translation_text:
                    st.markdown(translation_text)
                else:
                    st.write("No translation available.")

                # Display apparatus text if available
                if apparatus_text:
                    st.subheader("Apparatus (English)")
                    st.markdown("""
                    <style>
                        .apparatus-text {
                            background-color: #ffffff;
                            padding: 10px;
                            border-radius: 5px;
                            font-size: 18px;
                            line-height: 1.6;
                            font-family: 'CyrillicaBulgarian10U', sans-serif;
                        }
                    </style>
                    """, unsafe_allow_html=True)
                    st.markdown(f'<div class="apparatus-text">{apparatus_text}</div>', unsafe_allow_html=True)
                else:
                    st.write("No apparatus notes available.")

                # Commentary Section
                st.subheader("Commentary (English)")
                if commentary_text:
                    st.markdown(commentary_text)
                else:
                    st.write("No commentary available.")

                # Bibliography Section
                st.subheader("Bibliography")
                if bibliography_text:
                    st.text(bibliography_text)
                else:
                    st.write("No bibliography available.")

                # Provide a download button for the raw XML.
                st.download_button(
                    label="Download Original XML",
                    data=raw_xml,
                    file_name=mon_id + ".xml" if mon_id else "tei_document.xml",
                    mime="text/xml"
                )            # Collect data for analytics
            monument_data = {
                'Title': monument_title,
                'ID': mon_id if mon_id else "Unknown",
                'Type': object_type if object_type else 'Not available',
                'Material': material if material else 'Not available',
                'Origin': origin_info.get('en', 'Not available'),
                'Date': dating_info.get('en', 'Not available'),
                'Category': inscription_category if inscription_category else 'Not available'
            }
            all_data.append(monument_data)

    with query_tab:
        st.header("Search & Query TEI Documents")
        
        # Dynamic search categories from loaded documents
        search_categories = {
            'Monument Types': sorted(list(unique_types)) if unique_types else ['No types found'],
            'Materials': sorted(list(unique_materials)) if unique_materials else ['No materials found'],
            'Categories': sorted(list(unique_categories)) if unique_categories else ['No categories found'],
            'Custom Search': ['custom']
        }
        
        # Show available options
        st.sidebar.subheader("Available Search Terms")
        if st.sidebar.checkbox("Show available terms"):
            st.sidebar.markdown("**Monument Types:**")
            st.sidebar.write(sorted(list(unique_types)))
            st.sidebar.markdown("**Materials:**")
            st.sidebar.write(sorted(list(unique_materials)))
            st.sidebar.markdown("**Categories:**")
            st.sidebar.write(sorted(list(unique_categories)))
        
        search_category = st.selectbox("Select search category", list(search_categories.keys()))
        
        if search_category == 'Custom Search':
            search_term = st.text_input("Enter custom search term")
        else:
            search_term = st.selectbox(f"Select {search_category}", search_categories[search_category])
            
        search_field = st.selectbox(
            "Select where to search",
            ["All Fields", "Monument Information", "Church Slavonic Text", "Translation", "Commentary", "Bibliography"]
        )
        
        # Debug information to help users
        st.info("💡 Note: Monument Information includes type, material, origin, etc.")

        if search_term and search_term != 'custom':
            search_term_lower = search_term.lower().strip()
            results = []  # Store all matches here
            
            for file_data in parsed_files:
                root = file_data['root']
                file_name = file_data['name']
                file_matches = []  # Store matches for this file
                
                # Extract monument information first
                tei_header = root.find("tei:teiHeader", NS)
                if tei_header is not None:
                    ms_desc = tei_header.find(".//tei:msDesc", NS)
                    if ms_desc is not None and search_field in ["All Fields", "Monument Information"]:
                        # Check type
                        object_type = get_text(ms_desc, ".//tei:objectType", lang="en")
                        if object_type and search_term_lower in object_type.lower():
                            file_matches.append(("Monument Type", object_type))
                        
                        # Check material
                        material = get_text(ms_desc, ".//tei:material", lang="en")
                        if material and search_term_lower in material.lower():
                            file_matches.append(("Material", material))
                        
                        # Check origin
                        origin = get_text(ms_desc, ".//tei:origin//tei:origPlace//tei:seg[@xml:lang='en']")
                        if origin and search_term_lower in origin.lower():
                            file_matches.append(("Origin", origin))
                
                # Search in text sections if needed
                body_elem = root.find("tei:text/tei:body", NS)
                if body_elem is not None:
                    for div in body_elem.findall("tei:div", NS):
                        div_type = div.attrib.get("type", "")
                        
                        # Search Greek Text
                        if div_type == "edition" and search_field in ["Greek Text", "All Fields"]:
                            if div.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") == "grc":
                                text = format_leiden_text(div)
                                if text and search_term_lower in text.lower():
                                    file_matches.append(("Greek Text", text))
                        
                        # Search Translation
                        elif div_type == "translation" and search_field in ["Translation", "All Fields"]:
                            text = extract_english_text(div, "seg")
                            if text and search_term_lower in text.lower():
                                file_matches.append(("Translation", text))
                        
                        # Search Commentary
                        elif div_type == "commentary" and search_field in ["Commentary", "All Fields"]:
                            text = extract_english_text(div, "seg")
                            if text and search_term_lower in text.lower():
                                file_matches.append(("Commentary", text))
                        
                        # Search Bibliography
                        elif div_type == "bibliography" and search_field in ["Bibliography", "All Fields"]:
                            text = extract_bibliography(div)
                            if text and search_term_lower in text.lower():
                                file_matches.append(("Bibliography", text))
                
                # If we found matches in this file, add them to the results
                if file_matches:
                    results.append({
                        'file_name': file_name,
                        'matches': file_matches
                    })
              # Only display results if we found any matches
            if results:
                st.subheader("Search Results")
                for result in results:
                    with st.expander(f"Results from {result['file_name']}"):
                        # Show match details
                        for section, content in result['matches']:
                            st.markdown(f"**Found in {section}:**")
                            st.text(content)
                        
                        # Add button to view the full document
                        if st.button("View Full Document", key=f"view_{result['file_name']}"):
                            st.markdown("---")
                            st.subheader(f"Full Document: {result['file_name']}")
                            
                            # Get the file data for this result
                            file_data = next((f for f in parsed_files if f['name'] == result['file_name']), None)
                            if file_data:
                                root = file_data['root']
                                
                                # Display monument title
                                title = root.find(".//tei:title[@xml:lang='en']", NS)
                                if title is not None and title.text:
                                    st.markdown(f"### {title.text}")
                                
                                # Display monument information
                                ms_desc = root.find(".//tei:msDesc", NS)
                                if ms_desc is not None:
                                    st.markdown("### Monument Information")
                                    
                                    # Display object type and material
                                    object_type = get_text(ms_desc, ".//tei:objectType", lang="en")
                                    material = get_text(ms_desc, ".//tei:material", lang="en")
                                    if object_type:
                                        st.markdown(f"- **Type:** {object_type}")
                                    if material:
                                        st.markdown(f"- **Material:** {material}")
                                
                                # Display each section from the document
                                body = root.find("tei:text/tei:body", NS)
                                if body is not None:
                                    for div in body.findall("tei:div", NS):
                                        div_type = div.get("type")
                                        if div_type:
                                            st.markdown(f"### {div_type.title()}")
                                            if div_type == "edition":
                                                # Apply styling for edition text
                                                st.markdown("""
                                                    <style>
                                                        .edition-text {
                                                            background-color: #f5f5f5;
                                                            padding: 20px;
                                                            border-radius: 5px;
                                                            font-size: 24px;
                                                            line-height: 1.6;
                                                            margin: 10px 0;
                                                            font-family: 'CyrillicaBulgarian10U', sans-serif;
                                                        }
                                                    </style>
                                                """, unsafe_allow_html=True)
                                                formatted_text = format_leiden_text(div)
                                                formatted_text = "\n".join(line for line in formatted_text.splitlines() if line.strip())
                                                st.markdown(f'<div class="edition-text">{formatted_text.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
                                            elif div_type == "apparatus":
                                                # Apply styling for apparatus text
                                                st.markdown("""
                                                    <style>
                                                        .apparatus-text {
                                                            background-color: #ffffff;
                                                            padding: 10px;
                                                            border-radius: 5px;
                                                            font-size: 18px;
                                                            line-height: 1.6;
                                                            font-family: 'CyrillicaBulgarian10U', sans-serif;
                                                        }
                                                    </style>
                                                """, unsafe_allow_html=True)
                                                apparatus_text = extract_apparatus_english(div)
                                                if apparatus_text:
                                                    st.markdown(f'<div class="apparatus-text">{apparatus_text}</div>', unsafe_allow_html=True)
                                            elif div_type == "translation":
                                                st.markdown(extract_english_text(div, "seg"))
                                            elif div_type == "commentary":
                                                st.markdown(extract_english_text(div, "seg"))
                                            elif div_type == "bibliography":
                                                st.markdown(extract_bibliography(div))
                                
                                # Display images if available
                                display_monument_images(root, image_data, result['file_name'])
                            else:
                                     st.info("No matches found for your search criteria.")


    with analytics_tab:
        st.header("Analytics & Visualizations")
        if all_data:
            df = pd.DataFrame(all_data)
            
            # Create a bar chart of monument types
            st.subheader("Distribution of Monument Types")
            type_counts = df['Type'].value_counts()
            fig_types = px.bar(
                x=type_counts.index, 
                y=type_counts.values,
                title="Monument Types Distribution",
                labels={'x': 'Type', 'y': 'Count'}
            )
            st.plotly_chart(fig_types)
            
            # Create a pie chart of materials
            st.subheader("Distribution of Materials")
            material_counts = df['Material'].value_counts()
            fig_materials = px.pie(
                values=material_counts.values,
                names=material_counts.index,
                title="Materials Distribution"
            )
            st.plotly_chart(fig_materials)
            
            # Create a timeline of monuments
            st.subheader("Timeline of Monuments")
            fig_timeline = px.scatter(
                df,
                x='Date',
                y='Category',
                color='Type',
                hover_data=['Title', 'Material'],
                title="Monuments Timeline"
            )
            st.plotly_chart(fig_timeline)
            
            # Show raw data
            st.subheader("Raw Data")
            st.dataframe(df)        
        else:
            st.write("No data available for visualization. Please upload some XML files first.")  
    with map_tab:
        st.header("Interactive Map of Linked Epigraphic Monument Locations")

        # Load authority files directly from the data directory
        authority_files = {
            'origloc': DATA_DIR / 'authority' / 'origloc.json',
            'findspot': DATA_DIR / 'authority' / 'Findspot.json',
            'currentloc': DATA_DIR / 'authority' / 'currentloc.json',
            'places': DATA_DIR / 'authority' / 'places.json'
        }
        
        # --- Map Helper Functions ---
        def create_leaflet_map(df):
            # Create a map centered at the mean coordinates
            m = folium.Map(location=[df['lat'].mean(), df['lon'].mean()], zoom_start=5)
            
            # Color mapping for sources
            color_lookup = {
                'Origin': 'red',
                'Findspot': 'green',
                'Current': 'blue',
                'General': 'orange'
            }
            
            # Add points to the map
            for idx, row in df.iterrows():
                color = color_lookup.get(row['source'], 'gray')
                folium.CircleMarker(
                    location=[row['lat'], row['lon']],
                    radius=8,
                    popup=f"<b>Name:</b> {row['name']}<br/><b>Source:</b> {row['source']}<br/><b>Document:</b> {row['document']}",
                    color=color,
                    fill=True,
                    fillOpacity=0.7
                ).add_to(m)
            
            return m

        def create_pydeck_map(df):
            # Get Mapbox token from environment variable
            mapbox_token = os.environ.get('MAP_BOX_TOKEN')
            
            # Define colors for each source
            color_lookup = {
                'Origin': [255, 0, 0, 160],      # Red
                'Findspot': [0, 255, 0, 160],    # Green
                'Current': [0, 0, 255, 160],     # Blue
                'General': [255, 255, 0, 160]    # Yellow
            }
            df['color'] = df['source'].apply(lambda s: color_lookup.get(s, [128, 128, 128, 160]))

            # Center the map on the mean of the coordinates
            initial_view_state = pdk.ViewState(
                latitude=df['lat'].mean(),
                longitude=df['lon'].mean(),
                zoom=5,
                pitch=50,
            )

            # Define the map layer
            layer = pdk.Layer(
                'ScatterplotLayer',
                data=df,
                get_position='[lon, lat]',
                get_color='color',
                get_radius=5000,
                pickable=True,
                auto_highlight=True
            )

            # Define the tooltip with document information
            tooltip = {
                "html": "<b>Name:</b> {name}<br/><b>Source:</b> {source}<br/><b>Document:</b> {document}",
                "style": {
                    "backgroundColor": "steelblue",
                    "color": "white",
                }
            }

            # Create and return the PyDeck map - conditionally add mapbox style only if token exists
            deck_args = {
                'initial_view_state': initial_view_state,
                'layers': [layer],
                'tooltip': tooltip
            }
            
            # Only add Mapbox properties if token is available
            if mapbox_token:
                deck_args['map_style'] = 'mapbox://styles/mapbox/light-v11'
                deck_args['mapbox_key'] = mapbox_token
            
            return pdk.Deck(**deck_args)

        # Load authority files
        json_data = {}
        for key, file_path in authority_files.items():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    json_data[key] = json.load(f)
            except Exception as e:
                st.warning(f"Could not load {key}.json: {e}")
                continue

        all_map_points = []
        all_text_points = {}        # Process each XML file and collect references
        for file_data in working_files:
            root = file_data['root']
            if root is None:
                continue

            # Get the document ID/name
            publication_stmt = root.find("tei:teiHeader/tei:fileDesc/tei:publicationStmt", NS)
            doc_id = get_text(publication_stmt, "tei:idno[@type='filename']")
            doc_name = doc_id if doc_id else file_data['name']

            # Convert XML tree to string for processing
            xml_string = ET.tostring(root, encoding='unicode')
            xml_refs = get_xml_references(xml_string)

            if not xml_refs:
                continue            # Get the document title for better display
            title_element = root.find(".//tei:title[@xml:lang='en']", NS)
            doc_title = title_element.text if title_element is not None and title_element.text else doc_name

            # Extract points from all JSON files
            for source_name, json_obj in [
                ('Origin', json_data.get('origloc')),
                ('Findspot', json_data.get('findspot')),
                ('Current', json_data.get('currentloc')),
                ('General', json_data.get('places'))
            ]:
                if json_obj:
                    map_points, text_points = extract_referenced_places(json_obj, source_name, xml_refs, doc_title)
                    all_map_points.extend(map_points)
                    
                    if source_name not in all_text_points:
                        all_text_points[source_name] = []
                    
                    # Add document information to text points
                    for point in text_points:
                        point['xml_source'] = doc_title
                    all_text_points[source_name].extend(text_points)

        # Create the Map Visualization if points were found
        if all_map_points:
            df = pd.DataFrame(all_map_points)

            def display_map_visualization(df):
                """Displays either a 2D or  3D map based on user selection."""

                if df.empty:
                    st.warning("No location data available to display on the map.")
                    return
                
                # Add map type selector
                map_type = st.radio("Select Map Type", ["2D Map", "3D Map"], horizontal=True)
                
                # Create and display the selected map type
                if map_type == "2D Map":
                    m = create_leaflet_map(df)
                    if m:
                        st_folium( m,
                        center=[ df['lat'].mean(), df['lon'].mean() ],
                        zoom=5,                        
                        key="user-map",
                        returned_objects=[],
                        use_container_width=True,
                        height=500,)

                else:  # 3D Map
                    deck = create_pydeck_map(df)
                    if deck:
                        st.pydeck_chart(deck)

            # Add a legend for the map
            st.markdown("""
            **Map Legend**
            - <span style="color:red; font-weight:bold;">Red:</span> Origin Location
            - <span style="color:green; font-weight:bold;">Green:</span> Findspot Location
            - <span style="color:blue; font-weight:bold;">Blue:</span> Current Location
            - <span style="color:orange; font-weight:bold;">Yellow:</span> General Place
            """, unsafe_allow_html=True)

            # Display the map visualization
            display_map_visualization(df)
        else:
            st.info("No locations with geographic coordinates were found referenced in the XML files.")

        # Display the textual summary
        st.header("Textual Summary of Linked Places")
        for source, points in all_text_points.items():
            with st.expander(f"Linked Places from: {source}", expanded=False):
                if points:
                    # Remove duplicates while preserving order
                    seen = set()
                    unique_points = []
                    for point in points:
                        point_id = point['id']
                        if point_id not in seen:
                            seen.add(point_id)
                            unique_points.append(point)     
                    for point in unique_points:
                        if 'xml_source' in point:
                            st.success(f"**{point['name']}** (ID: `{point['id']}`)\n\nFound in document: {point['xml_source']}")
                        else:
                            st.success(f"**{point['name']}** (ID: `{point['id']}`)")
                else:
                    st.warning(f"No connections found for this source.")
