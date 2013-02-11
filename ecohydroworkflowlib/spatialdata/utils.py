"""!@package ecohydroworkflowlib.spatialdata.utils
    
@brief Generic utilities for manipulating spatial data sets.
@brief Builds a task-oriented API, for select operations, on top of
GDAL/OGR utilities, GDAL/OGR API, Proj API.

This software is provided free of charge under the New BSD License. Please see
the following license information:

Copyright (c) 2013, University of North Carolina at Chapel Hill
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of the University of North Carolina at Chapel Hill nor the
      names of its contributors may be used to endorse or promote products
      derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE UNIVERSITY OF NORTH CAROLINA AT CHAPEL HILL
BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR 
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE
GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT 
LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


@author Brian Miles <brian_miles@unc.edu>
"""
import os, sys, errno
from math import sqrt

import gdal
import ogr
import osr
from pyproj import Proj
from pyproj import transform
from pyproj import Geod
from pyproj import polygonarea

SHP_MINX = 0
SHP_MAXX = 1
SHP_MINY = 2
SHP_MAXY = 3

RASTER_RESAMPLE_METHOD = ['near', 'bilinear', 'cubic', 'cubicspline', 'lanczos']


def transformCoordinates(sourceX, sourceY, t_srs, s_srs="EPSG:4326"):
    """!Transform a pair of X,Y coordinates from one reference system to another
    
        @param sourceX A float representing the X coordinate
        @param sourceY A float representing the Y coordinate
        @param t_srs A string representing the spatial reference system of the output coordinates
        @param s_srs A string representing the spatial reference system, in EPSG format, of the input
            coordinates
        
        @return A tuple of floats representing the transformed coordinates
    """
    p_in = Proj(init=s_srs)
    p_out = Proj(init=t_srs)
    return transform(p_in, p_out, sourceX, sourceY)


def extractTileFromRaster(config, outputDir, inRasterFilename, outRasterFilename, bbox):
    """!Extract a tile from a raster. Tile extent is defined by supplied bounding box 
        with coordinates defined in WGS84 (EPSG:4326).
        
        @note Output raster will be in LZW-compressed GeoTIFF file.
        @note Will silently return if output raster already exists.
        
        @param config Python ConfigParser containing the section 'GDAL/OGR' and option 'PATH_OF_GDAL_TRANSLATE'
        @param outputDir String representing the absolute/relative path of the directory into which output raster
         should be written
        @param inRasterFilename String representing the name of the input raster
        @param outRasterFilename String representing the name of the output raster
        @param bbox A dict containing keys: minX, minY, maxX, maxY, srs, where srs='EPSG:4326' (WGS84)
    """
    gdalCmdPath = config.get('GDAL/OGR', 'PATH_OF_GDAL_TRANSLATE')
    if not os.access(gdalCmdPath, os.X_OK):
        raise IOError(errno.EACCES, "The gdal_translate binary at %s is not executable" %
                      gdalCmdPath)
    gdalCmdPath = os.path.abspath(gdalCmdPath)
    
    if not os.path.isdir(outputDir):
        raise IOError(errno.ENOTDIR, "Output directory %s is not a directory" % (outputDir,))
    if not os.access(outputDir, os.W_OK):
        raise IOError(errno.EACCES, "Not allowed to write to output directory %s" % (outputDir,))
    outputDir = os.path.abspath(outputDir)
    
    inRasterFilepath = os.path.join(outputDir, inRasterFilename)
    outRasterFilepath = os.path.join(outputDir, outRasterFilename)
    
    if not os.path.exists(outRasterFilepath):
        # Convert into coordinate system of inRaster
        inRasterSrs = getSpatialReferenceForRaster(inRasterFilepath)
        inSrs = osr.SpatialReference()
        assert(inSrs.ImportFromWkt(inRasterSrs[4]) == 0)
        p_in = Proj(init="EPSG:4326")
        p_out = Proj(inSrs.ExportToProj4())
        (ulX, ulY) = transform(p_in, p_out, bbox['minX'], bbox['maxY'])
        (lrX, lrY) = transform(p_in, p_out, bbox['maxX'], bbox['minY'])
        
        gdalCommand = "%s -q -stats -of GTiff -co 'COMPRESS=LZW' -projwin %f %f %f %f %s %s" \
                        % (gdalCmdPath, ulX, ulY, lrX, lrY, \
                           inRasterFilepath, outRasterFilepath)
        #print gdalCommand
        returnCode = os.system(gdalCommand)
        if returnCode != 0:
            raise Exception("GDAL command %s failed." % (gdalCommand,)) 


