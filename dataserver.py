#!/usr/bin/env python

# Part of PROA - Python research organization and analysis
# Copyright (C) 2013 Werner Koch
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Based loosely on a python proxy written by
# at voorloop_at_gmail.com
# distributed over IDC(I Don't Care) license.

import socket
import numpy as np
import traceback
import threading
import datetime
import select
import time
import sys
import cPickle as pickle
import threading

import jobhelper
config=jobhelper.loadConfig()


lastallfd=[]
cacheGplFiles=[]

# Changing the buffer_size and delay, you can improve the speed and bandwidth.
# But when buffer get to high or delay go too down, you can broke things
buffer_size = 4096
delay = 0.0001

outSocket=None
stderr=None

class socketStdErr(object):
  def write(self,data):
    if outSocket!=None:
      pickle.dump(('o',data),outSocket)
    else:
      stderr.write(data)

class requestThread(threading.Thread):
  def __init__(self,request,clientSock):
    super(requestThread,self).__init__()
    self.running=True
    self.request=request
    self.clientSock=clientSock
    self.start()

  def start(self):
    global lastallfd,cacheGplFiles,outSocket
    self.resultStream=self.clientSock.makefile('wb',buffer_size)
    outSocket=self.resultStream
    try:
      if (len(self.request)>2) and (self.request[2]!=None):
        jobhelper.reloadMods(self.request[2],self)
      if self.request[0]=='g':
        self.findjobs.lastallfd=lastallfd
        pickle.dump(('r',self.findjobs.gimmeAll(*self.request[1])),self.resultStream)
        lastallfd=self.findjobs.lastallfd
      elif self.request[0]=='o':
        self.findjobs.cacheGplFiles=cacheGplFiles
        result=self.findjobs.openFile(*self.request[1])
        pickle.dump(('a',result),self.resultStream,-1)
#        pickle.dump(('a',result.shape,result.dtype,result.tostring()),f)
        cacheGplFiles=self.findjobs.cacheGplFiles
    except Exception, e:
      try:
        pickle.dump(('e',sys.exc_info()[0],traceback.format_exc()),self.resultStream)
      except IOError:
        outSocket=None
        print >>stderr,traceback.format_exc()
    self.resultStream.close()
    self.clientSock.close()
    outSocket=None
    self.running=False

  def stop(self):
    if self.running:
      print >>sys.stderr,'stopping data gathering'
      self.running=False
      if hasattr(self,'findjobs'):
        self.findjobs.running=False

class dataServer:
  def __init__(self, host, port):
    self.requests = []
    self.server=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.server.bind((host, port))
    self.server.listen(200)

  def mainLoop(self):
    self.running=True
    while self.running==True:
      time.sleep(delay)
      inputready, outputready, exceptready = select.select([self.server], [], [])
      for self.s in inputready:
        self.onAccept()
        break
      for ind,ar in enumerate(self.requests):
        if not ar.running:
          del self.requests[ind]
    self.server.close()

  def onAccept(self):
    global outSocket,lastallfd,cacheGplFiles
    clientSock, clientaddr = self.server.accept()
    f=clientSock.makefile('rb',buffer_size)
    request=pickle.load(f)
    f.close()
    f=clientSock.makefile('wb',buffer_size)
    outSocket=f
    if request[0] in ['t','r','c']:
      if request[0]=='t':
        self.running=False
      elif request[0]=='r':
        self.running='restart'
        print >>sys.stderr,'Restarting dataServer...'
      elif request[0]=='c':
        for ar in self.requests:
          ar.stop()
      f.close()
      outSocket=None
      clientSock.close()
    else:
      self.requests.append(requestThread(request,clientSock))

lastServer=None
lastPort=None

def cancelRequest():
  makeRequest(lastServer,lastPort,('c',))

def makeRequest(serverIP,serverPort,request):
  try:
    datasocket=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
  except socket.error as e:
    raise IOError(str(e))
  datasocket.connect((serverIP,serverPort))
  f=datasocket.makefile('wb',buffer_size)
  pickle.dump(request,f)
  f.close()
  if not (request[0] in ['t','r','c']):
    lastServer=serverIP
    lastPort=serverPort
    f=datasocket.makefile('rb',buffer_size)
    while (1):
      result=pickle.load(f)
      if result[0]=='o':
        sys.stderr.write(result[1])
      else:
        break
    f.close()
    datasocket.close()
    if result[0]=='e':
      raise result[1](result[2])
    elif result[0]=='r':
      return result[1]
    elif result[0]=='a':
      # todo: do something fancy to reduce network transfer times
      return result[1]
    raise ValueError('Received invalid response vom dataServer : "{}"'.format(result[0]))
  datasocket.close()
#    return np.fromstring(result[3],result[2]).reshape(result[1])
 

if __name__ == '__main__':
  # Redirecting sys.stderr into a an object so that it can be piped through
  # a network connection
  stderr=sys.stderr
  sys.stderr=socketStdErr()
  server = dataServer('', config.login[sys.argv[1]]['port'])
  try:
    server.mainLoop()
  except KeyboardInterrupt:
    print datetime.datetime.today().isoformat(),"Ctrl C - Stopping server"
    sys.exit(1)
  if server.running=='restart':
    import subprocess
    subprocess.call('nohup '+" ".join(sys.argv)+' &',shell=True)
