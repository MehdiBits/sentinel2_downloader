import requests
import os
import io

from tqdm import tqdm
from shapely.geometry import box
from shapely import Polygon
from pystac_client import Client
import numpy as np
import planetary_computer

import rasterio
from rasterio.io import MemoryFile
from dateutil.parser import isoparse
from rio_tiler.io import Reader
import argparse

from sentinel2_downloader.utils.geometry import delta_km_to_deg

def download(url, verbose=False):
    """
    Downloads data from a given URL and returns it as a NumPy array.
    Args:
        url (str): The URL to download the data from.
        verbose (bool, optional): If True, displays a progress bar during the download. Defaults to False.
    Returns:
        list: A list containing the downloaded images as a list of NumPy arrays.
        list: A list of MemoryFile objects containing the downloaded images.
    Raises:
        Exception: If the date of the image cannot be parsed to be included in the image suffix tag.
    """
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get("content-length", 0))
    block_size = 1024 * 1024  # 1 MB
    buffer = io.BytesIO()

    if verbose:
        t = tqdm(total=total_size, unit='B', unit_scale=True)
        for data in response.iter_content(block_size):
            buffer.write(data)
            t.update(len(data))
        t.close()
    else:
        for data in response.iter_content(block_size):
            buffer.write(data)

    buffer.seek(0)
    
    with rasterio.open(buffer) as src:

        band = src.read(1)
        meta = src.meta.copy()
        transform = src.transform
        crs = src.crs

    return band, meta, transform, crs

def download_bbox(url, bounds, max_size=512):
    """
    Downloads only the spatial bounding box from a COG using HTTP Range requests.

    Args:
        url (str): URL to the COG file (e.g., Sentinel-2 band URL).
        bounds (tuple): (minx, miny, maxx, maxy) in image CRS (usually EPSG:4326 for STAC assets).
        max_size (int): Maximum pixel size for output image (preserves aspect ratio).

    Returns:
        tuple: (band_data, meta, transform, crs)
    """
    with Reader(url) as cog:
        # WGS84 bounds (required by Planetary Computer for some reasons)
        img = cog.part(bounds, max_size=max_size, dst_crs=cog.crs, bounds_crs="EPSG:4326")
        band = img.data[0]

        meta = cog.dataset.meta.copy()
        meta.update({
            "height": band.shape[0],
            "width": band.shape[1],
            "transform": img.transform,
            "count": 1
        })
        return band, meta, meta["transform"], cog.crs