def resampleRaster(config, outputDir, inRasterFilename, outRasterFilename, \
                s_srs, t_srs, trX, trY, resampleMethod='bilinear'):
    """!Resample raster from one spatial reference system and resolution to another.
        
        @note Output raster will be in LZW-compressed GeoTIFF file.
        @note Will silently return if output raster already exists.
    
        @param config Python ConfigParser containing the section 'GDAL/OGR' and option 'PATH_OF_GDAL_WARP'
        @param outputDir String representing the absolute/relative path of the directory into which output raster
            should be written
        @param inRasterFilename String representing the name of the input raster
        @param outRasterFilename String representing the name of the output raster
        @param s_srs String representing the spatial reference of the input raster, if s_srs is None, 
            the input raster's spatial reference
        @param t_srs String representing the spatial reference of the output raster
        @param trX Float representing the X resolution of the output raster (in target spatial reference units)
        @param trY Float representing the Y resolution of the output raster (in target spatial reference units) 
        @param resampleMethod String representing resampling method to use. Must be one of spatialdatalib.utils.RASTER_RESAMPLE_METHOD.
        
        @exception ConfigParser.NoSectionError
        @exception ConfigParser.NoOptionError
        @exception IOError(errno.ENOTDIR) if outputDir is not a directory
        @exception IOError(errno.EACCESS) if outputDir is not writable
        @exception ValueError if trX or trY are not floating point numbers greater than 0
        @exception Exception if a gdal_warp command fails
    """
    gdalCmdPath = config.get('GDAL/OGR', 'PATH_OF_GDAL_WARP')
    if not os.access(gdalCmdPath, os.X_OK):
        raise IOError(errno.EACCES, "The gdal_rasterize binary at %s is not executable" %
                      gdalCmdPath)
    gdalCmdPath = os.path.abspath(gdalCmdPath)
    
    if not os.path.isdir(outputDir):
        raise IOError(errno.ENOTDIR, "Output directory %s is not a directory" % (outputDir,))
    if not os.access(outputDir, os.W_OK):
        raise IOError(errno.EACCES, "Not allowed to write to output directory %s" % (outputDir,))
    outputDir = os.path.abspath(outputDir)
    
    trX = float(trX)
    if trX <= 0.0:
        raise ValueError("trX must be > 0.0")
    trY = float(trY)
    if trY <= 0.0:
        raise ValueError("trY must be > 0.0")
    
    assert(resampleMethod in RASTER_RESAMPLE_METHOD)
    
    inRasterFilepath = os.path.join(outputDir, inRasterFilename)
    outRasterFilepath = os.path.join(outputDir, outRasterFilename)
    
    if not os.path.exists(outRasterFilepath):
        if s_srs is None:
            gdalCommand = "%s -q -t_srs %s -tr %f %f -r %s -of GTiff -co 'COMPRESS=LZW' %s %s" \
                            % (gdalCmdPath, t_srs, trX, trY, resampleMethod, \
                               inRasterFilepath, outRasterFilepath)
        else:
            gdalCommand = "%s -q -s_srs %s -t_srs %s -tr %f %f -r %s -of GTiff -co 'COMPRESS=LZW' %s %s" \
                            % (gdalCmdPath, s_srs, t_srs, trX, trY, resampleMethod, \
                               inRasterFilepath, outRasterFilepath)
        #print gdalCommand
        returnCode = os.system(gdalCommand)
        if returnCode != 0:
            raise Exception("GDAL command %s failed." % (gdalCommand,)) 


