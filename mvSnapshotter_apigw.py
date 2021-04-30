#!/usr/bin/python3
'''
mvSnapshotter_apigw
Author: Ryan LaTorre <ryan@latorre.ca>
Description: HTTP API to Fetch snapshot(s) from Meraki MV cameras and post to Webex
Learn more at http://github.com/rylatorr/mvSnapshotter
'''

from flask import Flask, jsonify, abort, request, make_response
import mvSnapshotter
import meraki
import json

app = Flask(__name__)

@app.before_first_request
def activate_job():
	mvSnapshotter.startLogging()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
	return ('Hello world! MV Snapshotter API Gateway app. You requested path: %s' % path)

@app.route('/api/v1.0/getSnapshot', methods=['GET', 'POST'])
def getSnapshot():

	videoLinks = []
	snapshotLinks = []
	configDict = mvSnapshotter.readConfigVars()
	dashboard = meraki.DashboardAPI(
		configDict['meraki']['apikey'],
		output_log=False
	)

	if request.method == 'POST':
		if not request.json or not 'apikey' in request.json:
			abort(400)
		postdata = request.json
	else:
		postdata = request.args

	#print(f'Debug: postdata is: {json.dumps(postdata)}')
	#print(f"Debug: configured apikey is: {configDict['apigw']['apigwtoken']}")

	if postdata['apikey'] != configDict['apigw']['apigwtoken']:
		return jsonify({'Error': 'Invalid API Key'})
		abort(400)

	mvSerials = [configDict['meraki']['mvserials']]
	if 'mvSerial' in postdata:
		mvSerials = postdata['mvSerial'].split(',')

	print(f'Debug: mvSerials list is: {mvSerials}')
	for idx, val in enumerate(mvSerials):
		mvSerial = mvSerials[idx]
		validity = mvSnapshotter.validateSerial(mvSerial)
		if validity == False:
			print(f'Supplied serial number {mvSerial} is invalid, skipping. ')
			continue

		if 'webexRoom' in postdata:
			configDict['webex']['roomname'] = postdata['webexRoom']

		# Obtain link to live video and generate a snapshot
		videoLink, snapshotLink = mvSnapshotter.getSnapshot(configDict, dashboard, mvSerial)
		videoLinks.append(videoLink)
		snapshotLinks.append(snapshotLink)

	# Post a message to Webex
	mvSnapshotter.postSnapshot(configDict, videoLinks, snapshotLinks)

	return json.dumps("Success"), 200, {'Content-Type': 'application/json; charset=utf-8'}

@app.errorhandler(404)
def not_found(error):
	return make_response(jsonify({'error': 'Not found'}), 404)

if __name__ == '__main__':
	configDict = mvSnapshotter.readConfigVars()
	app.run(debug=True,host=configDict['apigw']['serverip'],port=configDict['apigw']['serverport'])


