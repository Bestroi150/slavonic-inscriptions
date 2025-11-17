# Slavonic Inscriptions

A web application for exploring and analyzing Slavonic inscriptions, encoded in TEI XML  with network visualization and mapping capabilities.

## Features

- **Network View**: Visualize relationships between inscriptions, people, places, and other entities
- **Map View**: Geographic visualization of inscription findspots and locations
- **Bibliography**: Comprehensive bibliographic information for inscriptions
- **Authority Data**: Structured authority files for consistent data references

## Project Structure

```
├── app.py                 # Main application entry point
├── bibliography.py        # Bibliography handling
├── map_view.py           # Map visualization module
├── requirements.txt      # Python dependencies
├── data/                 # Data files
│   ├── bibliography.xml  # Bibliography source data
│   ├── authority/        # Authority files (JSON)
│   └── xmls/            # XML inscription data
├── images/              # Image assets
├── pages/               # Application pages
│   └── 02_Network_View.py
└── static/              # Static files
    └── imgs/            # Images for web interface
```

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the application:
```bash
python app.py
```

## Data Files

- **Authority**: JSON files containing controlled vocabularies for materials, people, places, etc.
- **Inscriptions**: XML files containing inscription data and metadata
- **Bibliography**: Bibliography references and citations

## License
This project is licensed under the [Creative Commons Attribution 4.0 International (CC BY 4.0) License](https://github.com/Bestroi150/slavonic-inscriptions/blob/main/LICENSE). See LICENSE file for details.
