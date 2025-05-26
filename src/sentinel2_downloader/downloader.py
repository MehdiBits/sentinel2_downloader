import requests
from tqdm import tqdm
from shapely.geometry import box
from pystac_client import Client
import numpy as np
import planetary_computer
import io
import rasterio
from rasterio.io import MemoryFile
from dateutil.parser import isoparse

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


def get_sentinel2_image(lat, lon, cloud_cover=10, date_range=("2024-01-01", "2024-03-01"), bbox_delta=0.009, verbose=False, api='microsoft'):
    
    if api == 'microsoft':
        API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
        client = Client.open(API_URL, modifier=planetary_computer.sign_inplace)
    elif api == 'element84':
        API_URL = "https://earth-search.aws.element84.com/v1"
        client = Client.open(API_URL)
    collection = "sentinel-2-l2a"


    # Define a (roughly) 2km x 2km bounding box around the given coordinates
    bbox = box(lon - bbox_delta, lat - bbox_delta, lon + bbox_delta, lat + bbox_delta)
    
    # Search for images containing the bouding box using the STAC API
    search = client.search(
        collections=[collection],
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
    rgb_list = []

    for item in items:
        assets = item.assets
        
        # Get RGB bands download links (blue, green, red)
        if api == 'microsoft': # Microsoft api is usually faster than element84
            blue_href = assets["B02"].href
            green_href = assets["B03"].href
            red_href = assets["B04"].href
        elif api == 'element84':
            blue_href = assets["blue"].href
            green_href = assets["green"].href
            red_href = assets["red"].href

        # Estimate file sizes before downloading
        if verbose:
            estimated_sizes = {}
            for color, href in zip(["blue", "green", "red"], [blue_href, green_href, red_href]):
                response = requests.head(href)
                size = int(response.headers.get("Content-Length", 0)) / (1024 * 1024)
                estimated_sizes[color] = size
            
            total_size = sum(estimated_sizes.values())
            print(f"Estimated download size: {total_size:.2f} MB (Blue: {estimated_sizes['blue']:.2f} MB, Green: {estimated_sizes['green']:.2f} MB, Red: {estimated_sizes['red']:.2f} MB)")

        b, meta_b, transform, crs = download(blue_href, verbose=verbose)
        g, _, _, _ = download(green_href, verbose=verbose)
        r, _, _, _ = download(red_href, verbose=verbose)

        
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
            try:
                date = isoparse(item.properties["datetime"])
                dst.update_tags(
                    Title="Sentinel-2 RGB Composite",
                    CloudCover=item.properties["eo:cloud_cover"],
                    Date=item.properties["datetime"],
                    Suffix=f'_{date.year}_{date.month:02d}_{date.day:02d}',
                    Platform=item.properties.get("platform", "Sentinel-2")
                )
            except Exception as e:
                print(f"Error parsing date for item {item.id}: {e}")
                dst.update_tags(
                    Title="Sentinel-2 RGB Composite",
                    CloudCover=item.properties["eo:cloud_cover"],
                    Date=item.properties["datetime"],
                    Platform=item.properties.get("platform", "Sentinel-2")
                )
        memfile_list.append(memfile)
        rgb_list.append(rgb)
    
    # Return BytesIO object
    return rgb_list, memfile_list

def save_image(memfile, path):
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
        else:
            with rasterio.open(path, 'w', **src.meta) as dst:
                dst.write(src.read())
                dst.update_tags(**src.tags())

if __name__ == "__main__":
    latitude, longitude = 51.482694952724614, 46.20856383098548
    cloud_cover = 30
    date_range = ("2024-01-01", "2024-01-13")

    rgb, memfile = get_sentinel2_image(latitude, longitude, cloud_cover, date_range, verbose=True)