def convertGMLToShapefile(config, outputDir, gmlFilepath, layerName, t_srs):
    """!Convert a GML file to a shapefile.  Will silently exit if shapefile already exists
    
        @param config A Python ConfigParser containing the section 'GDAL/OGR' and option 'PATH_OF_OGR2OGR'
        @param outputDir String representing the absolute/relative path of the directory into which shapefile should be written
        @param gmlFilepath String representing the absolute path of the GML file to convert
        @param layerName String representing the name of the layer contained in the GML file to write to a shapefile
        @param t_srs String representing the spatial reference system of the output shapefile, of the form 'EPSG:XXXX'
        
        @return String representing the name of the shapefile written
    
        @exception Exception if the conversion failed.
    """
    pathToOgrCmd = config.get('GDAL/OGR', 'PATH_OF_OGR2OGR')
    
    if not os.path.isdir(outputDir):
        raise IOError(errno.ENOTDIR, "Output directory %s is not a directory" % (outputDir,))
    if not os.access(outputDir, os.W_OK):
        raise IOError(errno.EACCES, "Not allowed to write to output directory %s" % (outputDir,))
    outputDir = os.path.abspath(outputDir)
    
    shpFilename = "%s.shp" % (layerName,)
    shpFilepath = os.path.join(outputDir, shpFilename)
    if not os.path.exists(shpFilepath):
        ogrCommand = "%s -f 'ESRI Shapefile' -nln %s -t_srs %s %s %s" % (pathToOgrCmd, "MapunitPolyExtended", t_srs, shpFilepath, gmlFilepath)
        returnCode = os.system(ogrCommand)
        if returnCode != 0:
            raise Exception("GML to shapefile command %s returned %d" % (ogrCommand, returnCode))
    
    return shpFilename


def deleteShapefile(shpfilePath):
    """!Delete shapefile and its related files (.dbf, .prj, .shx)
        
        @param shpfilePath -- Path, including filename, of the shapefile to be deleted
    """
    SHP_EXT = ['dbf', 'prj', 'shx']
    fileName = os.path.splitext(shpfilePath)[0]
    if os.path.exists(shpfilePath):
        os.remove(shpfilePath)
    for ext in SHP_EXT:
        tmpFilepath = fileName + "." + ext
        if os.path.exists(tmpFilepath):
            os.remove(tmpFilepath)


def deleteGeoTiff(geoTiffPath):
    """!Delete GeoTIFF and its related files (.aux.xml)
        
        @param geoTiffPath -- Path, including filename, of the GeoTIFF to be deleted
    """
    GTIFF_EXT = ['tif.aux.xml']
    fileName = os.path.splitext(geoTiffPath)[0]
    if os.path.exists(geoTiffPath):
        os.remove(geoTiffPath)
    for ext in GTIFF_EXT:
        tmpFilepath = fileName + "." + ext
        if os.path.exists(tmpFilepath):
            os.remove(tmpFilepath)


def calculateBoundingBoxAreaSqMeters(bbox):
    """!Calculate bbox area in square meters
    
        @param bbox A dict containing keys: minX, minY, maxX, maxY, srs, where srs='EPSG:4326'
        
        @return Float representing the bounding box area in square meters
    """
    assert(bbox['srs'] == 'EPSG:4326')
    # Points for polygon representing bounding box
    points = [{'lat':bbox['minY'], 'lon':bbox['minX']}, 
              {'lat':bbox['minY'], 'lon':bbox['maxX']}, 
              {'lat':bbox['maxY'], 'lon':bbox['maxX']}, 
              {'lat':bbox['maxY'], 'lon':bbox['minX']}]

    geod = Geod(ellps='WGS84')
    (numPoints, perimeter, area) = polygonarea.PolygonArea.Area(geod.G, points, None)
    return area


