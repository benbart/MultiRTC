from pathlib import Path
import numpy as np
from sarpy.io.complex.converter import conversion_utility
from sarpy.utils.chip_sicd import create_chip
from sarpy.geometry import point_projection
from sarpy.io.complex.sicd import SICDReader


def getrowcol(sicdfile, bbox):
    """
    sicdffile: sicd file
    bbox: [lonmin,latmin,lonmax,latmax]

    Returns
    rowcolbox: (rowmin,rowmax, colmin, colmax)

    """
    # Open the SICD file
    reader = SICDReader(sicdfile)

    # Get the SICD metadata structure
    sicd_structure = reader.sicd_meta

    # Define your Lon/Lat/HAE coordinates
    # This should be a numpy array of shape (N, 3), where N is the number of points
    # and the last dimension is [longitude, latitude, hae]
    # Example: a single point at (lon, lat, hae)

    hae = sicd_structure.GeoData.SCP.LLH.HAE

    upperl = np.array([bbox[0], bbox[3], hae])
    upperr = np.array([bbox[2], bbox[3], hae])
    lowerr = np.array([bbox[2], bbox[1], hae])
    lowerl = np.array([bbox[0], bbox[1], hae])
    lon_lat_hae_coords = np.vstack((upperl, upperr, lowerr, lowerl))

    # lon_lat_hae_coords = np.array([[-105.2705, 40.0150, 1625.0]])  # Example coordinates
    # sicd_structure.GeoData.SCP is the center point of the image in scene coordinates
    # lon_lat_hae_coords = np.array([[sicd_structure.GeoData.SCP.LLH.Lon, sicd_structure.GeoData.SCP.LLH.Lat, sicd_structure.GeoData.SCP.LLH.HAE]])
    # Perform the conversion
    # The 'ordering' parameter specifies the order of the input coordinates.
    # 'longlat' means [longitude, latitude, hae].
    # Otherwise, it defaults to [latitude, longitude, hae].
    image_coords = point_projection.ground_to_image_geo(lon_lat_hae_coords, sicd_structure, ordering='longlat')

    # image_coords will be a numpy array of shape (N, 2),
    # with the final dimension representing [row, column]

    # Accessing individual row and column
    row0 = int(image_coords[0][:, 0].min())
    row1 = int(image_coords[0][:, 0].max())
    col0 = int(image_coords[0][:, 1].min())
    col1 = int(image_coords[0][:, 1].max())

    rowcolbox = (row0, row1, col0, col1)

    reader.close()

    return rowcolbox


def clip_sicd_file(sicdfile: str, rowcolbox: tuple, outfile: str):
    """ subset the sicd file based on the rowcolbox (min_row, max_row, min_col, max_col)
    Parameters
    ---------
    sicdfile: sicd file
    rowcolbox: (rowmin, rowmax, colmin,colmac)
    outfile : subsetted sicd file

    Returns
    ---------
    """
    if Path(outfile).exists() and Path(outfile).is_file():
        Path(outfile).unlink()

    output_directory = Path(outfile).parent
    output_filename = Path(outfile).name

    try:
        # Use the create_chip utility to extract and save the subset
        create_chip(
            str(sicdfile),
            str(output_directory),
            str(output_filename),
            row_limits =(rowcolbox[0], rowcolbox[1]),
            col_limits = (rowcolbox[2], rowcolbox[3]),
        )
        print(f"Successfully created subset file: {outfile}")

    except Exception as e:
        print(f"An error occurred: {e}")

def subset_sicdfile(sicdfile: str, bbox: list, outfile: str):

    rowcolbox = getrowcol(sicdfile, bbox)

    clip_sicd_file(sicdfile, rowcolbox, outfile)
