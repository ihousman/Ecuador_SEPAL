# Landsat package


import ee
import math 
from utils import *
from paramsTemplate import *

class env(object):

    def __init__(self):
        """Initialize the environment."""   
        ##########################################
        # Export variables                       #
        ##########################################      

        self.assetId ="projects/Sacha/PreprocessedData/L8_Annual_V4_QBands/"
        self.name = "LS_AN_" 
        self.exportScale = 20   
        self.epsg = "EPSG:32717"

        # Initialize the Earth Engine object, using the authentication credentials.       
        self.startDate = ""
        self.endDate = ""
        self.location = ee.Geometry.Polygon([[103.876,18.552],[105.806,18.552],[105.806,19.999],[103.876,19.999],[103.876,18.552]])
        
        self.metadataCloudCoverMax = 80
        self.cloudThreshold = 10
        self.hazeThresh = 200
              
        self.maskSR = True
        self.cloudMask = True
        self.hazeMask = True
        self.shadowMask = True
        self.brdfCorrect = True
        self.terrainCorrection = True

        self.terrainScale = 600
        self.dem = ee.Image("JAXA/ALOS/AW3D30_V1_1").select("MED")

        self.cloudScoreThresh= 2
        self.cloudScorePctl= 11
        self.zScoreThresh= -0.8
        self.shadowSumThresh= 0.15
        self.contractPixels= 1.2
        self.dilatePixels= 2.5

                        
        self.SLC = False
        self.percentiles = [20,80] 
        
        self.medoidBands = ee.List(['blue','green','red','nir','swir1','swir2'])
        self.divideBands = ee.List(['blue','green','red','nir','swir1','swir2'])
        self.bandNamesLandsat = ee.List(['blue','green','red','nir','swir1','thermal','swir2','sr_atmos_opacity','pixel_qa','radsat_qa'])
        self.sensorBandDictLandsatSR = ee.Dictionary({'L8' : ee.List([1,2,3,4,5,7,6,9,10,11]),\
                                                      'L7' : ee.List([0,1,2,3,4,5,6,7,9,10]),\
                                                      'L5' : ee.List([0,1,2,3,4,5,6,7,9,10]),\
                                                      'L4' : ee.List([0,1,2,3,4,5,6,7,9,10])})
                                                      

