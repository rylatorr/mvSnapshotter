'''
mvSnapshotter
Author: Ryan LaTorre <ryan@latorre.ca>
Description: Fetch snapshot(s) from Meraki MV cameras and post to Webex
Learn more at http://github.com/rylatorr/mvSnapshotter
'''

import sys
import os
import logging
import configparser
import meraki
import json
import requests
from datetime import datetime, timedelta
import time
import re

logger = logging.getLogger()

def print_help():
    lines = READ_ME.split('\n')
    for line in lines:
        print('# {0}'.format(line))

def startLogging():
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(os.path.join(os.path.dirname(__file__), 'mvSnapshotter.log'))
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return

def configToDict(config):
    # Converts a ConfigParser object into a dictionary.
    # The resulting dictionary has sections as keys which point to a dict of the
    # sections options as key => value pairs.
    configDict = {}
    for section in config.sections():
        configDict[section] = {}
        for key, val in config.items(section):
            configDict[section][key] = val
    return configDict

def readConfigVars():
    config_file = os.path.join(os.path.dirname(__file__), 'config/config.ini')
    config = configparser.ConfigParser()
    try:
        config.read(config_file)
        configDict = configToDict(config)
        configDict['meraki']['apikey']
        configDict['meraki']['orgid']
        configDict['meraki']['mvserial']
        configDict['webex']['webexbottoken']
        configDict['webex']['roomname']
        configDict['webex']['msgprefix']
        configDict['apigw']['serverip']
        configDict['apigw']['serverport']
        configDict['apigw']['apigwtoken']

    except:
        print('Missing config items or file!')
        sys.exit(2)

    logger.info('Finished reading config vars.')

    configDict['meraki']['mvserials'] = (configDict['meraki']['mvserial']).split(',')
    # Check the format of the serial numbers in config.ini
    numCams = len(configDict['meraki']['mvserials'])
    for i in range(numCams):
        validity = validateSerial((configDict['meraki']['mvserials'])[i])
    if validity == False:
        print(f"Supplied serial number {(configDict['meraki']['mvserials'])[i]} is invalid, exiting.")
        exit()

    return configDict

# Some limited sanity checking of the supplied serial number
def validateSerial(input_string):
    regex = re.compile('Q[0-9A-Z]{3}-[0-9A-Z]{4}-[0-9A-Z]{4}\Z', re.I)
    match = regex.match(str(input_string.upper()))
    return bool(match)

# Get Webex bot's rooms
def getWebexBotRooms(session, headers):
    response = session.get('https://webexapis.com/v1/rooms', headers=headers)
    return response.json()['items']

# Get room ID for desired space
def getWebexRoomId(session, headers, webexNotificationRoomName):
    rooms = getWebexBotRooms(session, headers)
    for room in rooms:
        if room["title"].startswith(webexNotificationRoomName):
            webexRoomId = room["id"]
            return webexRoomId
    return False

# Send a message in Webex
# This function unused, it's essentially the same as postSnapshot, but doesn't include
# posting the image directly to Webex.
def postWebexMessage(session, headers, payload, message):
    payload['markdown'] = message
    session.post('https://webexapis.com/v1/messages/',
                 headers=headers,
                 data=json.dumps(payload))

# Send a message with file attachment in Webex Teams
def postWebexMessageWithAttach(session, headers, payload, message, file_url):
    payload['file'] = file_url
    postWebexMessage(session, headers, payload, message)

def getSnapshot(configDict, dashboard, mvSerial):
    # Get link to video feed
    # Note the snapshot API seems to interpret the time as SF/Pacific time so I've subtracted 3 hours to compensate
    # from Eastern time. Debug confirmed that I was sending the ISO timestamp correctly, but the epoch time returned
    # in the URL is always 3 hours ahead.
    timestamp = (datetime.now() - timedelta(seconds=15) - timedelta(hours=3)).isoformat()
    videoLinkResp = dashboard.camera.getDeviceCameraVideoLink(mvSerial, timestamp=timestamp)
    videoLink = videoLinkResp['url']
    print(f"Link to camera video feed is: {videoLink}")

    # Generate a snapshot
    snapshotLinkResp = dashboard.camera.generateDeviceCameraSnapshot(mvSerial)
    snapshotLink = snapshotLinkResp['url']
    print(f"Link to snapshot is: {snapshotLink}")

    return videoLink, snapshotLink

# This function presently unused, essentially same as postSnapshot (below) but without embedding the image
def postNotification(configDict, videoLinks, snapshotLinks):
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {configDict['webex']['webexbottoken']}"
    }
    session = requests.Session()
    webexRoomId = getWebexRoomId(session, headers, configDict['webex']['roomname'])
    payload = {'roomId': webexRoomId}
    numLinks = len(videoLinks)
    for i in range(numLinks):
        message = f"{configDict['webex']['msgprefix']}:  {datetime.now().strftime('%a %b %d, %I:%M %p')}. " \
                  f"[Snapshot]({snapshotLinks[i]}). [Video on Dashboard]({videoLinks[i]})."
        postWebexMessage(session, headers, payload, message)
    return

def postSnapshot(configDict, videoLinks, snapshotLinks):
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {configDict['webex']['webexbottoken']}"
    }
    session = requests.Session()
    webexRoomId = getWebexRoomId(session, headers, configDict['webex']['roomname'])
    payload = {'roomId': webexRoomId}
    # Wait a few seconds to ensure cameras to upload snapshots to links
    time.sleep(4)
    numLinks = len(videoLinks)
    for i in range(numLinks):
        message = f"{configDict['webex']['msgprefix']}:  {datetime.now().strftime('%a %b %d, %I:%M %p')}. " \
                  f"[Snapshot]({snapshotLinks[i]}). [Video on Dashboard]({videoLinks[i]})."
        postWebexMessageWithAttach(session, headers, payload, message, snapshotLinks[i])
    return

def setupSession():
    startLogging()
    configDict = readConfigVars()

    # Instantiate a Meraki dashboard API session
    dashboard = meraki.DashboardAPI(
        configDict['meraki']['apikey'],
        output_log=False
    )

    return configDict, dashboard

def main(args):
    configDict, dashboard = setupSession()
    videoLinks = []
    snapshotLinks = []

    #print(f"Debug: mvSerials list is: {configDict['meraki']['mvserials']}")
    for idx, val in enumerate(configDict['meraki']['mvserials']):
        mvSerial = configDict['meraki']['mvserials'][idx]
        validity = validateSerial(mvSerial)
        if validity == False:
            print(f'Supplied serial number {mvSerial} is invalid, skipping. ')
            continue

        # Obtain link to live video and generate a snapshot
        videoLink, snapshotLink = getSnapshot(configDict, dashboard, mvSerial)
        videoLinks.append(videoLink)
        snapshotLinks.append(snapshotLink)

        # Post a message to Webex
        postSnapshot(configDict, videoLinks, snapshotLinks)

    return


if __name__ == "__main__":
    main(sys.argv[1:])
