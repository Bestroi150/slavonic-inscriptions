"""
Helper functions for the map view in the main application.
"""
import xml.etree.ElementTree as ET
import streamlit as st
import folium
import pydeck as pdk
import pandas as pd
import os

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

def extract_referenced_places(json_data, source_name, xml_refs, document_title=None):
    """
    Extracts places from a JSON object that are referenced in the XML.
    Returns a list of dictionaries for map plotting and a list for textual display.
    
    Args:
        json_data: The JSON data containing place information
        source_name: The type of source (Origin, Findspot, etc.)
        xml_refs: Set of references found in the XML
        document_title: Title of the document this place is referenced in
    """
    map_points = []
    text_points = []
    
    try:
        places_list = json_data.get(next(iter(json_data)))['body']['listPlace']['place']
    except (KeyError, TypeError, StopIteration):
        st.warning(f"Could not find a list of places in '{source_name}.json'")
        return [], []

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
            
            # Add to the textual list with document information
            text_point = {
                'name': english_name, 
                'id': place_id,
                'xml_source': document_title if document_title else None
            }
            text_points.append(text_point)
            
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
                        'document': document_title if document_title else 'Unknown'
                    })
                except (ValueError, TypeError):
                    continue  # Ignore if geo format is incorrect
                    
    return map_points, text_points

def create_leaflet_map(df):
    """Creates a 2D map with Leaflet using consistent styling with the 3D map."""
    if df.empty:
        return None

    # Calculate the center of the map
    center_lat = df['lat'].mean()
    center_lon = df['lon'].mean()
    
    # Create the base map
    m = folium.Map(location=[center_lat, center_lon], zoom_start=4)
    
    # Define colors for different sources
    source_colors = {
        'Origin': '#1f77b4',    # blue
        'Findspot': '#2ca02c',  # green
        'Current': '#ff7f0e',   # orange
        'General': '#d62728'    # red
    }
    
    # Add markers for each point
    for _, row in df.iterrows():
        color = source_colors.get(row['source'], '#7f7f7f')  # grey as default
        popup_html = f"""
            <b>{row['name']}</b><br>
            Source: {row['source']}<br>
            Document: {row['document']}
        """
        
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=8,
            popup=folium.Popup(popup_html, max_width=300),
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7
        ).add_to(m)
    
    return m

def create_pydeck_map(df):
    """Creates a 3D map with PyDeck using consistent styling with the 2D map."""
    if df.empty:
        return None

    # Get Mapbox token from environment variable (GitHub secret)
    mapbox_token = os.environ.get('MAP_BOX_TOKEN', '')
    
    # Define colors for different sources (using RGB values for PyDeck)
    source_colors = {
        'Origin': [31, 119, 180],    # blue
        'Findspot': [44, 160, 44],   # green
        'Current': [255, 127, 14],   # orange
        'General': [214, 39, 40]     # red
    }
    
    # Add color values to the dataframe
    df['color'] = df['source'].map(lambda x: source_colors.get(x, [127, 127, 127]))
    
    # Create the layer
    layer = pdk.Layer(
        "ScatterplotLayer",
        df,
        pickable=True,
        opacity=0.8,
        stroked=True,
        filled=True,
        radius_scale=6,
        radius_min_pixels=5,
        radius_max_pixels=15,
        line_width_min_pixels=1,
        get_position=["lon", "lat"],
        get_fill_color="color",
        get_line_color=[0, 0, 0],
    )
    
    # Set the initial view
    view_state = pdk.ViewState(
        latitude=df['lat'].mean(),
        longitude=df['lon'].mean(),
        zoom=4,
        pitch=50,
    )
    
    tooltip = {
        "html": "<b>{name}</b><br/>"
                "Source: {source}<br/>"
                "Document: {document}",
        "style": {
            "backgroundColor": "white",
            "color": "black"
        }
    }
    
    # Create the map with Mapbox as the base map if token is available
    if mapbox_token:
        return pdk.Deck(
            map_style='mapbox://styles/mapbox/light-v10',
            mapbox_api_key=mapbox_token,
            layers=[layer],
            initial_view_state=view_state,
            tooltip=tooltip
        )
    else:
        # Fallback to default base map if no token is available
        return pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip=tooltip
        )
