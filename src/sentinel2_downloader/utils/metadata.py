def change_arr(memfiles, arr):
    """
    Change the array in the MemoryFile objects without changing the metadata.

    Args:
        memfiles (list): List of MemoryFile objects.
        arr (numpy.ndarray): The new array to set in the MemoryFile objects.

    Returns:
        list: List of MemoryFile objects with updated arrays.
    """
    for memfile in memfiles:
        with memfile.open() as src:
            src.write(arr)
    return memfiles