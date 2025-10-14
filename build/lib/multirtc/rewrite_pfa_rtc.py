import os
from osgeo import gdal
import numpy as np

def rewrite_pfa_rtc(infile):
    ''' set nodata = np.nan in the infile

    Args:
        infile: rtc geotif file

    Returns:

    '''

    ds = gdal.Open(infile, gdal.GA_Update)
    band = ds.GetRasterBand(1)
    data = band.ReadAsArray()
    [rows, cols] = data.shape
    datatype = band.DataType

    # driver = gdal.GetDriverByName("GTiff")
    # outdata = driver.Create(outFileName, cols, rows, 1, datatype)
    # outdata.SetGeoTransform(ds.GetGeoTransform())##sets same geotransform as input
    # outdata.SetProjection(ds.GetProjection())##sets same projection as input
    # outdata.GetRasterBand(1).WriteArray(data)
    # outdata.GetRasterBand(1).SetNoDataValue(np.float32(nan))##if you want these values transparent
    band.SetNoDataValue(np.nan)
    # outdata.FlushCache() ##saves to disk!!

    band=None
    ds=None
