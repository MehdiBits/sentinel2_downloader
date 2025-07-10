from sentinel2_superres import upscale
import numpy as np


def upscale_images(input_arr):
    input_arr = [np.array(arr) for arr in input_arr]
    monodate = len(input_arr) == 1
    results = upscale.upscale(input_arr, monodate=monodate)
    return results