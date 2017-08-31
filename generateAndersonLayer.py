import arcpy
from arcpy import env
from arcpy.sa import *

import pandas as pd
import os.path
import errno
import sys
import math
import glob

import shutil

# --- FUNCTIONS ----------------------------------------------------------------
def getRasterCalcArgument(df, categories, rasterValue,
                          gisDataLayerName,
                          shoulSetNoDataToZero = False):
    
    data = df.loc[df['anderson-code'] == categories[0]]
    
    result = "Con("

    count = len(data.index)

    for i in range(0, count):
        result += "(" + gisDataLayerName + " == "
        result += str(data.iloc[i]['cdl-code'])
        result += ")"
        if i < count - 1:
            result += " | "

    result += "," + str(rasterValue)
    
    if shoulSetNoDataToZero:
        result += ",0"
    
    result += ")\n"

    return result

def createAndersonLayer(cdlRasterBasename, cdlRasterYear, cdlRasterExtension, rasterCalcArgs, resultDirName, workingDirName):
    cdlRasterName = cdlRasterBasename + str(cdlRasterYear) + cdlRasterExtension
    print("Starting raster: "+cdlRasterName)

    # IMPORTANT: Make sure this variable name matches the parameter _layerNameForRasterCalcArgs
    rasterIn = Raster("Working" + os.path.sep + cdlRasterName)
    
    # Create layer for each anderson value
    rasterLayers = []
    print("... generating layers")
    count = len(rasterCalcArgs)
    for i in range(1, count):
        print("... generating layer " + str(i))
        exec("tempRaster = "+rasterCalcArgs[i])
        rasterLayers.append(tempRaster)

    # Combine all layers
    print("... Generating mosaic")
    rasterOutFileName = cdlRasterBasename + "anderson-" + str(cdlRasterYear) + ".tif"
    arcpy.MosaicToNewRaster_management(rasterLayers,
        resultDirName,rasterOutFileName,"","8_BIT_UNSIGNED","",
        1,"FIRST","FIRST")

    #if(shouldSaveIntermediateLayers == True):
    #    print("... Saving intermediate layers")
    #    for i in range(0, len(rasterLayers)):
    #        rasterToSave = arcpy.env.workspace + os.path.sep + workingDirName +  os.path.sep + "anderson-" + str(year) + "-" + str(i) + ".tif"
    #        rasterLayers[i].save(rasterToSave)
   
    # Clean temperary files
    #print("... cleaning up temperary files")
    #if arcpy.Exists("in_memory"):
    #    arcpy.Delete_management("in_memory")

    return os.path.join(resultDirName, rasterOutFileName)

def createDynamicMap(andersonMapPaths, outputDirWorking, outputDirPathResult):
    print("Creating dynamic map...")

    # Turn filenames into Rasters
    andersonMaps = []
    for andersonMapPath in andersonMapPaths:
        andersonMaps.append(Raster(andersonMapPath))

    print("... running cell statistics")
    majorityRasterTempPath = os.path.join(outputDirWorking, "majorityRasterTemp.tif")
    majorityPath = os.path.join(outputDirWorking, "majorityRaster.tif")
    # Create MAJORITY Cell Statistic layer
    majorityRasterTemp = arcpy.gp.CellStatistics_sa(andersonMaps, 
        majorityRasterTempPath,
        "MAJORITY", "DATA")

    # Returns largest YYYY in list of anthromeYYYYn.tif
    andersonPathCurrYearPath = sorted(andersonMapPaths, reverse=True)[0]

    # The MAJORITY function in Cell Statistics returns NoData if a tie for majority, so fill these with current year's value'
    majorityRaster = Con(IsNull(majorityRasterTempPath), andersonPathCurrYearPath, majorityRasterTempPath)
    majorityRaster.save(majorityPath)

    varietyRaster = arcpy.gp.CellStatistics_sa(andersonMaps, 
        os.path.join(outputDirWorking, "varietyRaster.tif"),
        "VARIETY", "DATA")
    
    varietyPath = os.path.join(outputDirWorking, "varietyRaster.tif")

    # Get cutoff value, should be greater than 50%
    dynamicUnstableCuttoff = len(andersonMapPaths)/2

    print("... generating stable, dynamic, and unstable rasters")
    stableRaster = Con(varietyPath, majorityPath, "", "Value = 1")
    dynamicRaster = Con(varietyPath, Raster(majorityPath) + 100, "", "Value > 1 AND Value < " + str(dynamicUnstableCuttoff))
    unstableRaster = Con(varietyPath, Raster(majorityPath) + 200, "", "Value >= " + str(dynamicUnstableCuttoff))

    stableRaster.save(os.path.join(outputDirPathResult, "andersonStable.tif"))
    dynamicRaster.save(os.path.join(outputDirPathResult, "andersonDynamic.tif"))
    unstableRaster.save(os.path.join(outputDirPathResult, "andersonUnstable.tif"))

    print("... generating mosaic")
    arcpy.MosaicToNewRaster_management(
        [stableRaster, dynamicRaster, unstableRaster],
        outputDirPathResult,"anderson-athrome-mandan.tif",
        "",
        "8_BIT_UNSIGNED","",1,"FIRST","FIRST")

    #print("... cleaning up")
    #arcpy.Delete_management(majorityRaster)
    #arcpy.Delete_management(majorityRasterTemp)
    #arcpy.Delete_management(varietyRaster)