def get_sentinel2_image(lat, lon, cloud_cover=10, date_range=("2024-01-01", "2024-03-01"), bbox_delta=2, verbose=False, api='microsoft', bbox=None, bands=['B04', 'B03', 'B02'], full=False):
    """
    Downloads Sentinel-2 images for a given latitude and longitude, with options for cloud cover, date range, and bounding box size.
    
    Args:
        lat (float): Latitude of the center point.
        lon (float): Longitude of the center point.
        cloud_cover (int): Maximum cloud cover percentage for image selection.
        date_range (tuple): Start and end dates for image selection in ISO format (YYYY-MM-DD).
        bbox_delta (float): Delta in degrees for the bounding box around the center point.
        verbose (bool): If True, prints additional information during the download process.
        api (str): API to use for downloading Sentinel-2 images ('microsoft' or 'element84').
        bbox (tuple or None): Custom bounding box as a tuple of (minx, miny, maxx, maxy) in degrees. If None, a default bounding box is created.
        bands (list): List of bands to download. Default is ['B04', 'B03', 'B02'].

    Returns:
        tuple: A list of downloaded images as NumPy arrays and a list of MemoryFile objects containing the downloaded images.
    """

    # api logic
    file_suffix = bands # To use as output file suffixes, need to get the band names before potential changes

    

    if api == 'microsoft':
        API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
        client = Client.open(API_URL, modifier=planetary_computer.sign_inplace)
    elif api == 'element84':
        API_URL = "https://earth-search.aws.element84.com/v1"
        client = Client.open(API_URL)
        # Element84 uses different band names, so we need to map them
        # to the standard Sentinel-2 band names for consistency
        band_names = {
            "B04": "red",
            "B03": "green",
            "B02": "blue",
            "B01": "coastal",
            "B05": "rededge1",
            "B06": "rededge2",
            "B07": "rededge3",
            "B08": "nir",
            "B8A": "nir08",
            "B09": "nir09",
            "B10": "cirrus",
            "B11": "swir16",
            "B12": "swir22"
        }
        bands = [band_names[band] for band in bands]

    # bbox logic
    if bbox is None:
        if isinstance(bbox_delta, (int, float)):
            # bbox delta can be given either as a tuple or a single float value, if single float value is given, it will be used for both latitude and longitude
            bbox_delta = (bbox_delta, bbox_delta)

        # If bbox is not provided, create a bounding box around the given latitude and longitude then create a Polygon from it
        bbox_delta = delta_km_to_deg(lat, bbox_delta[0], bbox_delta[1])
        bbox = (lon - bbox_delta[0], lat - bbox_delta[1], lon + bbox_delta[0], lat + bbox_delta[1])
        bbox = box(*bbox)
    else:
    # If bbox is provided, ensure it is a Polygon
        if not isinstance(bbox, Polygon):
            bbox = box(*bbox)
    
    arr_list, memfiles = _get_sentinel2_image(cloud_cover, date_range, verbose, bbox, bands, client=client, file_suffix=file_suffix, full=full)

    return arr_list, memfiles

def _get_sentinel2_image(cloud_cover, date_range, verbose, bbox, bands, client, file_suffix, full):
    
    # Search for images containing the bouding box using the STAC API
    search = client.search(
        collections=["sentinel-2-l2a"],
        intersects=bbox,
        query={"eo:cloud_cover": {"lt": cloud_cover}},
        datetime=f"{date_range[0]}/{date_range[1]}"
    )

    items = search.item_collection()
    if not items or len(items) == 0:
        print("No suitable images found.")
        return None, None
    
    if verbose:
        print(f"Found {len(items)} images matching the criteria.")
        for item in items:
            print(f"Image ID: {item.id}, Cloud Cover: {item.properties['eo:cloud_cover']}%, Date: {item.properties['datetime']}")

    memfile_list = []
    arr_list = []

    
    for item in tqdm(items, desc="Processing Items", leave=False, disable=not verbose):
        assets = item.assets
        bands_data = []

        for band in bands:
            link = assets[band].href
            if link is None:
                print(f"Band {band} not found in item {item.id}. Skipping this item.")
                break
            else:
                if full:
                # Download the full image
                    b, meta_b, transform, crs = download(link, verbose=verbose)
                else:
                # Download only the bounding box
                    b, meta_b, transform, crs = download_bbox(link, bbox.bounds)
                bands_data.append([b, meta_b, transform, crs])
                

        if bands == ['B04', 'B03', 'B02'] or bands == ['red', 'green', 'blue']:
            r = bands_data[0][0]  # Red band
            g = bands_data[1][0]  # Green band
            b = bands_data[2][0]  # Blue band
            rgb = np.stack([r, g, b], axis=0)

            meta_b.update({
                "count": 3,
                "dtype": rgb.dtype,
                "driver": "GTiff",
                "transform": transform,
                "crs": crs
            })

            memfile = MemoryFile()
            with memfile.open(**meta_b) as dst:
                dst.write(rgb[0], 1)
                dst.write(rgb[1], 2)
                dst.write(rgb[2], 3)

                date = isoparse(item.properties["datetime"])
                dst.update_tags(
                    Title="Sentinel-2 RGB Composite",
                    CloudCover=item.properties["eo:cloud_cover"],
                    Date=item.properties["datetime"],
                    Suffix=f'_{date.year}_{date.month:02d}_{date.day:02d}_RGB',
                    Platform=item.properties.get("platform", "Sentinel-2")
                )
            memfile_list.append(memfile)
            arr_list.append(rgb)

        else:
            for data, band_name in zip(bands_data, file_suffix):
                b = data[0]
                meta_b = data[1]
                transform = data[2]
                crs = data[3]

                memfile = MemoryFile()
                with memfile.open(**meta_b) as dst:
                    dst.write(b, 1)

                    date = isoparse(item.properties["datetime"])
                    dst.update_tags(
                        Title=f"Sentinel-2 {band_name} Band",
                        CloudCover=item.properties["eo:cloud_cover"],
                        Date=item.properties["datetime"],
                        Suffix=f'_{date.year}_{date.month:02d}_{date.day:02d}_{band_name}',
                        Platform=item.properties.get("platform", "Sentinel-2")
                    )
                memfile_list.append(memfile)
                arr_list.append(b)

    return arr_list, memfile_list


