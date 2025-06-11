# Sentinel-2 Image Downloader

A Python tool to download, process, and save Sentinel-2 satellite images based on geographical coordinates, cloud cover, date range, and spectral bands. Supports multiple APIs including Microsoft Planetary Computer and Element84.


## Table of Contents

- [Features](#features)  
- [Installation](#installation)  
- [Usage](#usage)  

## Features

- Downloads Sentinel-2 images from the Microsoft Planetary Computer or Element84 APIs.
- Provides both full image and partial bounding box downloads using HTTP Range. Greatly reducing the size of the downloaded file.
- Saves images with metadata including date, cloud cover, and band information.
- CLI interface with multiple configuration options.


## Installation

### (Recommended) Using uv

Install the package as editable to be used in scripts.

```bash
cd sentinel2_downloader
uv pip install -e .
```

### Wihtout uv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

This package can both be used as script to be launched from the CLI or imported in other scripts.

### CLI usage

### (Recommended) Using uv

```bash
uv run sentinel_downloader.py latitude longitude --output_dir path/to/output
```

Alternatively, if you want to launch the script from another directory you can use the --project option using : 

```bash
uv run --project full/path/to/sentinel_downloader.py latitude longitude --output_dir path/to/output
```

### Wihtout uv

```bash
python sentinel_downloader.py latitude longitude --output_dir path/to/output
```

A few optional parameters exist:

- `--output_dir`: Path to save the downloaded images.
- `--cloud_cover`: Maximum cloud cover percentage (default: 10).
- `--date_range`: Start and end date in ISO format (default: 2024-01-01 2024-03-01).
- `--bands`: Sentinel-2 bands to download (default: B04 B03 B02).
- `--bbox_delta`: Bounding box size around the point in km (default: 3).
- `--api`: Choose between `microsoft` or `element84`. Microsoft api need a session token to use, one is generated automatically on the fly however it expires after 45 minutes. Use element84 for longer downloads.
- `--verbose`: Enable verbose logging.

