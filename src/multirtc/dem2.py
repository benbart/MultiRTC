from collections.abc import Generator
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from osgeo import gdal, ogr, osr
import numpy as np
from hyp3lib import DemError
from hyp3lib.util import GDALConfigManager
import shapely.geometry
import geojson
import json
import geopandas as gpd
import subprocess
from multirtc import dem


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
        dem_ma = dem_ds.GetRasterBand(1).ReadAsMaskedArray()
        geoid_ma = np.ma.array(geoid_data, mask=dem_ma.mask)
        dem_ma += geoid_ma
        dem_ds.GetRasterBand(1).WriteArray(dem_ma)
        dem_ds.FlushCache()
        del dem_ds


def process_dem(dem_file: Path):
    reproject_to_4326(dem_file)
    convert_to_height_above_ellipsoid(dem_file)


def polygon2geojsonfile(poly:shapely.geometry.Polygon, geojsonfile):
    geojson_geometry = shapely.geometry.mapping(poly)
    geojson_feature = geojson.Feature(geometry=geojson_geometry, properties={"name": "my_polygon"})
    feature_collection = geojson.FeatureCollection([geojson_feature])

    with open(geojsonfile, 'w') as f:
        geojson.dump(feature_collection, f, indent=2)


def readgeojsonfile(geojsonfile):
    with open(geojsonfile) as f:
        geojson = json.load(f)
        lst = []
        for feature in geojson['features']:
            lst.append(shapely.geometry.shape(feature['geometry']))
        if len(lst) == 1:
            polys = shapely.geometry.Polygon(lst[0])
        else:
            polys = shapely.geometry.MultiPolygon(lst)

    return polys


def download_geodata_cooperative_dem_for_footprint(output_path: Path, footprint: shapely.geometry.Polygon, buffer: float = 0.2) -> None:
    """
    Download the OPERA DEM for a given footprint and save it to the specified output path.

    Args:
        output_path: Path where the DEM will be saved.
        footprint: Polygon representing the area of interest.
        buffer: Buffer distance in degrees to extend the footprint.
    """
    output_dir = output_path.parent
    if output_path.exists():
        return output_path

    # footprint = shapely.geometry.box(*footprint.buffer(buffer).bounds)
    footprint = shapely.geometry.box(*footprint.bounds)
    footprints = dem.check_antimeridean(footprint)
    footprints = shapely.geometry.MultiPolygon(footprints)

    godata_coperative = "/media/jiangzhu/Elements/crrel/sar_data/dem/DGED5b_new2/JSON_AK_DGED5B_6N.geojson"

    gdf = gpd.read_file(godata_coperative)

    intersects_series = gdf.geometry.intersects(footprints)

    intersection_rows = gdf[intersects_series]

    with TemporaryDirectory() as temp_dir:
        input_files = []
        for index, row in intersection_rows.iterrows():
            seg2 = row['CellID']
            zone = seg2[0:2]
            nume = seg2[2:4]

            file = f'U_{seg2}_30km_2012_ArcticPS_NGA_DTM_3m_01.tif'
            url = f's3://arctic-trafficability/DGED5b/UTM_{zone}/{nume}/{file}'

            result = subprocess.run(['aws','s3', '--profile', 'arctic-traffic', 'cp', f'{url}', f'{temp_dir}/{file}'], capture_output=True, text=True)

            print(result.returncode)

            if result.returncode == 0 and Path(f'{temp_dir}/{file}').exists():
                input_files.append(f'{temp_dir}/{file}')

        vrt_filepath = f'{temp_dir}/dem.vrt'
        gdal.BuildVRT(vrt_filepath, input_files)
        ds = gdal.Open(str(vrt_filepath), gdal.GA_ReadOnly)
        gdal.Translate(str(output_path), ds, format='GTiff')
        ds = None


    reproject_to_4326(output_path)
    convert_to_height_above_ellipsoid(output_path)

