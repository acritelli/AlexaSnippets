from __future__ import print_function
from flask import Flask, render_template
from flask_ask import Ask, statement, question, session
from xml.etree import ElementTree
import requests, logging, time, json, threading, subprocess
from threading import Thread
from config import *

#TODO: real logging

def DO_build_server(api_token, name, ssh_key_id, region="nyc1", size="512mb", image="centos-6-x64"):
    """
    Builds a Digital Ocean droplet and returns the droplet ID
    """

    bearer_token = "Bearer " + api_token
    url = "https://api.digitalocean.com/v2/droplets"
    ssh_keys = [ssh_key_id]

    headers = {'Authorization': bearer_token, 'Content-Type': "application/json"}
    body = {'name': name, 'region': region, 'size': size, 'image': image, 'ssh_keys': ssh_keys}

    try:
        r = requests.post(url, headers = headers, data = json.dumps(body))
    except Exception as e:
        raise

    parsed_request = r.json()
    droplet_id = parsed_request['droplet']['id']
    time.sleep(30)

    break_loop = 0
    counter = 0

    #TODO: need a better way of doing this. This loop should continue to poll the droplet status until it says "active", throw exception otherwise
    #TODO: also, the droplet ID will return active even if not ready to use...may need to read more into the DO API docs.
    while not break_loop:
        if counter == 4:
            break
        if DO_get_droplet_status(api_token, droplet_id) == "active":
            break_loop = 1
        else:
            time.sleep(30)
        counter += 1

    return droplet_id

def DO_get_droplet_status(api_token, id):
    """
    Provides the status of a Digital Ocean droplet
    """
    url = "https://api.digitalocean.com/v2/droplets/" + str(id)
    bearer_token = "Bearer " + api_token
    headers = {'Authorization': bearer_token, 'Content-Type': "application/json"}

    try:
        r = requests.get(url, headers = headers)
    except Exception as e:
        raise

    parsed_request = r.json()

    return parsed_request['droplet']['status']

def DO_get_droplet_IP(api_token, id):
        """
        Obtains the IP address of a Digital Ocean droplet
        """
        url = "https://api.digitalocean.com/v2/droplets/" + str(id)

        bearer_token = "Bearer " + api_token
        headers = {'Authorization': bearer_token, 'Content-Type': "application/json"}

        r = requests.get(url, headers = headers)
        parsed_request = r.json()

        return parsed_request['droplet']['networks']['v4'][0]['ip_address']

def SK_add_HTTP_test(username, api_key, websiteName, websiteURL, checkRate=300, testType="HTTP"):
    """
    Adds an HTTP test to Status Cake
    """
    url = "https://app.statuscake.com/API/Tests/Update"
    headers = {'API': api_key, 'Username': username}
    body = {'WebsiteName': websiteName, 'WebsiteURL': websiteURL, 'CheckRate': checkRate, 'TestType': testType}
    try:
        r = requests.put(url, headers = headers, data = body)
    except Exception as e:
        raise

def SK_get_environment_status(username, api_key):
    """
    Provides the status of all tests in a Status Cake account
    """
    url = "https://app.statuscake.com/API/Tests/"
    headers = {'API': api_key, 'Username': username}

    try:
        r = requests.get(url, headers=headers)
    except Exception as e:
        raise

    parsed_request = json.loads(r.text)

    failed_tests = []
    for test in parsed_request:
        if test['Status'].lower() == "down":
            failed_tests.append(test['WebsiteName'])

    return failed_tests

def NC_get_hosts(username, api_key, tld, sld, client_ip="1.1.1.1"):
    """
    Obtains a list of hosts associated with a NameCheap domain
    """
    url = "https://api.namecheap.com/xml.response"
    #The clientIP paramater doesn't actually do anything, so default to 1.1.1.1
    params = {'APIUser': username, 'APIkey': api_key, 'UserName': username,
        'Command': "namecheap.domains.dns.getHosts", 'clientIP': client_ip,
        'TLD': tld, 'SLD': sld}

    #TODO: better error handling here.
    #For example: if IP isn't authorized, NC API returns an XML error code
    try:
        r = requests.get(url, params=params)
    except Exception as e:
        raise

    return r.content

#TODO: more error checking needs to be done with the NC API.
def NC_add_host(username, api_key, hostname, ip_addr, tld, sld, ttl="3600", record_type="A", client_ip="1.1.1.1"):
    """
    Adds a new host to a NameCheap domain
    """
    url = "https://api.namecheap.com/xml.response"
    xml = ElementTree.fromstring(NC_get_hosts(username, api_key, tld, sld))

    #The clientIP paramater doesn't actually do anything, so default to 1.1.1.1
    params = {'APIUser': username, 'APIkey': api_key, 'UserName': username,
        'Command': "namecheap.domains.dns.setHosts", 'clientIP': client_ip,
        'TLD': tld, 'SLD': sld}

    #The namecheap API currently deletes all existing hosts when a new one is added.
    #So, we have to pull down all the existing hosts and build a request to re-add all of them
    i = 1;
    for CommandResponse in xml.findall("{http://api.namecheap.com/xml.response}CommandResponse"):
        for DomainDNSGetHostsResult in CommandResponse:
            for host in DomainDNSGetHostsResult:
                params["HostName" + str(i)] = host.get('Name')
                params["RecordType" + str(i)] = host.get('Type')
                params["Address" + str(i)] = host.get('Address')
                i += 1

    params["HostName" + str(i)] = hostname
    params["RecordType" + str(i)] = record_type
    params["Address" + str(i)] = ip_addr
    params["TTL" + str(i)] = ttl

    try:
        r = requests.post(url, params=params)
    except Exception as e:
        raise

def deploy_web_server():
    try:
        droplet_id = DO_build_server(do_token, droplet_name, do_ssh_key_id)
        droplet_ip = DO_get_droplet_IP(do_token, droplet_id)
        NC_add_host(nc_username, nc_api_key, hostname, droplet_ip, tld, sld)
        SK_add_HTTP_test(sk_username, sk_api_key, droplet_name, droplet_name)
        time.sleep(30)
        subprocess.call("ansible-playbook -i " + droplet_ip + ", " + "main.yml >> /home/ansible/alexa_log.txt 2>&1", shell=True)
    except Exception as e:
        raise
        print("Exception is: ", type(x).__name__, " Value: ", x)
        return


app = Flask(__name__)
ask = Ask(app, "/")
logging.getLogger("flask_ask").setLevel(logging.DEBUG)

@ask.intent("GetEnvironmentStatus")
def env_status():

    try:
        failed_tests = SK_get_environment_status(sk_username, sk_api_key)
    except Exception as e:
        raise

    if len(failed_tests) == 0:
        return statement("Your environment looks good. All tests are currently passing.")
    else:
        return_statement = "The following tests are failing: "
        for test in failed_tests:
            return_statement += test
            return_statement += ", "
        return statement(return_statement)

@ask.intent("BuildWebservers")
def build_web_server():
    thread = Thread(target = deploy_web_server)
    thread.start()
    return statement("I've started deploying your web server. It should be done within the next 5 minutes.")

if __name__ == '__main__':

    app.run(debug=True, host="0.0.0.0")