def tileBoundingBox(bbox, threshold):
    """!Break up bounding box into tiles if bounding box is larger than threshold. 
        Bounding box must be defined by WGS84 lat,lon coordinates
        
        @param bbox A dict containing keys: minX, minY, maxX, maxY, srs, where srs='EPSG:4326'
        @param threshold Float representing threshold area above which bounding box will be tiled. Units: sq. meters
        
        @return A list containing tiles defined as a dict containing keys: minX, minY, maxX, maxY, srs, where srs='EPSG:4326'
    """
    assert(bbox['srs'] == 'EPSG:4326')
    area = calculateBoundingBoxAreaSqMeters(bbox)
    
    bboxes = []
    if area <= threshold:
        sys.stderr.write("Area of bounding box <= threshold, no tiling\n")
        bboxes.append(bbox)
    else:
        sys.stderr.write("Area of bounding box > threshold, tiling ...\n")
        # Tile it
        # Calculate the length of a "side" of a square tile
        tileSide = sqrt(threshold)
        # Start at the southwestern-most corner of the bounding box
        minLat = bbox['minY']
        minLon = bbox['minX']
        #maxLat = None; maxLon = None
        while minLat < bbox['maxY']: 
            (lon, maxLat, backAz) = geod.fwd(lons=minLon, lats=minLat, az=NORTH, dist=tileSide)
            while minLon < bbox['maxX']:
                (maxLon, lat, backAz) = geod.fwd(lons=minLon, lats=maxLat, az=EAST, dist=tileSide)
                bboxes.append(dict({'minX': minLon, 'minY': minLat, 'maxX': maxLon, 'maxY': maxLat, 'srs': 'EPSG:4326'}))
                minLon = maxLon
            minLat = maxLat
            minLon = bbox['minX']
                                                
    return bboxes


def getBoundingBoxForShapefile(shapefileName):
    """!Return the bounding box, in WGS84 (EPSG:4326) coordinates, for the ESRI shapefile.  
        Assumes shapefile exists and is readable.
        Based on http://svn.osgeo.org/gdal/trunk/gdal/swig/python/samples/ogrinfo.py
   
        @param shapefileName A string representing the path of the shapefile whose bounding box should be determined.
        
        @return A dict containing keys: minX, minY, maxX, maxY, srs, where srs='EPSG:4326'
    """
    minX = 0
    minY = 90
    maxX = -180
    maxY = 0
    
    # Get spatial reference system for shapefile
    poDS = ogr.Open(shapefileName, True)
    assert(poDS.GetLayerCount() > 0)
    poLayer = poDS.GetLayer(0)
    assert(poLayer)
    srs_proj4 = poLayer.GetSpatialRef().ExportToProj4()
    
    # Setup Proj to convert to EPSG:4326 (WGS84)
    p_in = Proj(srs_proj4)
    p_out = Proj(init="EPSG:4326")
    
    # Get bounding box for shapefile
    poFeature = poLayer.GetNextFeature()
    while poFeature is not None:
        poGeometry = poFeature.GetGeometryRef()
        poEnvelope = poGeometry.GetEnvelope()
        # Convert coordinates to EPSG:4326 (WGS84)
        (tmpMinX, tmpMinY) = transform(p_in, p_out, poEnvelope[SHP_MINX], poEnvelope[SHP_MINY])
        (tmpMaxX, tmpMaxY) = transform(p_in, p_out, poEnvelope[SHP_MAXX], poEnvelope[SHP_MAXY])
        
        if tmpMinX < minX:
            minX = tmpMinX
        if tmpMinY < minY:
            minY = tmpMinY
        if tmpMaxX > maxX:
            maxX = tmpMaxX
        if tmpMaxY > maxY:
            maxY = tmpMaxY 
        #print minX,minY,maxX,maxY  
        poFeature = poLayer.GetNextFeature()
            
    return dict({'minX': minX, 'minY': minY, 'maxX': maxX, 'maxY': maxY, 'srs': 'EPSG:4326'})


