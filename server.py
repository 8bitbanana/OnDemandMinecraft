from flask import Flask, render_template, request, jsonify, redirect, session
from werkzeug.security import check_password_hash
from configuration import Config, AWSConfig, DOConfig
import boto3
import time
import requests
import functools
import sys

CLIENT_TTL_HOURS = 1

mc_statuses = {
    None:None,
    0:"stopped",
    1:"starting-blank",
    2:"starting-launching",
    3:"starting-preparing",
    4:"running",
    5:"stopped-ssh",
    6:"stopping",
    -1:"unknown"
}

app = Flask(__name__)
app.secret_key = Config.FLASK_SECRET
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Strict"
)

class AWSConnection:
    def __init__(self):
        self.client = None
        self.client_ttlend = None
        self.isOn = False

    def getClient(self):
        if self.client == None or self.client_ttlend > time.time():
            self.client = boto3.client(
                'ec2',
                aws_access_key_id=AWSConfig.ACCESS_KEY,
                aws_secret_access_key=AWSConfig.SECRET_KEY,
                region_name=AWSConfig.ec2_region
            )
            self.isOn = True
            self.client_ttlend = time.time() + 3600 * CLIENT_TTL_HOURS
        return self.client

    def startServer(self):
        client = self.getClient()
        instanceIds = [AWSConfig.INSTANCE_ID]
        response = client.start_instances(InstanceIds = instanceIds)
        startingInstance = response['StartingInstances'][0]
        currentState = startingInstance['CurrentState']['Name']
        previousState = startingInstance['PreviousState']['Name']
        if currentState == "pending" and previousState == "stopped":
            workingAsExpected = True
        else:
            workingAsExpected = False
        return workingAsExpected, previousState, currentState

    def stopServer(self):
        client = self.getClient()
        instanceIds = [AWSConfig.INSTANCE_ID]
        response = client.stop_instances(InstanceIds = instanceIds)
        stoppingInstance = response['StoppingInstances'][0]
        currentState = stoppingInstance['CurrentState']['Name']
        previousState = stoppingInstance['PreviousState']['Name']
        if currentState == "stopping" and previousState == "running":
            workingAsExpected = True
        else:
            workingAsExpected = False
        return workingAsExpected, previousState, currentState

    def getServerState(self):
        client = self.getClient()
        if client == None:
            return None, None
        instanceIds = [AWSConfig.INSTANCE_ID]
        response = client.describe_instances(InstanceIds = instanceIds)
        reservations = response['Reservations']
        reservation = reservations[0]
        instances = reservation['Instances']
        if len(instances) > 0:
            instance = instances[0]
            state = instance['State']['Name']
            if state == "running":
                serverip = instance['PublicIpAddress']
            else:
                serverip = None
        else:
            return None, None
        return state, serverip

class DigitalOceanConnection:
    def __init__(self):
        self.headers = {"Content-Type": "application/json", "Authorization": f"Bearer {DOConfig.AUTH_TOKEN}"} 
        self.isOn = False
        self.lastStartAction = None
        self.lastStopAction = None

    def getActionStatus(self, actionID):
        r = requests.get(
            f"https://api.digitalocean.com/v2/actions/{actionID}",
            headers=self.headers
        )
        if r.status_code == 200:
            return r.json()['action']['status']  == "in-progress"
        else:
            return False

    def sendAction(self, action):
        r = requests.post(
            f"https://api.digitalocean.com/v2/droplets/{DOConfig.DROPLET_ID}/actions",
            json={'type':action},
            headers=self.headers
        )
        return r.status_code, r.json()

    def startServer(self):
        status, response = self.sendAction("power_on")
        if status != 201:
            return False
        if response['action']['status'] != 'in-progress':
            return False
        self.lastStartAction = response['action']['id']
        return True

    def stopServer(self):
        status, response = self.sendAction("shutdown")
        if status != 201:
            return False
        if response['action']['status'] != 'in-progress':
            return False
        self.lastStopAction = response['action']['id']
        return True

    # stopped
    # starting
    # running
    # stopping
    def getServerState(self):
        r = requests.get(f"https://api.digitalocean.com/v2/droplets/{DOConfig.DROPLET_ID}", headers=self.headers)
        if r.status_code != 200:
            return None, None
        response = r.json()['droplet']
        on_statuses = {'active'}
        off_statuses = {'new', 'off', 'archive'}
        status = None
        if response['status'] in on_statuses:
            status = "running"
            if self.getActionStatus(self.lastStopAction):
                status = "stopping"
        elif response['status'] in off_statuses:
            status = "stopped"
            if self.getActionStatus(self.lastStartAction):
                status = "starting"
        else:
            return None, None
        serverip = None
        try:
            networks = response['networks']['v4']
            for network in networks:
                if network['type'] == 'public':
                    serverip = network['ip_address']
        except KeyError:
            serverip = None
        return status, serverip


