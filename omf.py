#!/bin/python

# third party modules
import flask, werkzeug, os, multiprocessing, json, time, threading, datetime
# our modules
import analysis, feeder, reports, studies, milToGridlab, storage
# import logging_system

app = flask.Flask(__name__)

store = storage.Filestore('data')

class backgroundProc(multiprocessing.Process):
	def __init__(self, backFun, funArgs):
		self.name = 'omfWorkerProc'
		self.backFun = backFun
		self.funArgs = funArgs
		self.myPid = os.getpid()
		multiprocessing.Process.__init__(self)
	def run(self):
		self.backFun(*self.funArgs)

class background_thread(threading.Thread):
    def __init__(self, backFun, funArgs):
        threading.Thread.__init__(self)
        self.backFun = backFun
        self.funArgs = funArgs
         
    def run(self):
        self.backFun(*self.funArgs)

###################################################
# VIEWS
###################################################

@app.route('/')
def root():
	browser = flask.request.user_agent.browser
	metadatas = [store.get('Analysis', x) for x in store.listAll('Analysis')]
	feeders = store.listAll('Feeder')
	conversions = store.listAll('Conversion')
	if browser == 'msie':
		return 'The OMF currently must be accessed by Chrome, Firefox or Safari.'
	else:
		return flask.render_template('home.html', metadatas=metadatas, feeders=feeders, conversions=conversions)

@app.route('/newAnalysis/')
@app.route('/newAnalysis/<analysisName>')
def newAnalysis(analysisName=None):
	# Get some prereq data:
	tmy2s = store.listAll('Weather')
	feeders = store.listAll('Feeder')
	analyses = store.listAll('Analysis')
	reportTemplates = reports.__templates__
	studyTemplates = studies.__templates__
	studyRendered = {}
	for study in studyTemplates:
		studyRendered[study] = str(flask.render_template_string(studyTemplates[study], tmy2s=tmy2s, feeders=feeders))
	# If we aren't specifying an existing name, just make a blank analysis:
	if analysisName is None or analysisName not in analyses:
		existingStudies = None
		existingReports = None
		analysisMd = None
	# If we specified an analysis, get the studies, reports and analysisMd:
	else:
		thisAnalysis = store.get('Analysis', analysisName)
		analysisMd = json.dumps({key:thisAnalysis[key] for key in thisAnalysis if type(thisAnalysis[key]) is not list})
		existingReports = json.dumps(thisAnalysis['reports'])
		#TODO: remove analysis name from study names. Dang DB keys.
		existingStudies = json.dumps([store.get('Study', analysisName + '---' + studyName) for studyName in thisAnalysis['studyNames']])
	return flask.render_template('newAnalysis.html', studyTemplates=studyRendered, reportTemplates=reportTemplates, existingStudies=existingStudies, existingReports=existingReports, analysisMd=analysisMd)

@app.route('/viewReports/<analysisName>')
def viewReports(analysisName):
	if not store.exists('Analysis', analysisName):
		return flask.redirect(flask.url_for('root'))
	thisAnalysis = analysis.Analysis(store.get('Analysis',analysisName))
	studyList = []
	for studyName in thisAnalysis.studyNames:
		studyData = store.get('Study', thisAnalysis.name + '---' + studyName)
		moduleRef = getattr(studies, studyData['studyType'])
		classRef =  getattr(moduleRef, studyData['studyType'].capitalize())
		studyList.append(classRef(studyData))
	reportList = thisAnalysis.generateReportHtml(studyList)
	return flask.render_template('viewReports.html', analysisName=analysisName, reportList=reportList)

@app.route('/feeder/<feederName>')
def feederGet(feederName):
	return flask.render_template('gridEdit.html', feederName=feederName, anaFeeder=False)

@app.route('/analysisFeeder/<analysis>/<study>')
def analysisFeeder(analysis, study):
	return flask.render_template('gridEdit.html', feederName=analysis+'---'+study, anaFeeder=True)


####################################################
# API FUNCTIONS
####################################################

@app.route('/uniqueName/<name>')
def uniqueName(name):
	return json.dumps(name not in store.listAll('Analysis'))

@app.route('/run/', methods=['POST'])
@app.route('/reRun/', methods=['POST'])
def run():
	anaName = flask.request.form.get('analysisName')
	thisAnalysis = analysis.Analysis(store.get('Analysis', anaName))
	thisAnalysis.status = 'running'
	store.put('Analysis', anaName, thisAnalysis.__dict__)
	runProc = backgroundProc(analysisRun, [thisAnalysis, store])
	runProc.start()
	return flask.render_template('metadata.html', md=thisAnalysis.__dict__)

# Helper function that runs an analyses in a new process.
def analysisRun(anaObject, store):
	#TODO: support non-Gridlab studies.
	studyList = [studies.gridlabd.Gridlabd(dict(store.get('Study', anaObject.name + '---' + studyName).items() + {'name':studyName,'analysisName':anaObject.name}.items())) for studyName in anaObject.studyNames]
	anaObject.run(studyList)
	store.put('Analysis', anaObject.name, anaObject.__dict__)
	for study in studyList:
		store.put('Study', study.analysisName + '---' + study.name, study.__dict__)

