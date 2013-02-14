"""!

@brief Query GeoBrain WCS4DEM (http://geobrain.laits.gmu.edu/wcs4dem.htm) for digital elevation
model (DEM) data. 

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
  
  
Pre conditions
--------------
1. Configuration file must define the following sections and values:
   'GDAL/OGR', 'PATH_OF_GDAL_WARP'

2. The following metadata entry(ies) must be present in the study area section of the metadata associated with the project directory:
   bbox_wgs84

Post conditions
---------------
1. Will write the following entry(ies) to the manifest section of metadata associated with the project directory:
   dem [the name of the DEM raster]  

2. Will write the following entry(ies) to the study area section of metadata associated with the project directory:
   dem_res_x [X resolution of the DEM raster in units of the raster's projection]
   dem_res_y [Y resolution of the DEM raster in units of the raster's projection]
   dem_srs [spatial reference system of the DEM, in EPSG:<nnnn> format]
   dem_columns [number of pixels in the X direction]
   dem_rows [number of pixels in the Y direction]

Usage:
@code
python ./GetDEMExplorerDEMForBoundingbox.py -i macosx2.cfg -t EPSG:26918 -s 3 3 -p /path/to/project_dir -f DEM
@endcode
"""
import os
import sys
import errno
import argparse
import ConfigParser

import ecohydroworkflowlib.metadata as metadata
from ecohydroworkflowlib.wcs4dem.demquery import getDEMForBoundingBox
from ecohydroworkflowlib.spatialdata.utils import resampleRaster
from ecohydroworkflowlib.spatialdata.utils import getDimensionsForRaster
from ecohydroworkflowlib.spatialdata.utils import deleteGeoTiff

# Handle command line options
parser = argparse.ArgumentParser(description='Get DEM raster (in GeoTIFF format) for a bounding box from GeoBrain WCS4DEM')
parser.add_argument('-i', '--configfile', dest='configfile', required=True,
                    help='The configuration file')
parser.add_argument('-p', '--projectDir', dest='projectDir', required=False,
                    help='The directory to which metadata, intermediate, and final files should be saved')
parser.add_argument('-f', '--outfile', dest='outfile', required=True,
                    help='The name of the DEM file to be written.  File extension ".tif" will be added.')
parser.add_argument('-s', '--outputrasterresolution', dest='outputrasterresolution', required=True, nargs=2, type=float,
                    help='Two floating point numbers representing the desired X and Y output resolution of soil property raster maps; unit: meters')
parser.add_argument('-t', '--t_srs', dest='t_srs', required=True, 
                    help='Target spatial reference system of output, in EPSG:num format')
args = parser.parse_args()

if not os.access(args.configfile, os.R_OK):
    raise IOError(errno.EACCES, "Unable to read configuration file %s" %
                  args.configfile)
config = ConfigParser.RawConfigParser()
config.read(args.configfile)

if not config.has_option('GDAL/OGR', 'PATH_OF_GDAL_WARP'):
    sys.exit("Config file %s does not define option %s in section %s" & \
          (args.configfile, 'GDAL/OGR', 'PATH_OF_GDAL_WARP'))

if args.projectDir:
    projectDir = args.projectDir
else:
    projectDir = os.getcwd()
if not os.path.isdir(projectDir):
    raise IOError(errno.ENOTDIR, "Project directory %s is not a directory" % (projectDir,))
if not os.access(projectDir, os.W_OK):
    raise IOError(errno.EACCES, "Not allowed to write to project directory %s" %
                  projectDir)
projectDir = os.path.abspath(projectDir)

demFilename = "%s.tif" % (args.outfile)
# Overwrite DEM if already present
demFilepath = os.path.join(projectDir, demFilename)
if os.path.exists(demFilepath):
    os.unlink(demFilepath)

# Get study area parameters
studyArea = metadata.readStudyAreaEntries(projectDir)
bbox = studyArea['bbox_wgs84'].split()
bbox = dict({'minX': float(bbox[0]), 'minY': float(bbox[1]), 'maxX': float(bbox[2]), 'maxY': float(bbox[3]), 'srs': 'EPSG:4326'})

outputrasterresolutionX = args.outputrasterresolution[0]
outputrasterresolutionY = args.outputrasterresolution[1]

# Get DEM from DEMExplorer
tmpDEMFilename = "%s-TEMP.tif" % (args.outfile)
returnCode = getDEMForBoundingBox(projectDir, tmpDEMFilename, bbox=bbox, srs=args.t_srs)
assert(returnCode)

tmpDEMFilepath = os.path.join(projectDir, tmpDEMFilename)
# Resample DEM to target srs and resolution
resampleRaster(config, projectDir, tmpDEMFilepath, demFilename, \
               s_srs=args.t_srs, t_srs=args.t_srs, \
               trX=outputrasterresolutionX, trY=outputrasterresolutionY)
metadata.writeManifestEntry(projectDir, "dem", demFilename)
metadata.writeStudyAreaEntry(projectDir, "dem_res_x", outputrasterresolutionX)
metadata.writeStudyAreaEntry(projectDir, "dem_res_y", outputrasterresolutionY)
metadata.writeStudyAreaEntry(projectDir, "dem_srs", args.t_srs)

# Get rows and columns for resampled DEM
demFilepath = os.path.join(projectDir, demFilename)
(columns, rows) = getDimensionsForRaster(demFilepath)
metadata.writeStudyAreaEntry(projectDir, "dem_columns", columns)
metadata.writeStudyAreaEntry(projectDir, "dem_rows", rows)

# Clean-up
deleteGeoTiff(tmpDEMFilepath)