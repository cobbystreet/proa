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

import os
import sys
import numpy

def importCode(code, name, add_to_sys_modules=False,seqInd=None):
  """
  Construct a module from source.

  code: Any object containing code: a string, a file object, or
    a compiled code object.

  add_to_sys_modules: If True, and the new Modules is added to
    sys.modules under the given name.

  seqInd: A list or array that can be used to parametrize the code
    being passed. Its length will be available at module execution
    as "seqLen". The actual "seqInd" parameter will be expanded to
    contain at least 20 (possibly ==0) elements. Thus only the
    desired first values need to be passed but more can be referenced
    in the code.

  Returns a new module object initialized by dynamically importing the given code.
    
  """
# The reason for the seqInd here is that it needs to be available for the
# exec in the module to work. seqInd thus unfortunately can't be added
# afterwards.
  import new
  module = new.module(name.encode('ascii', 'ignore'))
  if add_to_sys_modules:
    import sys
    sys.modules[name.encode('ascii', 'ignore')] = module
  if seqInd!=None:
    seqInd=numpy.array(seqInd)
    module.seqLen=seqInd.shape[0]
    module.seqInd=numpy.concatenate((seqInd,numpy.zeros(20,dtype=int)))
  exec code in module.__dict__
  return module

def getInput(name,path=None,seqInd=None):
  if path!=None:
    name=os.path.join(path,name)
  parafile=open(name,'r')
  if seqInd!=None:
    try:
      # importCode will add more zeros at the end of this so you can supply only the
      # first (few) parameter(s) and the rest will be set to zero
      seqInd=[int(i) for i in seqInd.split(',')]
    except AttributeError:
      # already split?
      pass
  else:
    # this is a very crude hack. I don't know how many zeros you might need
    seqInd=numpy.zeros(100,dtype=int)
  aPar=importCode(parafile,"params",seqInd=seqInd)
  aPar.name=name
  parafile.close()
  return aPar

def printerr(a,col=32):
  print >>sys.stderr,'\033[{}m{}\033[0m'.format(col,a)

def uniq(seq):
  """
  Make a set unique.

  Parameters
  ----------
  
  seq : Sequence of items.

  Returns
  -------

  uniqSeq : Same sequence with duplicates removed.
  """
  seen = set('repr')
  seen_add = seen.add
  return [ x for x in seq if str(x) not in seen and not seen_add(str(x))]

def reloadMods(modNames,target=None):
  oldPath=list(sys.path)
  try:
    # Provide the configured pythonPath in case some of the reloaded
    # modules are located there.
    sys.path=config.pythonPath+sys.path
    for m in modNames:
      if m in sys.modules:
        del sys.modules[m]
      sys.modules[m]=__import__(m)
      if target!=None:
        setattr(target,m,sys.modules[m])
  finally:
    sys.path[:]=oldPath # Restore

def loadConfig():
  oldPath=list(sys.path)
  sys.path.insert(0,'./')
  try:
    return __import__('proaconfig')
  finally:
    sys.path[:]=oldPath # Restore

def loadJobTypes():
  import xml.etree.ElementTree as ET
  xmlfields=ET.ElementTree(ET.Element("proaconfig"))
  try:
    xmlfields.parse(config.jobTypes)
  except:
    print >>sys.stderr,"Couldn't load jobType config. Trying defaults in PROA directory."
    path=os.path.dirname(os.path.realpath(__file__))
    xmlfields.parse(os.path.join(path,config.jobTypes))
  return xmlfields

# login to cluster and launch command in 'clientArgs' there
def sshCall(clientArgs,hostname,cwd=None,catch=False,noTTY=False,noWait=False):
  import subprocess
  sshCmd="ssh "+['-t ',' -T '][noTTY]+"-q "+hostname+" '. ~/.bashrc ;"
  if cwd!=None:
    sshCmd+=" cd "+cwd+" ;"
  sshCmd+=" ".join(clientArgs)+"'"
#  print >>sys.stderr,'calling : ',sshCmd
  procArgs={}
  if catch:
    procArgs['stdout']=subprocess.PIPE
#   if noTTY:
#       # attach this if you need to keep signals away from ssh
#       # usually, it is sufficient to provide '-T' argument. 
#       # In some cases, however, you need a tty but don't want SIGINT to
#       # propagate to ssh.
#     print 'attaching sigINTchanger'
#     def sigINTchanger():
#       print 'changing signals'
#       import os
#       os.setpgrp()
#       import signal
#       signal.signal(signal.SIGINT, signal.SIG_IGN)
#     procArgs['preexec_fn']=sigINTchanger
  proc=subprocess.Popen(sshCmd,shell=True,**procArgs)
  if noWait:
    return proc
  else:
    return proc.communicate()[0]

config=loadConfig()