def getMeterConversionFactorForLinearUnitOfGMLfile(gmlFilename):
    """!Get conversion factor for converting a GML file's linear unit into meters
    
        @param gmlFilename String representing the GML file
        
        @return Float representing the conversion factor
    
        @exception IOError(errno.EACCES) if the GML file cannot be opened
    """
    driver = ogr.GetDriverByName('GML')
    inDS = driver.Open(gmlFilename, 0)
    if inDS is None:
        raise IOError(errno.EACCES, "Unable to open GML file %s" %
                      gmlFilename)
    inLayer = inDS.GetLayer()
    soilSrs = inLayer.GetSpatialRef()
    return soilSrs.GetLinearUnits()


def getMeterConversionFactorForLinearUnitOfShapefile(shpFilename):
    """!Get conversion factor for converting a shapefile's linear unit into meters
    
        @param shpFilename String representing the shapefile
        
        @return Float representing the conversion factor
    
        @exception IOError(errno.EACCES) if the shapefile cannot be opened
    """
    driver = ogr.GetDriverByName('ESRI Shapefile')
    inDS = driver.Open(shpFilename, 0)
    if inDS is None:
        raise IOError(errno.EACCES, "Unable to open shapefile %s" %
                      shpFilename)
    inLayer = inDS.GetLayer()
    soilSrs = inLayer.GetSpatialRef()
    return soilSrs.GetLinearUnits()


def getSpatialReferenceForRaster(filename):
    """!Get pixel size and unit for DEM.  Uses GDAL library
        Code adapted from: http://svn.osgeo.org/gdal/trunk/gdal/swig/python/samples/gdalinfo.py
        
        @param filename String representing the DEM file to read pixel size and units
        
        @return A tuple of the form: 
        (pixelWidth, pixelHeight, linearUnitsName, linearUnitsConversionFactor, WKT SRS string)
        
        @exception IOError if filename is not readable
    """
    pixelWidth = None
    pixelHeight = None
    linearUnitsName = None
    linearUnitsConversionFactor = None
    pszProjection = None
    
    if not os.access(filename, os.R_OK):
        raise IOError(errno.EACCES, "Not allowed to read DEM %s to read pixel size and units" %
                      filename)
    
    hDataset = gdal.Open(filename, gdal.GA_ReadOnly)

    if hDataset is not None:
        adfGeoTransform = hDataset.GetGeoTransform(can_return_null=True)
        if adfGeoTransform is not None:
            pixelWidth = abs(adfGeoTransform[1])
            pixelHeight = abs(adfGeoTransform[5])
        
        pszProjection = hDataset.GetProjectionRef()
        if pszProjection is not None:
            hSRS = osr.SpatialReference()
            if hSRS.ImportFromWkt(pszProjection) == gdal.CE_None:
                linearUnitsName = hSRS.GetLinearUnitsName()
                linearUnitsConversionFactor = hSRS.GetLinearUnits()
            
    return (pixelWidth, pixelHeight, linearUnitsName, linearUnitsConversionFactor, pszProjection)

def getDimensionsForRaster(filename):
    """!Get number of columns and rows for raster.  Uses GDAL library
        Code adapted from: http://svn.osgeo.org/gdal/trunk/gdal/swig/python/samples/gdalinfo.py
        
        @param filename String representing the DEM file to read pixel size and units
        
        @return A tuple of the form: 
        (columns, rows) or None if raster could not be opened
        
        @exception IOError if filename is not readable
    """
    columns = None
    rows = None
    
    if not os.access(filename, os.R_OK):
        raise IOError(errno.EACCES, "Not allowed to read DEM %s to read number of columns and rows" %
                      filename)
    
    hDataset = gdal.Open(filename, gdal.GA_ReadOnly)

    if hDataset is not None:
        columns = hDataset.RasterXSize
        rows = hDataset.RasterYSize
            
    return (columns, rows)