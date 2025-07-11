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
import rasterio
from rasterio.transform import Affine
from rasterio.mask import mask
from shapely.geometry import LinearRing, Polygon, box

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


def polygon2geojsonfile(poly:shapely.geometry.Polygon, geojsonfile, crs:str='EPSG:4326'):
    geo_series = gpd.GeoSeries([poly])
    geo_series.crs = crs
    gdf = gpd.GeoDataFrame({'geometry': geo_series, 'id': [1]})
    gdf.to_file(geojsonfile, driver="GeoJSON")


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


def clip_dem(input_dem:str, polygon:shapely.geometry.Polygon, output_dem:str):
    with rasterio.open(input_dem) as src:
        out_image, out_transform = mask(src, [polygon], crop=True)
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform
        })

    with rasterio.open(output_dem, "w", **out_meta) as dest:
        dest.write(out_image)


def padding_dem(input_dem:str, output_dem:str, pad_pixels:list):
    """
    pad nodata to the input_dem. The padding area is determined by the buffer length with the same unit
    as the input_dem. Ideally the buffer is the n*resolution of the input dem.
    Args:
        input_dem: input dem file
        output_dem: output dem file
        padding: List [pad_left, pad_right, pad_top, pad_bottom], padding pixel numbers of ever side
    Returns:

    """
    pad_left, pad_right, pad_top, pad_bottom = pad_pixels
    src = rasterio.open(input_dem)
    src_height = src.meta['height']
    src_width = src.meta['width']
    src_transform = src.meta['transform']
    padded_height = src_height + pad_top + pad_bottom
    padded_width = src_width + pad_left + pad_right

    padded_transform = Affine(
        src_transform.a, src_transform.b, src_transform.c - pad_left * src_transform.a,
        src_transform.d, src_transform.e, src_transform.f + abs(pad_top * src_transform.e)
    )

    profile = src.profile
    profile.update(
        driver = 'GTiff',
        height = padded_height,
        width = padded_width,
        transform = padded_transform
    )

    with rasterio.open(output_dem, 'w', **profile) as dst:
        window_col_start = pad_left
        window_row_start = pad_top
        dst.write(src.read(),
                  window=rasterio.windows.Window(window_col_start, window_row_start, src_width, src_height))


def extend_dem_to_polygon(input_dem:str, poly:shapely.geometry.Polygon, output_dem:str):
    """

    Args:
        input_dem: input dem file
        poly: polygon is in longitude and latitude (WGS84) geographic coordinate system.
        output_dem: output dem file

    Returns:

    """
    gdf84 = gpd.GeoSeries([poly], crs=f'EPSG:4326')
    src = rasterio.open(input_dem)
    src_epsg = src.profile['crs'].to_epsg()
    gdf_src = gdf84.to_crs(f'EPSG:{src_epsg}')

    poly = gdf_src.iloc[0]
    poly = box(*poly.bounds)

    transform = src.profile['transform']
    poly_src = box(*src.bounds)
    poly_comb = poly.union(poly_src)
    src_bounds = poly_src.bounds
    comb_bounds = poly_comb.bounds

    pad_left = int((src_bounds[0] - comb_bounds[0])/transform.a) + 5
    pad_right = int((comb_bounds[2] - src_bounds[2])/transform.a) + 5
    pad_bottom = int((src_bounds[1] - comb_bounds[1])/abs(transform.e)) + 5
    pad_top = int((comb_bounds[3] - src_bounds[3])/abs(transform.e)) + 5

    padding_dem(input_dem, output_dem, [pad_left, pad_right, pad_top, pad_bottom])


