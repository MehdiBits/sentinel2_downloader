from rasterio.io import MemoryFile
import rasterio
import numpy as np

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