class functions():       
    def __init__(self):
        """Initialize the Surfrace Reflectance app."""  
    
        # get the environment
        self.env = env()    
        
    def getLandsat(self,aoi,year,regionName):
        self.env.regionName = regionName
        self.env.location = aoi
        self.env.startDate = ee.Date.fromYMD(year,1,1)
        self.env.endDate = ee.Date.fromYMD(year+1,1,1)

        self.paramSwitch = Switcher().paramSelect(self.env.regionName)

        self.env.cloudScoreThresh = self.paramSwitch[0]
        self.env.cloudScorePctl= self.paramSwitch[1]
        self.env.zScoreThresh= self.paramSwitch[2]
        self.env.shadowSumThresh= self.paramSwitch[3]
        self.env.contractPixels= self.paramSwitch[4]
        self.env.dilatePixels= self.paramSwitch[5]


        landsat5 =  ee.ImageCollection('LANDSAT/LT05/C01/T1_SR').filterDate(self.env.startDate,self.env.endDate).filterBounds(self.env.location)
        landsat5 = landsat5.filterMetadata('CLOUD_COVER','less_than',self.env.metadataCloudCoverMax)
        landsat5 = landsat5.select(self.env.sensorBandDictLandsatSR.get('L5'),self.env.bandNamesLandsat).map(self.defringe)

        landsat7 =  ee.ImageCollection('LANDSAT/LE07/C01/T1_SR').filterDate(self.env.startDate,self.env.endDate).filterBounds(self.env.location)
        landsat7 = landsat7.filterMetadata('CLOUD_COVER','less_than',self.env.metadataCloudCoverMax)
        landsat7 = landsat7.select(self.env.sensorBandDictLandsatSR.get('L7'),self.env.bandNamesLandsat)


        landsat8 =  ee.ImageCollection('LANDSAT/LC08/C01/T1_SR').filterDate(self.env.startDate,self.env.endDate).filterBounds(self.env.location)
        landsat8 = landsat8.filterMetadata('CLOUD_COVER','less_than',self.env.metadataCloudCoverMax)
        landsat8 = landsat8.select(self.env.sensorBandDictLandsatSR.get('L8'),self.env.bandNamesLandsat)

        if (self.env.SLC or year < 2004):
            landsat = landsat5.merge(landsat7).merge(landsat8)
        else:
            landsat = landsat5.merge(landsat8)
        
        print landsat.size().getInfo()
        if landsat.size().getInfo() > 0:
            
            # mask clouds using the QA band
            if self.env.maskSR == True:
                #print "removing clouds" 
                landsat = landsat.map(self.CloudMaskSRL8)    
            
            
            # mask clouds using cloud mask function
            if self.env.hazeMask == True:
                #print "removing haze"
                landsat = landsat.map(self.maskHaze)


            # mask clouds using cloud mask function
            if self.env.shadowMask == True:
                #print "shadow masking"
                self.fullCollection = ee.ImageCollection('LANDSAT/LC08/C01/T1_SR').filterBounds(self.env.location).select(self.env.sensorBandDictLandsatSR.get('L8'),self.env.bandNamesLandsat)  
                landsat = self.maskShadows(landsat)
            
            
            landsat = landsat.map(self.scaleLandsat).map(self.addDateYear)

            # mask clouds using cloud mask function
            if self.env.cloudMask == True:
                #print "removing some more clouds"
                landsat = landsat.map(self.maskClouds)

            if self.env.brdfCorrect == True:
                landsat = landsat.map(self.brdf)
                        
            if self.env.terrainCorrection == True:
                landsat = ee.ImageCollection(landsat.map(self.terrain))
            
            medoid = self.medoidMosaic(landsat)
            medoidDown = ee.Image(self.medoidMosaicPercentiles(landsat,self.env.percentiles[0]))
            medoidUp = self.medoidMosaicPercentiles(landsat,self.env.percentiles[1])
            stdevBands = self.addSTDdev(landsat)
            
            mosaic = medoid.addBands(medoidDown).addBands(medoidUp).addBands(stdevBands)
            
            

            mosaic = self.reScaleLandsat(mosaic)
            
            mosaic = self.setMetaData(mosaic)

            self.exportMap(mosaic,self.env.location)
            return mosaic
       
    def addDateYear(self,img):
        """add a date and year bands"""
        date = ee.Date(img.get("system:time_start"))
        
        day = date.getRelative('day','year').add(1);
        yr = date.get('year');
        mk = img.mask().reduce(ee.Reducer.min());
        
        img = img.addBands(ee.Image.constant(day).mask(mk).uint16().rename('date'));
        img = img.addBands(ee.Image.constant(yr).mask(mk).uint16().rename('year'));
        
        return img;

    def CloudMaskSRL8(self,img):
        """apply cf-mask Landsat""" 
        QA = img.select("pixel_qa")
        
        shadow = QA.bitwiseAnd(8).neq(0);
        cloud =  QA.bitwiseAnd(32).neq(0);
        return img.updateMask(shadow.Not()).updateMask(cloud.Not()).copyProperties(img)     
         
    def scaleLandsat(self,img):
        """Landast is scaled by factor 0.0001 """
        thermal = img.select(ee.List(['thermal'])).multiply(0.1)
        scaled = ee.Image(img).select(self.env.divideBands).multiply(ee.Number(0.0001))
        
        return img.select(['TDOMMask']).addBands(scaled).addBands(thermal)

    def reScaleLandsat(self,img):
        """Landast is scaled by factor 0.0001 """
        
        noScaleBands = ee.List(['date','year','TDOMMask','cloudMask','count'])
        noScale = ee.Image(img).select(noScaleBands)

        thermalBand = ee.List(['thermal'])
        thermal = ee.Image(img).select(thermalBand).multiply(10)
                
        otherBands = ee.Image(img).bandNames().removeAll(thermalBand).removeAll(noScaleBands)
        scaled = ee.Image(img).select(otherBands).divide(0.0001)
        
        image = ee.Image(scaled.addBands([thermal,noScale])).int16()
        
        return image.copyProperties(img)
        

    def maskHaze(self,img):
        """ mask haze """
        opa = ee.Image(img.select(['sr_atmos_opacity']).multiply(0.001))
        haze = opa.gt(self.env.hazeThresh)
        return img.updateMask(haze.Not())
 

    def maskClouds(self,img):
        """
        Computes spectral indices of cloudyness and take the minimum of them.
        
        Each spectral index is fairly lenient because the group minimum 
        is a somewhat stringent comparison policy. side note -> this seems like a job for machine learning :)
        originally written by Matt Hancher for Landsat imageryadapted to Sentinel by Chris Hewig and Ian Housman
        """
        
        score = ee.Image(1.0);
        # Clouds are reasonably bright in the blue band.
        blue_rescale = img.select('blue').subtract(ee.Number(0.1)).divide(ee.Number(0.3).subtract(ee.Number(0.1)))
        score = score.min(blue_rescale);

        # Clouds are reasonably bright in all visible bands.
        visible = img.select('red').add(img.select('green')).add(img.select('blue'))
        visible_rescale = visible.subtract(ee.Number(0.2)).divide(ee.Number(0.8).subtract(ee.Number(0.2)))
        score = score.min(visible_rescale);

        # Clouds are reasonably bright in all infrared bands.
        infrared = img.select('nir').add(img.select('swir1')).add(img.select('swir2'))
        infrared_rescale = infrared.subtract(ee.Number(0.3)).divide(ee.Number(0.8).subtract(ee.Number(0.3)))
        score = score.min(infrared_rescale);

        # Clouds are reasonably cool in temperature.
        temp_rescale = img.select('thermal').subtract(ee.Number(300)).divide(ee.Number(290).subtract(ee.Number(300)))
        score = score.min(temp_rescale);

        # However, clouds are not snow.
        ndsi = img.normalizedDifference(['green', 'swir1']);
        ndsi_rescale = ndsi.subtract(ee.Number(0.8)).divide(ee.Number(0.6).subtract(ee.Number(0.8)))
        score =  score.min(ndsi_rescale).multiply(100).byte();
        mask = score.lt(self.env.cloudScoreThresh).rename(['cloudMask']);
        img = img.updateMask(mask).addBands([mask]);
        
        return img;
        
    def maskShadows(self,collection):

        def TDOM(image):
            zScore = image.select(shadowSumBands).subtract(irMean).divide(irStdDev)
            irSum = image.select(shadowSumBands).reduce(ee.Reducer.sum())
            TDOMMask = zScore.lt(self.env.zScoreThresh).reduce(ee.Reducer.sum()).eq(2)\
                .And(irSum.lt(self.env.shadowSumThresh)).Not()
            TDOMMask = TDOMMask.focal_min(self.env.contractPixels).focal_max(self.env.dilatePixels).rename(['TDOMMask'])
            
            image = image.addBands([TDOMMask])

            return image.updateMask(TDOMMask)
            
        shadowSumBands = ['nir','swir1']

        # Get some pixel-wise stats for the time series
        irStdDev = self.fullCollection.select(shadowSumBands).reduce(ee.Reducer.stdDev())
        irMean = self.fullCollection.select(shadowSumBands).reduce(ee.Reducer.mean())

        # Mask out dark dark outliers
        collection_tdom = collection.map(TDOM)

        return collection_tdom

    def addSTDdev(self,collection):
        
        def addSTDdevIndices(img):
            """ Function to add common (and less common) spectral indices to an image.
            Includes the Normalized Difference Spectral Vector from (Angiuli and Trianni, 2014) """
            img = img.addBands(img.normalizedDifference(['green','swir1']).rename(['ND_green_swir1']));  # NDSI, MNDWI
            img = img.addBands(img.normalizedDifference(['nir','red']).rename(['ND_nir_red']));  # NDVI
            img = img.addBands(img.normalizedDifference(['nir','swir2']).rename(['ND_nir_swir2']));  # NBR, MNDVI
            
            return img;       
        
        
        
        blue_stdDev = collection.select(["blue"]).reduce(ee.Reducer.stdDev()).rename(['blue_stdDev'])
        red_stdDev = collection.select(["red"]).reduce(ee.Reducer.stdDev()).rename(['red_stdDev'])
        green_stdDev = collection.select(["green"]).reduce(ee.Reducer.stdDev()).rename(['green_stdDev'])
        nir_stdDev = collection.select(["nir"]).reduce(ee.Reducer.stdDev()).rename(['nir_stdDev'])
        swir1_stdDev = collection.select(["swir1"]).reduce(ee.Reducer.stdDev()).rename(['swir1_stdDev'])
        swir2_stdDev = collection.select(["swir2"]).reduce(ee.Reducer.stdDev()).rename(['swir2_stdDev'])
        
        col = collection.map(addSTDdevIndices)
        
        ND_green_swir1 = col.select(['ND_green_swir1']).reduce(ee.Reducer.stdDev()).rename(['ND_green_swir1_stdDev']);
        ND_nir_red = col.select(['ND_nir_red']).reduce(ee.Reducer.stdDev()).rename(['ND_nir_red_stdDev']);
        ND_nir_swir2 = col.select(['ND_nir_swir2']).reduce(ee.Reducer.stdDev()).rename(['ND_nir_swir2_stdDev']);
        
        stdevBands = ee.Image(blue_stdDev.addBands(red_stdDev).addBands(green_stdDev).addBands(nir_stdDev).addBands(swir1_stdDev).addBands(swir2_stdDev)\
                                .addBands(ND_green_swir1).addBands(ND_nir_red).addBands(ND_nir_swir2))
        
        return stdevBands
                                
        

    def defringe(self,img):
        
        # threshold for defringing landsat5 and 7
        fringeCountThreshold = 279

        k = ee.Kernel.fixed(41, 41, 
                                [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
                                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]]);


        m = ee.Image(img).mask().reduce(ee.Reducer.min())
        sum = m.reduceNeighborhood(ee.Reducer.sum(), k, 'kernel')
        mask = sum.gte(fringeCountThreshold)        
        
        return img.updateMask(mask)
        

    def terrain(self,img):   
        
        
        degree2radian = 0.01745;
        otherBands = img.select(['thermal','date','year','TDOMMask','cloudMask'])
 
        def topoCorr_IC(img):
            
            dem = self.env.dem
            
            
            # Extract image metadata about solar position
            SZ_rad = ee.Image.constant(ee.Number(img.get('SOLAR_ZENITH_ANGLE'))).multiply(degree2radian).clip(img.geometry().buffer(10000)); 
            SA_rad = ee.Image.constant(ee.Number(img.get('SOLAR_AZIMUTH_ANGLE'))).multiply(degree2radian).clip(img.geometry().buffer(10000)); 
            
                
            # Creat terrain layers
            slp = ee.Terrain.slope(dem).clip(img.geometry().buffer(10000));
            slp_rad = ee.Terrain.slope(dem).multiply(degree2radian).clip(img.geometry().buffer(10000));
            asp_rad = ee.Terrain.aspect(dem).multiply(degree2radian).clip(img.geometry().buffer(10000));
  
  
            
            # Calculate the Illumination Condition (IC)
            # slope part of the illumination condition
            cosZ = SZ_rad.cos();
            cosS = slp_rad.cos();
            slope_illumination = cosS.expression("cosZ * cosS", \
                                                {'cosZ': cosZ, 'cosS': cosS.select('slope')});
            
            
            # aspect part of the illumination condition
            sinZ = SZ_rad.sin(); 
            sinS = slp_rad.sin();
            cosAziDiff = (SA_rad.subtract(asp_rad)).cos();
            aspect_illumination = sinZ.expression("sinZ * sinS * cosAziDiff", \
                                           {'sinZ': sinZ, \
                                            'sinS': sinS, \
                                            'cosAziDiff': cosAziDiff});
            
            # full illumination condition (IC)
            ic = slope_illumination.add(aspect_illumination);
            
            

            # Add IC to original image
            img_plus_ic = ee.Image(img.addBands(ic.rename(['IC'])).addBands(cosZ.rename(['cosZ'])).addBands(cosS.rename(['cosS'])).addBands(slp.rename(['slope'])));
            
            return ee.Image(img_plus_ic);
 
        def topoCorr_SCSc(img):
            img_plus_ic = img;
            mask1 = img_plus_ic.select('nir').gt(-0.1);
            mask2 = img_plus_ic.select('slope').gte(5) \
                            .And(img_plus_ic.select('IC').gte(0)) \
                            .And(img_plus_ic.select('nir').gt(-0.1));

            img_plus_ic_mask2 = ee.Image(img_plus_ic.updateMask(mask2));

            bandList = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2']; # Specify Bands to topographically correct
    

            def applyBands(image):
                blue = apply_SCSccorr('blue').select(['blue'])
                green = apply_SCSccorr('green').select(['green'])
                red = apply_SCSccorr('red').select(['red'])
                nir = apply_SCSccorr('nir').select(['nir'])
                swir1 = apply_SCSccorr('swir1').select(['swir1'])
                swir2 = apply_SCSccorr('swir2').select(['swir2'])
                return replace_bands(image, [blue, green, red, nir, swir1, swir2])

            def apply_SCSccorr(band):
                method = 'SCSc';
                        
                out = ee.Image(1).addBands(img_plus_ic_mask2.select('IC', band)).reduceRegion(reducer= ee.Reducer.linearRegression(2,1), \
                                                                       geometry= ee.Geometry(img.geometry().buffer(-5000)), \
                                                                        scale= self.env.terrainScale, \
                                                                        bestEffort =True,
                                                                        maxPixels=1e10)
                                                                        
                
                #out_a = ee.Number(out.get('scale'));
                #out_b = ee.Number(out.get('offset'));
                #out_c = ee.Number(out.get('offset')).divide(ee.Number(out.get('scale')));
                
                
                fit = out.combine({"coefficients": ee.Array([[1],[1]])}, False);

                #Get the coefficients as a nested list, 
                #cast it to an array, and get just the selected column
                out_a = (ee.Array(fit.get('coefficients')).get([0,0]));
                out_b = (ee.Array(fit.get('coefficients')).get([1,0]));
                out_c = out_a.divide(out_b)

                    
                # apply the SCSc correction
                SCSc_output = img_plus_ic_mask2.expression("((image * (cosB * cosZ + cvalue)) / (ic + cvalue))", {
                                                                'image': img_plus_ic_mask2.select([band]),
                                                                'ic': img_plus_ic_mask2.select('IC'),
                                                                'cosB': img_plus_ic_mask2.select('cosS'),
                                                                'cosZ': img_plus_ic_mask2.select('cosZ'),
                                                                'cvalue': out_c });
          
                return ee.Image(SCSc_output);
                                                                      
            #img_SCSccorr = ee.Image([apply_SCSccorr(band) for band in bandList]).addBands(img_plus_ic.select('IC'));
            img_SCSccorr = applyBands(img).select(bandList).addBands(img_plus_ic.select('IC'))
        
            bandList_IC = ee.List([bandList, 'IC']).flatten();
            
            img_SCSccorr = img_SCSccorr.unmask(img_plus_ic.select(bandList_IC)).select(bandList);
            
            return img_SCSccorr.unmask(img_plus_ic.select(bandList)) 
    
        
        
        img = topoCorr_IC(img)
        img = topoCorr_SCSc(img)
        
        return img.addBands(otherBands)

    
 
    def brdf(self,img):   
        
        import sun_angles
        import view_angles

    
        def _apply(image, kvol, kvol0):
            blue = _correct_band(image, 'blue', kvol, kvol0, f_iso=0.0774, f_geo=0.0079, f_vol=0.0372)
            green = _correct_band(image, 'green', kvol, kvol0, f_iso=0.1306, f_geo=0.0178, f_vol=0.0580)
            red = _correct_band(image, 'red', kvol, kvol0, f_iso=0.1690, f_geo=0.0227, f_vol=0.0574)
            nir = _correct_band(image, 'nir', kvol, kvol0, f_iso=0.3093, f_geo=0.0330, f_vol=0.1535)
            swir1 = _correct_band(image, 'swir1', kvol, kvol0, f_iso=0.3430, f_geo=0.0453, f_vol=0.1154)
            swir2 = _correct_band(image, 'swir2', kvol, kvol0, f_iso=0.2658, f_geo=0.0387, f_vol=0.0639)
            return replace_bands(image, [blue, green, red, nir, swir1, swir2])


        def _correct_band(image, band_name, kvol, kvol0, f_iso, f_geo, f_vol):
            """fiso + fvol * kvol + fgeo * kgeo"""
            iso = ee.Image(f_iso)
            geo = ee.Image(f_geo)
            vol = ee.Image(f_vol)
            pred = vol.multiply(kvol).add(geo.multiply(kvol)).add(iso).rename(['pred'])
            pred0 = vol.multiply(kvol0).add(geo.multiply(kvol0)).add(iso).rename(['pred0'])
            cfac = pred0.divide(pred).rename(['cfac'])
            corr = image.select(band_name).multiply(cfac).rename([band_name])
            return corr


        def _kvol(sunAz, sunZen, viewAz, viewZen):
            """Calculate kvol kernel.
            From Lucht et al. 2000
            Phase angle = cos(solar zenith) cos(view zenith) + sin(solar zenith) sin(view zenith) cos(relative azimuth)"""
            
            relative_azimuth = sunAz.subtract(viewAz).rename(['relAz'])
            pa1 = viewZen.cos() \
                .multiply(sunZen.cos())
            pa2 = viewZen.sin() \
                .multiply(sunZen.sin()) \
                .multiply(relative_azimuth.cos())
            phase_angle1 = pa1.add(pa2)
            phase_angle = phase_angle1.acos()
            p1 = ee.Image(PI().divide(2)).subtract(phase_angle)
            p2 = p1.multiply(phase_angle1)
            p3 = p2.add(phase_angle.sin())
            p4 = sunZen.cos().add(viewZen.cos())
            p5 = ee.Image(PI().divide(4))

            kvol = p3.divide(p4).subtract(p5).rename(['kvol'])

            viewZen0 = ee.Image(0)
            pa10 = viewZen0.cos() \
                .multiply(sunZen.cos())
            pa20 = viewZen0.sin() \
                .multiply(sunZen.sin()) \
                .multiply(relative_azimuth.cos())
            phase_angle10 = pa10.add(pa20)
            phase_angle0 = phase_angle10.acos()
            p10 = ee.Image(PI().divide(2)).subtract(phase_angle0)
            p20 = p10.multiply(phase_angle10)
            p30 = p20.add(phase_angle0.sin())
            p40 = sunZen.cos().add(viewZen0.cos())
            p50 = ee.Image(PI().divide(4))

            kvol0 = p30.divide(p40).subtract(p50).rename(['kvol0'])

            return (kvol, kvol0)
         
        date = img.date()
        footprint = determine_footprint(img)
        (sunAz, sunZen) = sun_angles.create(date, footprint)
        (viewAz, viewZen) = view_angles.create(footprint)
        (kvol, kvol0) = _kvol(sunAz, sunZen, viewAz, viewZen)
        return _apply(img, kvol.multiply(PI()), kvol0.multiply(PI()))

    def medoidMosaic(self,collection):
        """ medoid composite with equal weight among indices """
        nImages = ee.ImageCollection(collection).select([0]).count().rename('count')
        bandNames = ee.Image(collection.first()).bandNames()
        otherBands = bandNames.removeAll(self.env.divideBands)

        others = collection.select(otherBands).reduce(ee.Reducer.mean()).rename(otherBands);
        
        collection = collection.select(self.env.divideBands)

        bandNumbers = ee.List.sequence(1,self.env.divideBands.length());

        median = ee.ImageCollection(collection).median()
        
        def subtractmedian(img):
            diff = ee.Image(img).subtract(median).pow(ee.Image.constant(2));
            return diff.reduce('sum').addBands(img);
        
        medoid = collection.map(subtractmedian)
  
        medoid = ee.ImageCollection(medoid).reduce(ee.Reducer.min(self.env.divideBands.length().add(1))).select(bandNumbers,self.env.divideBands);
  
        return medoid.addBands(others).addBands(nImages);   


    def medoidMosaicPercentiles(self,inCollection,p):
        ' calculate the medoid of a percentile'
        
        inCollection = inCollection.select(self.env.medoidBands)
        
        p1 = p
        p2 = 100 -p
        
        med1 = self.medoidPercentiles(inCollection,p1).select(["green","nir"])
        med2 = self.medoidPercentiles(inCollection,p2).select(["blue","red","swir1","swir2"])
  
        medoidP = self.renameBands(ee.Image(med1).addBands(med2),str("p")+str(p))
        return medoidP
  

    def medoidPercentiles(self,inCollection,p):

        # Find band names in first image
        bandNumbers = ee.List.sequence(1,self.env.medoidBands.length());

        # Find the median
        percentile = inCollection.select(self.env.medoidBands).reduce(ee.Reducer.percentile([p]));
        
        def subtractPercentile(img):
            diff = ee.Image(img).subtract(percentile).pow(ee.Image.constant(2));
            return diff.reduce('sum').addBands(img);
        
        percentile = inCollection.map(subtractPercentile)
        
        percentile = ee.ImageCollection(percentile).reduce(ee.Reducer.min(self.env.medoidBands.length().add(1))).select(bandNumbers,self.env.medoidBands);
  
        return percentile;


    def renameBands(self,image,prefix):
        'rename bands with prefix'
        
        bandnames = image.bandNames();

        def mapBands(band):
            band = ee.String(prefix).cat('_').cat(band);
            return band;
                
        bandnames = bandnames.map(mapBands)
        
        image = image.rename(bandnames);

        return image;

    def setMetaData(self,img):

        img = ee.Image(img).set({'regionName': str(self.env.regionName),
                                 'system:time_start':ee.Date(self.env.startDate).millis(),
                                 'compositingMethod':'medoid',
                                 'toaOrSR':'SR',
                                 'epsg':str(self.env.epsg),
                                 'exportScale':str(self.env.exportScale),
                                 'shadowSumThresh':str(self.env.shadowSumThresh),
                                 'maskSR':str(self.env.maskSR),
                                 'cloudMask':str(self.env.cloudMask),
                                 'hazeMask':str(self.env.hazeMask),
                                 'shadowMask':str(self.env.shadowMask),
                                 'brdfCorrect':str(self.env.brdfCorrect),
                                 'terrainCorrection':str(self.env.terrainCorrection),
                                 'contractPixels':str(self.env.contractPixels),
                                 'dilatePixels':str(self.env.dilatePixels),
                                 'metadataCloudCoverMax':str(self.env.metadataCloudCoverMax),
                                 'hazeThresh':str(self.env.hazeThresh),
                                 'terrainScale':str(self.env.terrainScale)})

        return img
    def exportMap(self,img,studyArea):

        geom  = studyArea.getInfo();
        sd = str(self.env.startDate.getRelative('day','year').getInfo()).zfill(3);
        ed = str(self.env.endDate.getRelative('day','year').getInfo()).zfill(3);
        year = str(self.env.startDate.get('year').getInfo());
        regionName = self.env.regionName.replace(" ",'_') + "_"

        task_ordered= ee.batch.Export.image.toAsset(image=img, 
                                  description = self.env.name + regionName + year + sd + ed, 
                                  assetId= self.env.assetId + self.env.name + regionName + year + sd + ed,
                                  region=geom['coordinates'], 
                                  maxPixels=1e13,
                                  crs=self.env.epsg,
                                  scale=self.env.exportScale)
    
        task_ordered.start()
        print(self.env.assetId + self.env.name + regionName + year + sd + ed)
        
#def composite(aoi,year):
#   img = ee.Image(functions().getLandsat(aoi,year))
#   return img
    

if __name__ == "__main__":
    #def composite(aoi,year):

    ee.Initialize()
    for i in range(0,10):
        year = 2009 + i
 
        regionName = 'AMAZONIA NOROCCIDENTAL'
        studyArea =  ee.FeatureCollection("projects/Sacha/AncillaryData/StudyRegions/Ecuador_EcoRegions_Complete")
        studyArea = studyArea.filterMetadata('PROVINCIA','equals',regionName).geometry().bounds()
        
        print(functions().getLandsat(studyArea,year,regionName))

