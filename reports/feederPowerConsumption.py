﻿#!/usr/bin/env python

import os
import re
import math
import __util__

# The config template, when inserted, will have the string REMOVALID replaced with a unique GUID.
configHtmlTemplate = "<div id='REMOVALID' class='content feederPowerConsumption'><a href='javascript:removeStudyReport(REMOVALID)' class='removeStudyReport'>x</a><table class='reportOptions'><tr><td>Report Name</td><td class='reportName'>feederPowerConsumption</td></tr></table></div>"

def outputHtml(analysisName):
	# Put the title in:
	outputBuffer = "<p class='reportTitle'>Power Consumption From Transmission System</p><div id='feederPowerConsumptionReport' class='tightContent'>"
	# Variables for the whole analysis:
	pathPrefix = 'analyses/' + analysisName + '/studies/'
	studies = os.listdir(pathPrefix)
	# Figure out what the time interval was:
	with open(pathPrefix + studies[0] + '/main.glm') as testGlm:
		glmContent = testGlm.read()
		intervalText = re.findall('interval\s+(\d+)', glmContent)
		if [] != intervalText:
			interval = float(intervalText[0])
		else:
			interval = 0.0
	# Collect the power stats:
	powerTimeSeries = []
	energyTotals = [['Study Name','Energy Used']]
	for study in studies:
		powerToAdd = []
		swingFileNames = [x for x in os.listdir(pathPrefix + study) if x.startswith('SwingKids_') and x.endswith('.csv')]
		for swingFile in swingFileNames:
			fullArray = __util__.csvToArray(pathPrefix + study + '/' + swingFile)
			fullArray[0] = ['', str(study)]
			fullArray[1:] = [[row[0],(-1 if row[1]<0 else 1)*math.sqrt(row[1]**2+row[2]**2)/1000] for row in fullArray[1:]]
			if [] == powerToAdd:
				powerToAdd = fullArray
			else: 
				for rowNum in xrange(len(fullArray)):
					powerToAdd[rowNum][1] = powerToAdd[rowNum][1] + fullArray[rowNum][1]
		if [] == powerTimeSeries:
			powerTimeSeries = powerToAdd
		else:
			powerTimeSeries = [powerTimeSeries[rowNum] + [powerToAdd[rowNum][1]] for rowNum in xrange(len(powerTimeSeries))]
	# Collect the energy stats
	def totalEnergy(studyName, isRelevantFile, isSinglePhaseNotThree):
		def sumEnergy(lossOrGenFilePath, isSinglePhaseNotThree):
			fullData = __util__.csvToArray(lossOrGenFilePath)
			if isSinglePhaseNotThree:
				apparentPower = [['Datetime','AppPower(kW)']] + [[r[0],__util__.pyth(r[1],r[2])/1000] for r in fullData[1:]]
			else:
				apparentPower = [['Datetime','AppPower(kW)']] + [[r[0],(__util__.pyth(r[1],r[2])+__util__.pyth(r[3],r[4])+__util__.pyth(r[5],r[6]))/1000] for r in fullData[1:]]
			totalEnergyKwh = sum([interval * row[1] / 3600.0 for row in apparentPower[1:]])
			return totalEnergyKwh
		studyPrefix = pathPrefix + studyName + '/'
		lossesFiles = [x for x in os.listdir(studyPrefix) if isRelevantFile(x)]
		energies = map(lambda x:sumEnergy(studyPrefix + x, isSinglePhaseNotThree), lossesFiles)
		return sum(energies)
	losses = map(lambda x:totalEnergy(x, lambda y:y in ['TriplexLosses.csv','OverheadLosses.csv','UndergroundLosses.csv','TransformerLosses.csv'], False), studies)
	distGen = map(lambda x:totalEnergy(x, lambda y:y.startswith('Inverter_'), False), studies)
	substation = map(lambda x:totalEnergy(x, lambda y:y.startswith('SwingKids_'), True), studies)
	energyMatrix = [['#'] + map(str,studies),
					['DG'] + distGen,
					['Loads'] + __util__.vecSum(substation, distGen, [x*-1 for x in losses]),
					['Losses'] + losses]
	energyTotals = [list(r) for r in zip(*energyMatrix)]
	# Add the power time series graph:
	powerGraphOptions = "{vAxis:{title:'Power (kW)'}, chartArea:{left:60, top:20, width:'90%', height:'80%'}, hAxis:{title:'Time', textPosition:'none'}, colors:['red','darkred','salmon'], legend:{position:'top'}}"
	outputBuffer += "<div id='powerTimeSeries'><script>drawLineChart(" + str(powerTimeSeries) + ",'powerTimeSeries'," + powerGraphOptions + ")</script></div>"
	# Add the energy graph:
	energyGraphOptions = "{chartArea:{left:60,top:20,width:'90%', height:'80%'}, vAxis:{title:'Energy (kWh)'}, isStacked:true, series:{0:{type:'bars'}, 1:{type:'steppedArea'}, 2:{type:'steppedArea'}},colors:['seagreen','darkorange','orangered'], legend:'none', areaOpacity:0.7, bar:{groupWidth:'30%'}}"
	outputBuffer += "<div id='energyBalance'><script>drawComboChart(" + str(energyTotals) + ",'energyBalance'," + energyGraphOptions + ")</script></div>"
	return outputBuffer + "</div>"

def modifyStudy(analysisName):
	pass
	#TODO: implement if needed.

def main():
	# Tests go here.
	pass

if __name__ == '__main__':
	main()