from rasterio.io import MemoryFile
import rasterio
import numpy as np
from sentinel2_downloader.utils.geometry import delta_km_to_deg
from shapely.geometry import box
from sentinel2_downloader.utils.api import get_client_from_api

def change_arr(memfiles, arr_list):
    """
    Change the array in the MemoryFile objects without changing the metadata.

    Args:
        memfiles (list): List of MemoryFile objects.
        arr (numpy.ndarray): The new array to set in the MemoryFile objects.

    Returns:
        list: List of MemoryFile objects with updated arrays.
    """

    new_memfiles = []
    if isinstance(memfiles[0], list):
        # If memfiles is a list of lists, flatten it
        memfiles = [item for sublist in memfiles for item in sublist]
    for memfile, arr in zip(memfiles, arr_list):
        with memfile.open() as src:
            meta = src.meta.copy()
            trs = src.transform
            meta.update({
                'height': arr.shape[0],
                'width': arr.shape[1],
                'transform': rasterio.Affine(trs.a /2, trs.b, trs.c,
                                            trs.d, trs.e / 2, trs.f),
            })

        new_memfile = MemoryFile()
        with new_memfile.open(**meta) as dst:
            dst.write(arr[np.newaxis, ...])

        new_memfiles.append(new_memfile)

    return new_memfiles

def get_available_dates(lat, lon, cloud_cover, date_range, delta, api='microsoft'):
    """
    Get the available dates for sentinel-2 images for a specific location, time range, and api.
    
    Args:
        cloud_cover (float): Maximum cloud cover percentage.
        date_range (tuple): Start and end dates for the search.
        verbose (bool): If True, print additional information.
        delta (float): Delta in kilometers to define the bounding box around the location.
        client: Client object to interact with the API.

    Returns:
        list: List of available dates for sentinel-2 images.
        If no images are found, returns None.
    """

    client = get_client_from_api(api)

    bbox_delta = (delta, delta)
    bbox_delta = delta_km_to_deg(lat, bbox_delta[0], bbox_delta[1])
    bbox = (lon - bbox_delta[0], lat - bbox_delta[1], lon + bbox_delta[0], lat + bbox_delta[1])
    bbox = box(*bbox)



    search = client.search(
        collections=["sentinel-2-l2a"],
        intersects=bbox,
        query={"eo:cloud_cover": {"lt": cloud_cover}},
        datetime=f"{date_range[0]}/{date_range[1]}"
    )

    items = search.item_collection()
    if not items or len(items) == 0:
        return None
    
    return [item.properties['datetime'] for item in items]