# --- PARAMETERS ---------------------------------------------------------------
_cdlToAndersonMapFilename  = "CdlToAndersonMap.csv"
_layerNameForRasterCalcArgs = "rasterIn"

# Input raster filenames should be of the form {basename}{year}{extension}
# Provides basename to be combined with years and extension to create
# e.g. CDL_CAF_2016.tif, basename = "CDL_CAF_"
_inputRasterBasename = "cdl-mandan-"
_years = [
    2016,
    2015,
    2014,
    2013,
    2012,
    2011,
    2010]
_inputRasterExtension = ".tif"
_workingDirName = "WorkingTemp"

_resultDirName = "Results"
_tempFolderName = "temp"
shouldSaveIntermediateLayers = True

# Environment Parameters
arcpy.env.workspace = r"C:\OneDrive\OneDrive - Washington State University (email.wsu.edu)\Projects\CafModelingAndersonClassification\Working\ArcMap"
arcpy.env.overwriteOutput = True
#arcpy.env.snapRaster = arcpy.env.workspace + os.path.sep + _irrigatedPath

# --- MAIN ---------------------------------------------------------------------
# Setup
tempFolderPath = arcpy.env.workspace + os.path.sep + _tempFolderName
shutil.rmtree(tempFolderPath, ignore_errors=True)
os.makedirs(tempFolderPath)
arcpy.env.scratchWorkspace = tempFolderPath

# TESTING --------------------------------------------

#arcpy.CheckOutExtension("spatial")
#
#_andersonMapPaths = []
#_andersonMapPaths.append(os.path.join(
#   arcpy.env.workspace,  _resultDirName, "anderson-anthrome-2015.tif"
#))
#_andersonMapPaths.append(os.path.join(
#   arcpy.env.workspace,  _resultDirName, "anderson-anthrome-2016.tif"
#))
#
#createDynamicMap(_andersonMapPaths, 
#    os.path.join(arcpy.env.workspace, _workingDirName),
#    os.path.join(arcpy.env.workspace, _resultDirName))
#
#arcpy.CheckInExtension("spatial")
#
#quit()

# -------------------------------------------- TESTING

# Read in map attributes
try:
    df = pd.read_csv(_cdlToAndersonMapFilename)
except Exception as e:
    sys.stderr.write('ERROR: %sn' % str(e))

# Get unique categories in the data
categories = df["anderson-code"].unique()

arcpy.CheckOutExtension("spatial")

# Get raster arguments for each category
rasterStrings = []
for cat in categories:
    rasterStrings.append(
        getRasterCalcArgument(df, [cat], cat, _layerNameForRasterCalcArgs))
        
# Generate a map of all Anderson level 1 classifications for all years
andersonMapPaths = []
for year in _years:
    andersonMapPaths.append(
        createAndersonLayer(_inputRasterBasename, year, _inputRasterExtension,
            rasterStrings, _resultDirName, _workingDirName))

# Determine stable, unstable, dynamic layers then compress into single map
createDynamicMap(andersonMapPaths, 
    os.path.join(arcpy.env.workspace, _workingDirName),
    os.path.join(arcpy.env.workspace, _resultDirName))

arcpy.CheckInExtension("spatial")

# Cleanup
#shutil.rmtree(tempFolderPath, ignore_errors=True)
#arcpy.Delete_management(tempFolderPath)