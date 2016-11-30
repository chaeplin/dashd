#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import io, os, sys
import simplejson as json
import datetime
import time
import zmq
import array
import binascii
import struct
import psutil
import re
import subprocess
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from ISStreamer.Streamer import Streamer

# --- change 
# rpc
rpcuser     = 'rpc_user'    # change
rpcpassword = 'rpc_paasword' # change

rpcbindip   = '127.0.0.1'  # change
rpcport     = 19998  # change

# zmq
zmqport     = 28332  # change

# initialstate
iss_bucket_name   = 'bucket-name' # change
iss_bucket_key    = 'bucket-key' # change
iss_access_key    = 'access-key' # change
iss_prefix        = 'prefix'  # change to hostname or uniq name

# --- / change

def checksynced():
    try:
        synced = access.mnsync('status')['IsSynced']
        return synced
    except:
        return False

def check_version():
    try:
        cmd = "/usr/local/bin/dash-cli --version"
        with subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE).stdout as f:
            result = f.read().splitlines()
            match   = re.search('Dash Core RPC client version (.*)$', result[0].decode("utf-8"))
            if match:
                version = match.group(1)
                if version:
                    return version
                else:
                    return None

    except Exception as e:
        return None

def rpcgetinfo():
    try:
        getinfo = access.getinfo()

        if len(getinfo) > 0:
            bucket = {}
            bucket['blocks']      = getinfo['blocks']
            bucket['diff']        = json.dumps(getinfo['difficulty'])
            bucket['conns']       = getinfo['connections']
            bucket['tstamp']      = int(time.time())
            bucket['balance']     = json.dumps(getinfo['balance'])
            bucket['keypoolsize'] = getinfo['keypoolsize']
            bucket['protocolversion'] = getinfo['protocolversion']
            bucket['version']         = check_version()
            streamer.log_object(bucket, key_prefix=iss_prefix)

    except:
        pass

    try:
        mncount = access.masternode('count', 'all')
        match         = re.search('Total: (.*) \(PS Compatible: (.*) / Enabled: (.*) / Qualify: (.*)\)$', mncount)
        if match:
            bucket_mn = {}
            bucket_mn['total']   = match.group(1)
            bucket_mn['compa']   = match.group(2)
            bucket_mn['enabled'] = match.group(3)
            bucket_mn['qualify'] = match.group(4)

            if int(bucket_mn['total']) > 0:
                streamer.log_object(bucket_mn, key_prefix=iss_prefix + '_mn')

    except:
        pass

    try:
        spork = access.spork('show')
        if spork:
            streamer.log_object(spork, key_prefix=iss_prefix + '_spork')

    except:
        pass
                
    cpu_percents = psutil.cpu_percent(percpu=True)
    streamer.log_object(cpu_percents, key_prefix=iss_prefix + '_cpu')

#    memory = psutil.virtual_memory()
#    streamer.log_object(memory, key_prefix=iss_prefix + '_virtual_mem')
#    
#    swap = psutil.swap_memory()
#    streamer.log_object(swap, key_prefix=iss_prefix + '_swap_mem')

    streamer.flush()


# rpc 
serverURL = 'http://' + rpcuser + ':' + rpcpassword + '@' + rpcbindip + ':' + str(rpcport)
access = AuthServiceProxy(serverURL)

while(not checksynced()):
    time.sleep(30)

# zmq
zmqContext = zmq.Context()
zmqSubSocket = zmqContext.socket(zmq.SUB)
zmqSubSocket.setsockopt(zmq.SUBSCRIBE, b"hashblock")
zmqSubSocket.connect("tcp://%s:%i" % (rpcbindip, zmqport))

# iss
streamer = Streamer(bucket_name=iss_bucket_name, bucket_key=iss_bucket_key, access_key=iss_access_key, buffer_size=100)

current_sequence = 0

# main
try:
    while True:
        msg = zmqSubSocket.recv_multipart()
        topic = str(msg[0].decode("utf-8"))
        body  = str(binascii.hexlify(msg[1]).decode("utf-8"))
        sequence = "Unknown"

        if len(msg[-1]) == 4:
          msgSequence = struct.unpack('<I', msg[-1])[-1]
          sequence = str(msgSequence)

        if topic == "hashblock":
            if sequence != "Unknown" and int(sequence) >= current_sequence:
                rpcgetinfo()
                current_sequence = int(sequence)

            elif int(sequence) < current_sequence:
                while(not checksynced()):
                    print('x')
                    time.sleep(30)
                current_sequence = 0

except Exception as e:
    print(e.args[0])
    streamer.close()
    zmqContext.destroy()
    sys.exit()

except KeyboardInterrupt:
    streamer.close()
    #zmqContext.destroy()
    sys.exit()