@app.route('/delete/', methods=['POST'])
def delete():
	anaName = flask.request.form['analysisName']
	# Delete studies.
	childStudies = [x for x in store.listAll('Study') if x.startswith(anaName + '---')]
	for study in childStudies:
		store.delete('Study', study)
	# Delete analysis.
	store.delete('Analysis', anaName)
	return flask.redirect(flask.url_for('root'))

@app.route('/saveAnalysis/', methods=['POST'])
def saveAnalysis():
	pData = json.loads(flask.request.form.to_dict()['json'])
	#TODO: unique string join.
	def uniqJoin(stringList):
		return ', '.join(set(stringList))
	analysisData = {'status':'preRun',
					'sourceFeeder':uniqJoin([stud['feederName'] for stud in pData['studies']]),
					'climate':uniqJoin([stud['tmy2name'] for stud in pData['studies']]),
					'created':str(datetime.datetime.now()),
					'simStartDate':pData['simStartDate'],
					'simLength':pData['simLength'],
					'simLengthUnits':pData['simLengthUnits'],
					'runTime':'',
					'reports':pData['reports'],
					'studyNames':[stud['studyName'] for stud in pData['studies']] }
	store.put('Analysis', pData['analysisName'], analysisData)
	for study in pData['studies']:
		if study['studyType'] == 'gridlabd':
			studyData = {	'studyType':'gridlabd',
							'simLength':pData['simLength'],
							'simLengthUnits':pData['simLengthUnits'],
							'simStartDate':pData['simStartDate'],
							'sourceFeeder':study['feederName'],
							'climate':study['tmy2name'],
							'analysisName':pData['analysisName'] }
			studyFeeder = store.get('Feeder', study['feederName'])
			studyFeeder['attachments']['climate.tmy2'] = store.get('Weather', study['tmy2name']+'.tmy2', raw=True)
			studyData = {'inputJson':studyFeeder,'outputJson':{}}
			studyObj = studies.gridlabd.Gridlabd(studyData, new=True)
			store.put('Study', pData['analysisName'] + '---' + study['studyName'], studyObj.__dict__)
		elif study['studyType'] == 'XXX':
			#TODO: implement me.
			pass
	return flask.redirect(flask.url_for('root'))

@app.route('/terminate/', methods=['POST'])
def terminate():
	anaName = flask.request.form['analysisName']
	for runDir in os.listdir('running'):
		if runDir.startswith(anaName + '---'):
			try:
				with open('running/' + runDir + '/PID.txt','r') as pidFile:
					os.kill(int(pidFile.read()), 15)
			except:
				pass
	return flask.redirect(flask.url_for('root'))

@app.route('/feederData/<anaFeeder>/<feederName>.json')
def feederData(anaFeeder, feederName):
	if anaFeeder == 'True':
		#TODO: fix this.
		data = store.get('Study', feederName)['inputJson']
		del data['attachments']
		return json.dumps(data)
	else:
		return json.dumps(store.get('Feeder', feederName))

@app.route('/getComponents/')
def getComponents():
	components = {name:store.get('Component', name) for name in store.listAll('Component')}
	return json.dumps(components, indent=4)

@app.route('/saveFeeder/', methods=['POST'])
def saveFeeder():
	postObject = flask.request.form.to_dict()
	store.put('Feeder', str(postObject['name']), json.loads(postObject['feederObjectJson']))
	return flask.redirect(flask.url_for('root') + '#feeders')

@app.route('/runStatus')
def runStatus():
	name = flask.request.args.get('name')
	md = store.get('Analysis', name)
	if md['status'] != 'running':
		return flask.render_template('metadata.html', md=md)
	else:
		return flask.Response("waiting", content_type="text/plain")

@app.route('/milsoftImport/', methods=['POST'])
def milsoftImport():
	feederName = str(flask.request.form.to_dict()['feederName'])
	stdName = ''
	seqName = ''
	allFiles = flask.request.files
	for f in allFiles:
		fName = werkzeug.secure_filename(allFiles[f].filename)
		if fName.endswith('.std'): stdName = fName
		elif fName.endswith('.seq'): seqName = fName
		allFiles[f].save('./uploads/' + fName)
	runProc = backgroundProc(milImportAndConvert, [store, feederName, stdName, seqName])
	runProc.start()
	time.sleep(1)
	return flask.redirect(flask.url_for('root') + '#feeders')

def milImportAndConvert(store, feederName, stdName, seqName):
	store.put('Conversion', feederName, {'data':'none'})
	newFeeder = {'links':[],'hiddenLinks':[],'nodes':[],'hiddenNodes':[],'layoutVars':{'theta':'0.8','gravity':'0.01','friction':'0.9','linkStrength':'5'}}
	newFeeder['tree'] = milToGridlab.convert('./uploads/' + stdName, './uploads/' + seqName)
	with open('./schedules.glm','r') as schedFile:
		newFeeder['attachments'] = {'schedules.glm':schedFile.read()}
	store.put('Feeder', feederName, newFeeder)
	store.delete('Conversion', feederName)

# This will run on all interface IPs.
if __name__ == '__main__':
	# thread_logging = background_thread(logging_system.logging_system(app).logging_run, (app,))
	# thread_logging.start()
	app.run(host='0.0.0.0', debug=True, port=5001, threaded=True)