def save_image(memfile, path, verbose=False):
    """
    Save the image from the MemoryFile to a specified path.
    Args:
        memfile (MemoryFile): The MemoryFile containing the image data.
        path (str): The path where the image will be saved.
    """
    with memfile.open() as src:
        if src.tags().get('Suffix'):
            with rasterio.open(path[:-4] + src.tags().get('Suffix') + '.tif', 'w', **src.meta) as dst:
                
                dst.write(src.read())
                dst.update_tags(**src.tags())
            if verbose:
                print(f"Image saved to {path[:-4] + src.tags().get('Suffix') + '.tif'}")
        else:
            with rasterio.open(path, 'w', **src.meta) as dst:
                dst.write(src.read())
                dst.update_tags(**src.tags())
                if verbose:
                    print(f"Image saved to {path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Sentinel-2 Image Downloader and Processor")
    parser.add_argument('latitude', type=float, help="Latitude of the center point for image download")
    parser.add_argument('longitude', type=float, help="Longitude of the center point for image download")
    parser.add_argument('--output_dir', type=str, default=None, help="Directory path for saving output results")
    parser.add_argument('--cloud_cover', type=int, default=10, help="Maximum cloud cover percentage for image selection")
    parser.add_argument('--bands', nargs='+', default=['B04', 'B03', 'B02'], help="Bands to download. Names are given using the B notation. (default: ['B04', 'B03', 'B02'])")
    parser.add_argument('--date_range', type=str, nargs=2, default=("2024-01-01", "2024-03-01"), help="Date range for image selection (start, end)")
    parser.add_argument('--bbox_delta', type=float, default=[3, 3], help="Delta in km for bounding box around the center point")
    parser.add_argument('--verbose', action='store_true', help="Enable verbose output during download", default=False)
    parser.add_argument('--api', type=str, choices=['microsoft', 'element84'], default='microsoft', help="API to use for downloading Sentinel-2 images (default: microsoft)")
    parser.add_argument('--full', action='store_true', help="Download full images instead of just the bounding box")
    return parser.parse_args()

if __name__ == "__main__":
    # Parsing of the command line arguments
    args = parse_args()
    latitude = args.latitude
    longitude = args.longitude
    cloud_cover = args.cloud_cover
    date_range = args.date_range
    bbox_delta = args.bbox_delta
    verbose = args.verbose
    api = args.api
    output_dir = args.output_dir
    bands = args.bands
    full = args.full

    bbox_delta = delta_km_to_deg(latitude, bbox_delta[0], bbox_delta[1])
    bbox = (longitude - bbox_delta[0], latitude - bbox_delta[1], longitude + bbox_delta[0], latitude + bbox_delta[1])
    _, memfile = get_sentinel2_image(latitude, longitude, cloud_cover, date_range, verbose=verbose, bbox=bbox, bands=bands, api=api, full=full)

    if output_dir and memfile is not None:
        output_dir = output_dir.replace(' ', '_')
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        for i, mem in enumerate(memfile):
            image_path = os.path.join(output_dir, f"sentinel2_image_{i}.tif")
            save_image(mem, image_path)
            print(f"Image saved to {image_path}")
