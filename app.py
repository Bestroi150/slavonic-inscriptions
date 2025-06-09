import streamlit as st
from pathlib import Path
from typing import Dict, Any
from collections import defaultdict
from io import BytesIO
from PIL import Image
import xml.etree.ElementTree as ET
import pandas as pd
import os
import base64
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
import json
import tempfile

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

# Add custom fonts (Cyrillic Bulgarian, Roboto, and OpenDyslexic)
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
    @font-face {
        font-family: 'OpenDyslexic';
        src: url('static/OpenDyslexic-Regular.otf') format('opentype');
        font-weight: normal;
        font-style: normal;
    }
    
    /* Default fonts */
    * {
        font-family: 'Roboto', sans-serif;
    }
    
    /* Church Slavonic specific elements - these will not be overridden by OpenDyslexic */
    .custom-font,
    .apparatus-text,
    .ocs-text {
        font-family: 'CyrillicaBulgarian10U', sans-serif !important;
    }
    
    /* Base dyslexic font class - will be added to body when toggle is active */
    .dyslexic-font {
        font-family: 'OpenDyslexic', sans-serif !important;
    }
    
    /* Elements to apply OpenDyslexic to when toggle is active */
    .dyslexic-font .stMarkdown:not(.custom-font):not(.ocs-text):not(.apparatus-text),
    .dyslexic-font .stText:not(.custom-font):not(.ocs-text):not(.apparatus-text),
    .dyslexic-font h1,
    .dyslexic-font h2,
    .dyslexic-font h3,
    .dyslexic-font h4,
    .dyslexic-font h5,
    .dyslexic-font h6,
    .dyslexic-font .element-container:not(.custom-font):not(.ocs-text):not(.apparatus-text),
    .dyslexic-font p:not(.custom-font):not(.ocs-text):not(.apparatus-text),
    .dyslexic-font span:not(.custom-font):not(.ocs-text):not(.apparatus-text),
    .dyslexic-font label,
    .dyslexic-font button,
    .dyslexic-font select,
    .dyslexic-font input {
        font-family: 'OpenDyslexic', sans-serif !important;
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

def load_authority_file_json(file_path: str) -> Dict[str, Any]:
    """Load and parse a JSON authority file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            result = {}
            
            # Extract person names and IDs from the JSON structure 
            if 'persons' in data and isinstance(data['persons'], dict):
                try:
                    persons_list = data['persons']['text']['body']['listPerson']['person']
                    if isinstance(persons_list, list):
                        for person in persons_list:
                            person_id = person.get('_xml:id', '')
                            persName_list = person.get('persName', [])
                            if isinstance(persName_list, list):
                                eng_name = next((name['__text'] for name in persName_list 
                                            if name.get('_xml:lang') == 'en' and '__text' in name), '')
                                bg_name = next((name['__text'] for name in persName_list
                                            if name.get('_xml:lang') == 'bg' and '__text' in name), '')
                                result[person_id] = {'en': eng_name, 'bg': bg_name}
                except (KeyError, TypeError) as e:
                    st.error(f"Error parsing persons data structure: {str(e)}")
                    
            # Handle materials.json and objects.json similar structure
            elif ('materials' in data and isinstance(data['materials'], dict)) or \
                 ('objects' in data and isinstance(data['objects'], dict)):
                try:
                    key = 'materials' if 'materials' in data else 'objects'
                    items_list = data[key]['text']['body']['list']['item']
                    if isinstance(items_list, list):
                        for item in items_list:
                            item_id = item.get('_xml:id', '')
                            term_list = item.get('term', [])
                            if isinstance(term_list, list):
                                eng_term = next((term['__text'] for term in term_list 
                                            if term.get('_xml:lang') == 'en' and '__text' in term), '')
                                bg_term = next((term['__text'] for term in term_list
                                            if term.get('_xml:lang') == 'bg' and '__text' in term), '')
                                result[item_id] = {'en': eng_term, 'bg': bg_term}
                except (KeyError, TypeError) as e:
                    st.error(f"Error parsing {key} data structure: {str(e)}")
                    
            return result
    except Exception as e:
        st.error(f"Error loading authority file {file_path}: {str(e)}")
        return {}

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
    try:
        if authority_type == 'persons':
            # Navigate the JSON structure for persons
            persons = authority_files['persons']['persons']['text']['body']['listPerson']['person']
            for person in persons:
                if person.get('_xml:id') == ref_id:
                    for name in person['persName']:
                        if name.get('_xml:lang') == 'en' and '__text' in name:
                            return name['__text']
        elif authority_type == 'materials':
            # Navigate the JSON structure for materials
            items = authority_files['materials']['materials']['text']['body']['list']['item']
            for item in items:
                if item.get('_xml:id') == ref_id:
                    # Handle both single term and list of terms
                    if isinstance(item['term'], list):
                        for term in item['term']:
                            if term.get('_xml:lang') == 'en' and '__text' in term:
                                return term['__text']
                    elif isinstance(item['term'], dict) and item['term'].get('_xml:lang') == 'en' and '__text' in item['term']:
                        return item['term']['__text']
        elif authority_type == 'objects':
            # Navigate the JSON structure for objects
            items = authority_files['objects']['objects']['text']['body']['list']['item']
            for item in items:
                if item.get('_xml:id') == ref_id:
                    # Handle both single term and list of terms
                    if isinstance(item['term'], list):
                        for term in item['term']:
                            if term.get('_xml:lang') == 'en' and '__text' in term:
                                return term['__text']
                    elif isinstance(item['term'], dict) and item['term'].get('_xml:lang') == 'en' and '__text' in item['term']:
                        return item['term']['__text']
        return ref_id  # Return the ID if name not found
    except (KeyError, TypeError) as e:
        print(f"Error getting {authority_type} name for {ref_id}: {str(e)}")
        return ref_id

# Load authority files from JSON
authority_files = {
    'materials': load_authority_file_json(str(DATA_DIR / 'authority/materials.json')),
    'objects': load_authority_file_json(str(DATA_DIR / 'authority/objects.json')),
    'persons': load_authority_file_json(str(DATA_DIR / 'authority/persons.json'))
}

# Load pre-coded XMLs
precoded_xmls = load_precoded_xmls(str(DATA_DIR / 'xmls'))

# Set default renderer for Plotly

# Create sidebar
with st.sidebar:
    # Add OpenDyslexic toggle at the top of the sidebar
    use_dyslexic = st.toggle("Use OpenDyslexic Font", help="Enable OpenDyslexic font for better readability")
    if use_dyslexic:
        st.markdown("""
        <style>
            .stApp {
                font-family: 'OpenDyslexic', sans-serif !important;
            }
            .stApp .stMarkdown:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp .stText:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp h1:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp h2:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp h3:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp h4:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp h5:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp h6:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp p:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp span:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp label:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp button:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp select:not(.custom-font):not(.ocs-text):not(.apparatus-text),
            .stApp input:not(.custom-font):not(.ocs-text):not(.apparatus-text) {
                font-family: 'OpenDyslexic', sans-serif !important;
            }
                h1, h2, h3, h4, h5, h6 {
                    font-family: 'OpenDyslexic', sans-serif !important;
                }
                .stButton button {
                    font-family: 'OpenDyslexic', sans-serif !important;
                }
                .stSelectbox select {
                    font-family: 'OpenDyslexic', sans-serif !important;
                }
                .stTextInput input {
                    font-family: 'OpenDyslexic', sans-serif !important;
                }
            </style>
            """,
            unsafe_allow_html=True
        )

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
    """)

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
                text += f'{ch}\u0323'

        # Original letters
        elif tag == 'orig':
            text += f'={child.text or ""}='

        # Supplied text
        elif tag == 'supplied':
            reason = child.attrib.get('reason')
            cert = child.attrib.get('cert')
            sup = child.text or ''
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

        # Gaps
        elif tag == 'gap':
            # Ellipsis
            if child.attrib.get('reason') == 'ellipsis':
                text += '...'
            else:
                unit = child.attrib.get('unit')
                qty = child.attrib.get('quantity') or ''
                extent = child.attrib.get('extent')
                precision = child.attrib.get('precision')

                if unit == 'character':
                    if extent == 'unknown':
                        text += '[.?]'
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
            text += child.text or ''

        # Symbols
        elif tag == 'g':
            type_ = child.attrib.get('type')
            if type_:
                text += f'*{type_}*'

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
    Extract and join text from each <bibl> element.
    """
    texts = []
    if div is None:
        return ""
    for bibl in div.findall(".//tei:bibl", NS):
        if bibl.text:
            texts.append(bibl.text.strip())
    return "\n".join(texts)

# Load authority files
authority_files = {
    'materials': load_authority_file_json(str(DATA_DIR / 'authority/materials.json')),
    'objects': load_authority_file_json(str(DATA_DIR / 'authority/objects.json')),
    'persons': load_authority_file_json(str(DATA_DIR / 'authority/persons.json'))
}

# Load pre-coded XMLs
precoded_xmls = load_precoded_xmls(str(DATA_DIR / 'xmls'))

st.title("TEI Monument Visualization (Plain Text Versions)")

st.markdown("""
This application displays scholarly records of ancient Greek inscriptions.
Upload one or more TEI XML files to view key sections and information.
For the apparatus, translation, commentary, and bibliography sections only the English text is extracted and displayed as plain text.
""")

# Create two columns for uploaders and pre-coded files
col1, col2 = st.columns(2)

with col1:
    use_precoded = st.checkbox("Use pre-coded XML files", value=True)
    uploaded_files = st.file_uploader(
        "Upload additional TEI XML files", 
        type=["xml"], 
        accept_multiple_files=True,
        key="xml_uploader"
    )

with col2:
    uploaded_images = st.file_uploader(
        "Upload additional images", 
        type=["jpg", "jpeg", "png"], 
        accept_multiple_files=True,
        key="image_uploader"
    )

# Combine pre-coded and uploaded files if needed
working_files = []
if use_precoded:
    working_files.extend(precoded_xmls)

if uploaded_files:
    for uploaded_file in uploaded_files:
        try:
            # Process the XML file directly from memory
            root, raw_xml = parse_tei(uploaded_file)
            if root is not None:
                working_files.append({
                    'name': uploaded_file.name,
                    'root': root,
                    'raw_xml': raw_xml
                })
        except Exception as e:
            st.error(f"Error processing file {uploaded_file.name}: {str(e)}")
            continue

# Create a dictionary to store image data
image_data = {}
if uploaded_images:
    for img in uploaded_images:
        try:
            # Process the image directly from memory
            image_bytes = BytesIO(img.getvalue())
            with Image.open(image_bytes) as pil_img:
                image_data[img.name] = {
                    'data': img,
                    'type': img.type
                }
        except Exception as e:
            st.warning(f"Could not process image {img.name}: {str(e)}")
            continue

# Continue with file processing only if we have files to work with
if working_files:
    # Create tabs for visualization, querying, analytics, and network analysis
    viz_tab, query_tab, analytics_tab, network_tab = st.tabs(["Data Visualization", "Search & Query", "Analytics", "Network Analysis"])
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
                editors = title_stmt.findall("tei:editor/tei:persName", NS) if title_stmt is not None else []
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
                
                if dimensions is not None:
                    height_elem = dimensions.find("tei:height", NS)
                    width_elem = dimensions.find("tei:width", NS)
                    depth_elem = dimensions.find("tei:depth", NS)
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
                
                # If dimensions not found in dimensions element, try layout
                if not any([height, width, depth]) and layout_desc is not None:
                    # Look for lenght/length (handle both spellings), width, height in layout
                    height_elem = layout_desc.find("tei:lenght|tei:length", NS)
                    width_elem = layout_desc.find("tei:width", NS)
                    depth_elem = layout_desc.find("tei:depth", NS)
                    
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
                st.markdown(f"- **Dimensions:** Height {height} cm, width {width} cm, depth {depth} cm")
                st.markdown(f"- **Letter size:** Height {letter_size} cm")
                st.markdown(f"- **Layout description:** {layout if layout else 'Not available'}")
                st.markdown("- **Decoration description:** (appears to be blank)")
                st.subheader("Dating and Location Information")
                st.markdown(f"- **Category of inscription:** {inscription_category}")

                # Original Text Section with Old Church Slavonic Font
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
                        for section, content in result['matches']:
                            st.markdown(f"**Found in {section}:**")
                            st.text(content)
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
   
    with network_tab:
        st.header("Network Analysis")         
       
        
        # Add network type selection
        network_type = st.selectbox(
            "Select Network Analysis Type",
            ["Find Spot Connections", "Material Connections", "Object Type Connections", 
             "Person Connections", "Temporal Connections"]
        )
        
        if all_data:
            # Load authority files from JSON
            authority_files = load_authority_files()
            
            # Convert data to DataFrame if not already done
            df = pd.DataFrame(all_data)
            
            # Create a graph with references to authority files
            G = nx.Graph()
            
            # Create color mapping for different node types
            color_map = {
                'monument': '#1f77b4',  # blue for monuments
                'material': '#2ca02c',  # green for materials
                'object': '#ff7f0e',    # orange for objects
                'person': '#d62728'     # red for persons
            }
            
            # Process each monument based on the selected network type
            for _, monument in df.iterrows():
                mon_id = monument['ID']
                # Add monument node
                G.add_node(mon_id, 
                          type='monument',
                          title=monument['Title'],
                          color=color_map['monument'],
                          node_type='monument')
                
                # Get original file data to access references
                file_data = next((f for f in parsed_files if get_text(f['root'].find("tei:teiHeader/tei:fileDesc/tei:publicationStmt", NS), "tei:idno[@type='filename']") == mon_id), None)
                
                if file_data:
                    root = file_data['root']
                    
                    if network_type == "Material Connections":
                        # Process materials
                        for material_elem in root.findall(".//tei:material", NS):
                            material_name = None
                            ref = material_elem.get('ref', '')
                            if ref:
                                ref_id = ref.replace('materials.xml#', '')
                                material_name = get_authority_name(ref_id, 'materials', authority_files)
                            
                            if material_name:
                                if not G.has_node(material_name):
                                    G.add_node(material_name, type='material', color=color_map['material'], node_type='material')
                                G.add_edge(mon_id, material_name, type='material')
                    
                    elif network_type == "Object Type Connections":
                        # Process objects
                        for object_elem in root.findall(".//tei:objectType", NS):
                            object_name = None
                            ref = object_elem.get('ref', '')
                            if ref:
                                ref_id = ref.replace('objects.xml#', '')
                                object_name = get_authority_name(ref_id, 'objects', authority_files)
                            
                            if object_name:
                                if not G.has_node(object_name):
                                    G.add_node(object_name, type='object', color=color_map['object'], node_type='object')
                                G.add_edge(mon_id, object_name, type='object')
                    
                    elif network_type == "Person Connections":
                        # Process persons
                        for person_elem in root.findall(".//tei:persName", NS):
                            person_name = None
                            ref = person_elem.get('ref', '')
                            if ref and 'persons.xml#' in ref:
                                ref_id = ref.replace('persons.xml#', '')
                                person_name = get_authority_name(ref_id, 'persons', authority_files)
                            
                            if person_name:
                                if not G.has_node(person_name):
                                    G.add_node(person_name, type='person', color=color_map['person'], node_type='person')
                                G.add_edge(mon_id, person_name, type='person')
                    elif network_type == "Find Spot Connections":
                            # Process find spots - only use English place names
                        for place_elem in root.findall(".//tei:seg[@xml:lang='en']/tei:placeName", NS):
                            place_name = place_elem.text
                            if place_name:
                                place_name = place_name.strip()
                                if not G.has_node(place_name):
                                    G.add_node(place_name, type='place', color='#9467bd', node_type='place')
                                G.add_edge(mon_id, place_name, type='place')
                    
                    elif network_type == "Temporal Connections":
                        # Process dates
                        for date_elem in root.findall(".//tei:origDate", NS):
                            century = None
                            for seg in date_elem.findall("tei:seg[@xml:lang='en']", NS):
                                if seg.text and "c." in seg.text:
                                    century = seg.text.strip()
                                    break
                        
                            if not century:
                                not_before = date_elem.get('notBefore', '')
                                not_after = date_elem.get('notAfter', '')
                                if not_before and not_after:
                                    century = f"{not_before[:2]}th c."
                        
                            if century:
                                if not G.has_node(century):
                                    G.add_node(century, type='period', color='#8c564b', node_type='period')
                                G.add_edge(mon_id, century, type='period')
            
            # Create the network visualization using plotly
            if nx.number_of_nodes(G) > 0:
                # Calculate layout
                pos = nx.spring_layout(G, k=0.3, iterations=50)
                
                # Create edges trace
                edge_x = []
                edge_y = []
                for edge in G.edges():
                    x0, y0 = pos[edge[0]]
                    x1, y1 = pos[edge[1]]
                    edge_x.extend([x0, x1, None])
                    edge_y.extend([y0, y1, None])
                
                edges_trace = go.Scatter(
                    x=edge_x, y=edge_y,
                    line=dict(width=0.5, color='#888'),
                    hoverinfo='none',
                    mode='lines')
                
                # Create nodes trace for each node type
                node_traces = []
                node_types = set(nx.get_node_attributes(G, 'type').values())
                
                for node_type in node_types:
                    nodes = [n for n, attr in G.nodes(data=True) if attr.get('type') == node_type]
                    if nodes:
                        x = [pos[node][0] for node in nodes]
                        y = [pos[node][1] for node in nodes]
                        
                        # Get the color for this node type
                        if node_type in color_map:
                            node_color = color_map[node_type]
                        elif node_type == 'place':
                            node_color = '#9467bd'  # purple for places
                        elif node_type == 'period':
                            node_color = '#8c564b'  # brown for periods
                        else:
                            node_color = '#e377c2'  # pink for others
                        
                        node_trace = go.Scatter(
                            x=x, y=y,
                            mode='markers+text',
                            hoverinfo='text',
                            marker=dict(
                                size=15,
                                color=node_color,
                                line=dict(width=1, color='#000')
                            ),
                            text=[node for node in nodes],
                            textposition="bottom center",
                            name=node_type.capitalize(),
                            textfont=dict(
                                size=10,
                            )
                        )
                        node_traces.append(node_trace)
            
            # Create the figure
            fig = go.Figure(data=[edges_trace] + node_traces,
                          layout=go.Layout(
                              showlegend=True,
                              hovermode='closest',
                              margin=dict(b=0, l=0, r=0, t=0),
                              xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                              yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                              legend=dict(
                                  yanchor="top",
                                  y=0.99,
                                  xanchor="left",
                                  x=0.01,
                                  bgcolor="rgba(255, 255, 255, 0.5)"
                              ),
                              height=700
                          ))
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Display statistics
            st.subheader("Network Statistics")
            st.markdown(f"- **Total nodes:** {G.number_of_nodes()}")
            st.markdown(f"- **Total connections:** {G.number_of_edges()}")
            st.markdown("- **Node types:**")
            for node_type in sorted(node_types):
                count = len([n for n, attr in G.nodes(data=True) if attr.get('type') == node_type])
                st.markdown(f"  - {node_type.capitalize()}: {count}")
            
            # Add degree centrality analysis
            if G.number_of_nodes() > 1:
                st.subheader("Centrality Analysis")
                
                central_nodes = sorted(nx.degree_centrality(G).items(), key=lambda x: x[1], reverse=True)[:5]
                
                st.markdown("**Most connected nodes:**")
                for node, score in central_nodes:
                    node_type = G.nodes[node].get('type', 'unknown')
                    st.markdown(f"- {node} ({node_type}): {score:.4f} centrality score")
        else:
            st.info(f"No {network_type.lower()} found between monuments and authority files.")
