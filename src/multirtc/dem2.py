from collections.abc import Generator
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from osgeo import gdal, ogr, osr

from hyp3lib import DemError
from hyp3lib.util import GDALConfigManager


DEM_GEOJSON = '/vsicurl/https://asf-dem-west.s3.amazonaws.com/v2/cop30_20250407.geojson'
# GEOID = '/vsicurl/https://asf-dem-west.s3.amazonaws.com/GEOID/us_nga_egm2008_1.tif'
GEOID = '/home/jiangzhu/projects/work/crrel/egm/us_nga_egm96_15.tif'
gdal.UseExceptions()
ogr.UseExceptions()

def reproject_to_4326(in_raster: Path):
    in_info = gdal.Info(str(in_raster), format='json')
    srs = osr.SpatialReference(wkt=in_info['coordinateSystem']['wkt'])
    if srs.GetAuthorityCode(None) != '4326':
        tmp_raster = in_raster.rename(in_raster.parent.joinpath('tmp.tif'))
        warp = gdal.Warp(in_raster, tmp_raster, dstSRS='EPSG:4326', resampleAlg='cubic')
        warp = None  # Closes the files

def convert_to_height_above_ellipsoid(dem_file: Path) -> None:
    dem_info = gdal.Info(str(dem_file), format='json')
    minx = dem_info['cornerCoordinates']['lowerLeft'][0]
    miny = dem_info['cornerCoordinates']['lowerLeft'][1]
    maxx = dem_info['cornerCoordinates']['upperRight'][0]
    maxy = dem_info['cornerCoordinates']['upperRight'][1]
    with NamedTemporaryFile() as geoid_file:
        gdal.Warp(
            geoid_file.name,
            GEOID,
            dstSRS=dem_info['coordinateSystem']['wkt'],
            outputBounds=[minx, miny, maxx, maxy],
            width=dem_info['size'][0],
            height=dem_info['size'][1],
            resampleAlg='cubic',
            multithread=True,
            format='GTiff',
        )
        geoid_ds = gdal.Open(geoid_file.name)
        geoid_data = geoid_ds.GetRasterBand(1).ReadAsArray()
        del geoid_ds

        dem_ds = gdal.Open(str(dem_file), gdal.GA_Update)
        dem_data = dem_ds.GetRasterBand(1).ReadAsArray()
        dem_data += geoid_data
        dem_ds.GetRasterBand(1).WriteArray(dem_data)
        dem_ds.FlushCache()
        del dem_ds


def process_dem(dem_file: Path):
    reproject_to_4326(dem_file)
    convert_to_height_above_ellipsoid(dem_file)

