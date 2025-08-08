from pystac_client import Client
import planetary_computer

def get_client_from_api(api='microsoft'):
    """
    Get the client object for the specified API.

    Args:
        api (str): The API to use ('microsoft' or 'element84').

    Returns:
        Client: The client object for the specified API.
    """
    if api == 'microsoft':
        API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
        return Client.open(API_URL, modifier=planetary_computer.sign_inplace)
    elif api == 'element84':
        API_URL = "https://earth-search.aws.element84.com/v1"
        return Client.open(API_URL)
    else:
        raise ValueError("Unsupported API. Use 'microsoft' or 'element84'.")