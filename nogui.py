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

import string
import re
import threading
import sys
import traceback
import subprocess
import jobhelper
config=jobhelper.loadConfig()

lastAllFd=[]
toberemoved=[]

class resetThread(threading.Thread):
  def __init__(self,code,spins,wxapp=None,gplid=config.gplID,geometry=[-1,-1,-1,-1]):
    super(resetThread, self).__init__()
    self.running=True
    self.wxapp=wxapp
    self.spins=spins
    setTerm='set terminal '+config.terminal+' dashed title "'+gplid+'"'
    try:
      if (geometry[0]!=-1):
        setTerm+=' size {},{} '.format(*tuple(geometry[2:]))
      if (geometry[2]!=-1) and (config.terminal=='x11'):
        setTerm+=' position {},{} '.format(*tuple(geometry[:2]))
    except:
      raise
    self.resetCode=config.resetPrefix+re.sub("\n","\n  ",string.lstrip(code,"\n")) +\
               "\n  print >>gnuplot,'"+setTerm+"'\n  return data,extra,ukeys\n"
    self.start()

  def run(self):
    global lastAllFd
    try:
      self.resetMod=jobhelper.importCode(self.resetCode,"resetMod")
      jobhelper.reloadMods(config.varMods,self.resetMod)
      if self.wxapp!=None:
        self.wxapp.reportProgress(True,0,len(self.resetCode.split('\n')),'resetting...')
        self.wxapp.reportProgress(False,0,0)
        self.resetMod.findjobs.meter=self.wxapp
        self.resetMod.findjobs.useServer=self.wxapp.useServer
      self.resetMod.gnuplot=gnuplot
      self.resetMod.plot.gnuplot=gnuplot
      self.resetMod.findjobs.lastallfd=lastAllFd
      data,extra,ukeys=self.resetMod.myreset(self.wxapp,self.spins)
      lastAllFd=self.resetMod.findjobs.lastallfd
      self.restext=""
      for i in data.keys():
        try:
          self.restext+=i+":"+str(data[i].shape)+";"
        except AttributeError:
          try:
            self.restext+=i+":"+str(len(data[i]))+":"+str(data[i][0].shape)+";"
          except IndexError:
            pass
          except AttributeError:
            print >>sys.stderr,'list in list? ({})'.format(i)
    except:
      jobhelper.printerr(traceback.format_exc(),col=31)
      self.restext='Reset Error'
      data={}
      extra={}
      ukeys={}
    if self.wxapp!=None:
      self.wxapp.reportProgress('last',0,len(self.resetCode.split('\n')),'Done with reset')
    self.wxapp.data=data
    self.wxapp.extra=extra
    self.wxapp.ukeys=ukeys
    try:
      import wx
      wx.PostEvent(self.wxapp,self.wxapp.DataLabelEvent\
                   (data="data read ({}): {}".format(len(data),self.restext)))
    except (NameError,ImportError,wx._core.PyDeadObjectError):
      # The PyDeadObjectError may be raised if the wxapp has died since 
      # this thread was started. That's ok. We won't post then
      pass
    self.running=False

  def stop(self):
    self.running=False
    self.resetMod.findjobs.running=False
    if self.resetMod.findjobs.useServer:
      import dataserver
      dataserver.cancelRequest()
      
def doPlot(wxapp,code,data,spins,extra,allstores,ukeys,setrange):
  global toberemoved
  try:
    plotCode=config.plotPrefix+re.sub("\n","\n  ",string.lstrip(code,"\n"))\
        +"\n  sys.stdout.flush()\n"
    plotCode=plotCode+"  return plot.storedPlots\n"
    # print plotcode
    plotMod=jobhelper.importCode(plotCode ,"plotMod")
    jobhelper.reloadMods(config.varMods,plotMod)
    plotMod.gnuplot=gnuplot
    plotMod.plot.gnuplot=gnuplot
    plotMod.plot.toberemoved=toberemoved
    mystore=plotMod.myplot(wxapp,data,spins,extra,allstores,ukeys,setrange)
    toberemoved=plotMod.plot.toberemoved
  except:
    jobhelper.printerr(traceback.format_exc(),col=31)
    mystore=''
  return mystore
def doNothing(a):
    return a

def init():
  global gnuplot
  memLimit=config.memLimit
  print >>sys.stderr,"Setting absolute memory limit to {0}MB.".format(memLimit)
  import resource
  resource.setrlimit(resource.RLIMIT_AS, (memLimit * 1048576L, -1L))
  gplProc=subprocess.Popen(['gnuplot'],stdin=subprocess.PIPE)
  gnuplot=gplProc.stdin


if __name__ == "__main__":
  import argparse
  parser = argparse.ArgumentParser()
  
  parser.add_argument('--spins',nargs="+",type=int,help="Overwrite spin controls")
  parser.add_argument('--useserver',action='store_true')
  parser.add_argument('plotname')
  args=parser.parse_args()

  plotsets=ET.ElementTree(ET.Element("allsets"))
  plotsets.parse("plot.xml")
  a=plotsets.find("plotset[@name='"+args.plotname+"']")
  if (a!=None):
    spins=range(4)
    for i in spins:
      b=a.findall("sc")[i].text
      if (b != None):
        spins[i]=int(b)
      else:
        spins[i]=0
    spins[:len(args.spins)]=args.spins

    class fakeWxApp():
      pass
    FWA=fakeWxApp

    FWA.useServer=args.useserver

    myreset=resetThread(a.find("reset").text,spins,FWA)
    myreset.join()

    data,extra,ukeys=FWA.data,FWA.extra,FWA.ukeys
    print >>sys.stderr,"data read ("+str(len(data))+"):"+myreset.restext
    allstores=[]
    mystore=doPlot(None,a.find("plot").text,data,spins,extra,allstores,ukeys,doNothing)