if __name__ == "__main__":
    do = DigitalOceanConnection()
    print(do.getServerState())
    sys.exit(0)

conn = AWSConnection()

def needsAuth(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("auth"):
            return func(*args, **kwargs)
        else:
            return ("", 403)
    return wrapper

REPEAT_TIMEOUT = 2
repeat_dict = {}
def noRepeats(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # if current time is before time listed
        if func.__name__ in repeat_dict and time.time() < repeat_dict[func.__name__]:
            return ("Function already called", 400)
        repeat_dict[func.__name__] = time.time() + REPEAT_TIMEOUT
        return func(*args, **kwargs)
    wrapper.__name = func.__name__
    return wrapper

@noRepeats
def repeatTest():
    return True

@app.route("/callback/stopmainserver", methods=['POST'])
def stopMainServer():
    mainState, serverip = conn.getServerState()
    if request.remote_addr != serverip:
        return ("", 403)
    if mainState != "running":
        return ("", 400)
    response = {}
    response['success'],response['previousState'], response['currentState'] = conn.stopServer()
    print(response)
    return jsonify(response)

@app.route("/startserver", methods=['POST'])
@needsAuth
@noRepeats
def startMainServer():
    response = {}
    response['success'],response['previousState'], response['currentState'] = conn.startServer()
    return jsonify(response)

@app.route("/startmcserver", methods=['POST'])
@needsAuth
@noRepeats
def startMcServer():
    mainState, serverip = conn.getServerState()
    if mainState != "running":
        return ("Main Server isn't running", 400)
    try:
        r = requests.post(f"http://{serverip}/api/serverstart", timeout=3)
        if r.status_code != 201:
            return (f"Host API Returned {r.status_code} - {r.text}", 500)
    except requests.exceptions.RequestException:
        return ("Host API Didn't respond", 500)
    return ("", 201)

@app.route("/login", methods=['POST'])
def login():
    if check_password_hash(Config.SERVER_PASSWORD_HASH, request.form['password']):
        session['auth'] = True
        session.permanent = True
    return redirect("/")

@app.route("/serverstatus", methods=['GET'])
@needsAuth
def getServerStatus():
    mainState, serverip = conn.getServerState()
    minecraftServerState = None
    playerReport = None
    sshConnected = False
    if mainState == "running":
        try:
            r = requests.get(f"http://{serverip}/api/serverstatus", timeout=3)
            minecraftServerState = r.json()['status']
            playerReport = r.json()['players']
            playerReport = {k: playerReport[k] for k in sorted(playerReport.keys())}
            sshConnected = r.json()['ssh']
        except requests.exceptions.RequestException:
            minecraftServerState = None
        except ValueError:
            minecraftServerState = None
    if serverip:
        with open("serverip", "w") as f:
            f.write(serverip)
    return jsonify({
        "main":mainState,
        "mc":minecraftServerState,
        "ip":serverip,
        "players":playerReport,
        "ssh":sshConnected
    })

@app.route("/status")
@needsAuth
def statuspage():
    return render_template("status.html")

@app.route('/')
def index():
    if session.get('auth'):
        return render_template("status.html")
    else:
        return render_template("index.html")

#if __name__ == "__main__":
    #app.run()
