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
import argparse
import numpy
import sys
import time
import signal
import subprocess
import traceback
import shutil
import os
import stat
import re
try:
  import readline
  useRL=True
except ImportError:
  useRL=False

import jobhelper
config=jobhelper.loadConfig()

import findjobs

pid=None

watchProc=None
killed=False

def sigINT_handler(recSignal, frame):
  global killed
  print 'caught sigINT'
  killed=True
  if watchProc!=None:
    watchProc.send_signal(signal.SIGINT)
  if pid!=None:
    sys.stdout.write('\n')
    try:
      answer=raw_input("Kill running process(y) [y]?")
    except RuntimeError:
      answer='y' 
    if (answer in ['','y','Y']):
      print >>sys.stderr,'killing job "{}" ...'.format(pid)
      config.login[args.runnode]['killJob'](pid)
  else:
    sys.exit(3)

def exePath(program):
  import os
  def is_exe(fpath):
    return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

  fpath, fname = os.path.split(program)
  if fpath:
    if is_exe(program):
      return fpath
  else:
    for path in os.environ["PATH"].split(os.pathsep):
      path = path.strip('"')
      exe_file = os.path.join(path, program)
      if is_exe(exe_file):
        return path

  return None


parser = argparse.ArgumentParser()
parser.add_argument('--jobtype',help='Specify a jobtype from {} to use for defaults'.format(config.jobTypes))
parser.add_argument('-t','--threads',type=int,help='Set OpenMP thread count in environment')
parser.add_argument('--nodearg',nargs='?',const=None,help='Manually select a slave node')
parser.add_argument('-f','--files',nargs='+',help='List support files for the job')
parser.add_argument('--link',action='store_true',help='Link to support files instead of copy')
parser.add_argument('-p','--profile',action='store_true',help='Do not create a job directory. Just perform a profile run')
parser.add_argument('-P','--path',nargs='+',default=config.pythonPath,help='Provide additional PYTHONPATH paths')
parser.add_argument('-i','--input',help='Input parameter file')
parser.add_argument('--description',help='Job description')
parser.add_argument('-r','--redo',nargs='?',const='LAST',help='Rerun a previous job. Files are transfered again!')
parser.add_argument('-l','--loginnode',help='Loginnode for job submission')
parser.add_argument('--runnode',help=argparse.SUPPRESS)
parser.add_argument('--noStripPaths',action='store_true',help='Do not remove paths from support files. You almost certainly don\'t want that!!')
parser.add_argument('-L','--longoutput',action='store_true',help='Provide the full live job output. Default is a contracted view.')
parser.add_argument('--fireaway',action='store_true',help='Show no live output of the job. Start and log out.')
parser.add_argument('--nogitrev',action='store_true',help='Do not try to obtain git revision for the binary')
parser.add_argument('--libpath',help='Paths to add to LD_LIBRARY_PATH')
parser.add_argument('--preload',nargs='+',help='Libraries to load via LD_PRELOAD')
parser.add_argument('--precommand',help='Additional command to run in the job directory before the job command')
parser.add_argument('--trace',help='Provide a trace library. You almost certainly don\'t want that!!')
group = parser.add_mutually_exclusive_group()
group.add_argument('--show',action='store_true',help='Resume live view of the output of a still running job')
group.add_argument('--cmd',help='Command to execute for the job')

parser.add_argument('--sequence',help='Indices to use for a sequence run. \n'\
                    +'Comma seperated list of non inclusive upper bounds.')
parser.add_argument('--seqname',help='Provide a descriptive name for a sequence')
parser.add_argument('--seqstart',type=int,help='Start the sequence at this (linearized) index.')
parser.add_argument('--seqpreview',action='store_true',\
                      help="Show the effect of running a sequence")
parser.add_argument('--seqflatdir',action='store_true',\
                      help='Do not create subdirectories for sequence runs')

args=parser.parse_args()

if hasattr(config,'ldPreload'):
  if args.preload:
    args.preload+=config.ldPreload
  else:
    args.preload=config.ldPreload

cpFileList=[]

if args.jobtype:
  jobTypes=jobhelper.loadJobTypes()
  jobType=jobTypes.find('jobtype[@name="{}"]'.format(args.jobtype))
  if jobType==None:
    print >>sys.stderr,"unknown jobtype {}".format(args.jobType)
  else:
    for fn in jobType.findall('support'):
      cpFileList.append(fn.attrib['filename'])

if (args.files):
  cpFileList+=args.files

if (not args.show) and (not args.cmd):
  if jobType!=None:
    cmd=jobType.find('cmd')
    if cmd!=None:
      args.cmd=re.sub('%%INPUT',args.input,cmd.text)
    else:
      print >>sys.stderr,'Neither --cmd nor --show specified and the jobtype {} has no default command.'.format(args.jobtype)
      print >>sys.stderr,'I don\'t know what to do.'
  else:
    print >>sys.stderr,'Neither --cmd nor --show specified',
    if args.jobtype:
      print >>sys.stderr,'and the jobtype "{}" is unknow.'.format(args.jobtype)
    else:
      print >>sys.stderr,'and no jobtype provided.'
    print >>sys.stderr,'I don\'t know what to do.'
    sys.exit(1)

if args.cmd:
  binary=args.cmd.split(" ")[0]
  binpath=exePath(binary)
  if re.match('./',binary):
    cpFileList.append(binary)

if args.input:
  cpFileList.append(args.input)

#return the parsed sequence as a list of integers
def splitSeq(inputSeq):
  sequence=[]
  for s in inputSeq.split(','):
    aseq=[]
    sseq=s.split('/')
    for asplit in sseq:
      a=re.match('([0-9]+)(-([0-9]+))?',asplit)
      if a:
        try:
          end=int(a.group(3))
          start=int(a.group(1))
        except (ValueError,TypeError):
          if len(sseq)>1:
            start=int(a.group(1))
            end=start+1
          else:
            end=int(a.group(1))
            start=0
        aseq+=range(start,end)
    sequence.append(aseq)
  return sequence

def getRunDir(baseDir,redo=False,dirItems=config.dirItems):
  import findjobs
  if redo:
    ind=0
    paths=[]
    for job in findjobs.findFiles(baseDir,config.jobFile,dirItems=dirItems):
      try:
        desc=findjobs.loadJobMeta(job)['desc']
      except KeyError:
        desc=''
      path=os.path.split(job)[0]
      paths.append(path)
      print >>sys.stderr,ind,path,desc
      ind+=1
      if ind==10:
        break
    if ind==0:
      raise ValueError("No jobs found. Can't redo.")
    print >>sys.stderr,'Choose redo directory by number :',
    answer=sys.stdin.readline()
    if answer=='\n':
      return paths[0]
    else:
      return paths[int(answer)]
  else:
    for job in findjobs.findFiles(baseDir,'.job',dirItems=dirItems):
      path=os.path.split(job)[0]
      levelCount=0
      while (1):
        head,tail=os.path.split(path)
        if tail==dirItems[-1]:
          # this is the last possible directory name
          if head!=baseDir:
            levelCount+=1
            path=head
            continue
            
          # The store is full ( all levels maxed out at 'dirItems[-1]').
          # I need to move everything one level up
          import tempfile
          import shutil
          tempname=tempfile.mkdtemp(dir=baseDir)
          for d in dirItems:
            shutil.move(os.path.join(baseDir,d),tempname)
          shutil.move(tempname,os.path.join(baseDir,dirItems[0]))

          # Pretend this was the last found path.
          tail=dirItems[0]
          levelCount+=1
        break
      # Now create a path parallel to the old path with the same level
      # depth.
      newPath=os.path.join(head,dirItems[dirItems.index(tail)+1])
      for i in range(levelCount):
        newPath=os.path.join(newPath,dirItems[0])
      break
    else:
      # findfiles did not even find a single
      newPath=os.path.join(baseDir,dirItems[0])
    os.makedirs(newPath)
    return newPath
  
if args.seqpreview:
  import jobhelper

  ### WARNING: Deep magic begins here :)

  # This object will be passed to the getInput function in a seqInd array
  # to cause an exception that allows detection of references to a certain
  # seqInd component.
  class myFail(object):
    def __repr__(self):
      raise None
    def __str__(self):
      raise None
  maxSeq=100
  noSeqParams=jobhelper.getInput(name=args.input)
  useSeq=[]
  # detect all components of seqInd that are being refered to in the input file
  for i in range(maxSeq):
    sequence=[0]*maxSeq
    sequence[i]=myFail()
    seqInd=numpy.array(sequence)
    try:
      params=jobhelper.getInput(name=args.input,seqInd=seqInd)
    except (TypeError,IndexError):
      useSeq.append(i)
  print "sequence indices in use: ",useSeq
  if args.sequence:
    realSeq=splitSeq(args.sequence)
  else:
    try:
      seqFile=open('sequence','r')
      sequence=seqFile.read().rstrip()
      seqFile.close()
      realSeq=splitSeq(sequence)
    except IOError:
      realSeq=[[]]*len(useSeq)
  def printLastSet(lastSetInd,lastSet,realSeq,ind):
    if len(lastSetInd)>0:
      try:
        tarr=numpy.array([j in realSeq[ind] for j in lastSetInd])
        if tarr.any():
          sys.stdout.write('\033[1m')
      except IndexError:
        pass
      if (len(lastSetInd)>1):
        sys.stdout.write('{:3}-{:3}: {}'.format(lastSetInd[0],lastSetInd[-1],lastSet))
      else:
        sys.stdout.write('{:7}: {}'.format(lastSetInd[0],lastSet))
      try:
        if numpy.array([j in realSeq[ind] for j in lastSetInd]).any():
          sys.stdout.write('\033[m')
      except IndexError:
        pass
      sys.stdout.write("\n")

  import types
  for ind in useSeq:
    allChangeVars=[]
    sequence=[0]*(max(useSeq)+1)
    print "changing sequence ind {}:".format(ind)
    for i in range(maxSeq):
      try:
        sequence[ind]=i
        seqInd=numpy.array(sequence)
        params=jobhelper.getInput(name=args.input,seqInd=seqInd)
        for item in dir(params):
          if (not item.startswith("__")) and \
                (item.lower() not in ['nan','seqind','seqlen']) and\
                (not isinstance(params.__dict__[item],types.FunctionType)):
            kRange=None
            try: # is item a dict?
              kRange=params.__dict__[item].keys()
            except AttributeError:
              if ((type(params.__dict__[item])==type(list())) or\
                    (type(params.__dict__[item])==type(numpy.array([])))):
                # item is a list or array
                kRange=range(max(len(params.__dict__[item]),len(noSeqParams.__dict__[item])))
              else:
                 # item is just a regular variable?
                if (params.__dict__[item]!=noSeqParams.__dict__[item]):
                  if not [item] in allChangeVars:
                    allChangeVars.append([item])
                
            if kRange!=None: # check components if item is a dict, list, or array
              for k in kRange:
                try:
                  if (params.__dict__[item][k]!=noSeqParams.__dict__[item][k]):
                    if not [item,k] in allChangeVars:
                      allChangeVars.append([item,k])
                except ValueError:
                  if (params.__dict__[item][k]!=noSeqParams.__dict__[item][k]).any():
                    if not [item,k] in allChangeVars:
                      allChangeVars.append([item,k])
                except IndexError:
                  allChangeVars.append([item,k])
      except IndexError:
        break
    lastSet=[]
    lastSetInd=[]
    for i in range(maxSeq):
      try:
        changeVars=[]
        sequence[ind]=i
        seqInd=numpy.array(sequence)
        params=jobhelper.getInput(name=args.input,seqInd=seqInd)
        for item in allChangeVars:
          if len(item)==1: # item is a regular variable
            changeVars.append([item[0],params.__dict__[item[0]]])
          else: # item is a list, array, or dict
            try:
              changeVars.append([item[0]+'['+str(item[1])+']',params.__dict__[item[0]][item[1]]])
            except IndexError:
              changeVars.append([item[0]+'['+str(item[1])+']','MISSING'])
      except IndexError:
        break
      CVneq=False
      try:
        if changeVars!=lastSet:
          CVneq=True
      except ValueError: #one of the items was an array, so now check for it's elements
        for c,l in zip(changeVars,lastSet):
          try:
            if c[1]!=l[1]:
              CVneq=True
              break
          except ValueError:
            if not numpy.allclose(c[1],l[1]):
              CVneq=True
              break

      if CVneq:
        printLastSet(lastSetInd,lastSet,realSeq,ind)
        lastSet=changeVars
        lastSetInd=[i]
      else:
        lastSetInd.append(i)
      # for k in [v[0] for v in changeVars]:
      #   allChangeVars.add(k)
    printLastSet(lastSetInd,lastSet,realSeq,ind)
    changeVars=[]
    for item in allChangeVars:
      if len(item)==1: # item is a regular variable
        changeVars.append([item[0],noSeqParams.__dict__[item[0]]])
      else:
        try:
          changeVars.append([item[0]+'['+str(item[1])+']',noSeqParams.__dict__[item[0]][item[1]]])
        except IndexError:
          changeVars.append([item[0]+'['+str(item[1])+']','MISSING'])              
    print 'D      : {}'.format(changeVars)
  print "sequence ({} runs): {}".\
      format(numpy.prod(numpy.array([len(s) for s in realSeq])),realSeq)
  sys.exit(0)

def initDir(runpath,sourcePath,cpFileList=[],meta={}):
  meta['dir']=runpath
  meta['time']=str(int(time.time()))
  meta['asctime']=time.asctime()
  meta['jobtype']=args.jobtype
  # Save metaData here, to mark the directory in case of errors below
  findjobs.saveJobMeta(os.path.join(runpath,config.jobFile),meta)

  # copy all required files (provided list+input+binary) to rundir
  if (len(cpFileList)>0):
    for f in cpFileList:
      if not args.noStripPaths:
        f=os.path.basename(f)
      dest=os.path.join(runpath,f)
      source=os.path.join(sourcePath,f)
      try:
        os.unlink(dest)
      except OSError:
        pass # That's ok. The unlink is a check to remove old files from reruns.
      if args.link:
        os.link(source,dest)
      else:
        shutil.copy(source,runpath)

  # get git revision for binary
  if (not args.nogitrev):
    try:
      meta['gitrev']=open(binpath+'/.'+binary+'.gitrev','r').read()[:-1]
    except (IOError,TypeError):
      pass

  if args.input:
    f=args.input
    if args.noStripPaths:
      f=os.path.basename(f)
    meta['input']=f
  findjobs.saveJobMeta(os.path.join(runpath,config.jobFile),meta)

def execCmd(command,runpath,cmd,jobScript):  
  command+=config.login[args.runnode]['startCmd'](cmd)

  # Create the job script
  cmdFile=open(os.path.join(runpath,jobScript),'w')
  print >>cmdFile,'#!/bin/bash\n'+command
  mode = os.fstat(cmdFile.fileno()).st_mode
  mode |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
  os.fchmod(cmdFile.fileno(), stat.S_IMODE(mode))
  cmdFile.close()

  pid=config.login[args.runnode]['submitJob'](runpath,jobScript,args.nodearg)
  meta['pid']="--".join([str(p) for p in pid])
  return pid

def watchJob(pid):
  import select
  import fcntl
  import os
  global watchProc,killed
  # display output on screen, contracted to one line
  killed=False
  signal.signal(signal.SIGINT, sigINT_handler)
  watchProc=config.login[args.runnode]['watchJob'](pid)
  traceBack=None

  # Make stdout of watchProc non-blocking
  flags = fcntl.fcntl(watchProc.stdout.fileno(), fcntl.F_GETFL)
  fcntl.fcntl(watchProc.stdout.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)

  while 1:
    try:
      readlist=select.select([watchProc.stdout],[],[])[0]
    except select.error:
      break
    output=watchProc.stdout.read(1)
#    output=os.read(watchProc.stdout.fileno(),1024)
    if traceBack!=None:
      traceBack+=output
    if output=="Traceback (most recent call last):\n":
      traceBack=output
    if not output:
      break
    if not args.longoutput:
      sys.stdout.write(string.replace(output,'\n','\r'))
    else:
      sys.stdout.write(output)
    # maybe send a delete till end of line ? \033[K
  sys.stdout.write('\n')
  if traceBack!=None:
    sys.stdout.write('\033[32m')
    sys.stdout.write(traceBack)
    sys.stdout.write('\033[0m')
  watchProc.wait()
  ret=(watchProc.returncode)
  watchProc=None
  pid=None
  return ret


if args.loginnode:
  # compose arguments for call on cluster node. This requires removing the cluster parameters
  clientargs=sys.argv
  
  #find the --loginnode argument to replace it with --runnode 
  # for the runjob.py call on the cluster
  i=1
  while (clientargs[i] not in ['-l','--loginnode']):
    i+=1
  clientargs[i]='--runnode'

  # escape all remaining arguments for shell execution later on
  clientargs=['"'+c+'"' for c in clientargs]
  
  supportDir=os.path.join(config.login[args.loginnode]['baseDir'],config.supportDir)

  # transfer all dependent files to cluster
  # append the jobtypes file to make it available on the cluster
  cpFileList.append(config.jobTypes)
  if (len(cpFileList)>0):
    print >>sys.stderr,'copying files to cluster:',cpFileList
    subprocess.call(['scp','-p','-q']+cpFileList\
                    +[args.loginnode+':'+supportDir])
  
  jobhelper.sshCall(clientargs,args.loginnode,supportDir)
else:
  command=''
  if args.threads:
    command+='export OMP_NUM_THREADS='+str(args.threads)+'\n'
  if args.path:
    command+='export PYTHONPATH='+':'.join(args.path)+'\n'
  if args.libpath:
    command+='export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:'+args.libpath+'\n'
  if args.preload:
    command+='export LD_PRELOAD='+':'.join(args.preload)+'\n'
  if args.precommand:
    command+=args.precommand+'\n'
  if args.trace:
    command+='rm -f TRACE\n'
    command+='export LD_PRELOAD='+args.trace+'\n'
  if args.profile:
    command+='time stdbuf -o 0 -e 0 python -m cProfile -o '+binary+'.prof '+args.cmd+"\n"
    command+='python -c \'import pstats;p=pstats.Stats("'+binary+'.prof");p.strip_dirs().sort_stats("cumulative").print_callees("main")\''
    cmdOut=subprocess.Popen(command,shell=True,stdout=subprocess.PIPE)
    while 1:
      output=cmdOut.stdout.readline()
      if not output:
        break
      sys.stdout.write(output)
  else:
    meta={}

    sourcePath='./'
    baseDir=config.login[args.runnode]['baseDir']
    if args.redo or args.show:
      if (args.redo) and (args.redo!='LAST'):
        runpath=args.redo
      elif args.show and (args.show!=True):
        runpath=args.show
      else:
        runpath=getRunDir(baseDir,redo=True)
      meta=findjobs.loadJobMeta(os.path.join(runpath,config.jobFile))
    else:
      runpath=getRunDir(baseDir)

    print 'Running in "'+runpath+'"'

    if args.sequence:
      import itertools
      sequence=splitSeq(args.sequence)
      count=numpy.prod(numpy.array([len(s) for s in sequence]))
      if args.seqname:
        meta['desc']=args.seqname
      meta['sequence']=args.sequence
      initDir(runpath,sourcePath,cpFileList,meta=meta)

      for iteration,ind in enumerate(itertools.product(*(s for s in sequence))):
        if (not args.seqstart) or (iteration>=args.seqstart):
          print >>sys.stderr,'Running sequence {}/{}'.format(iteration,count)
          seqInd=','.join([str(i) for i in ind])
          if args.seqflatdir:
            seqPath=runpath
            jobScript=config.jobScript+'-'+seqInd
          else:
            seqMeta=dict(meta)
            del seqMeta['sequence']
            seqMeta['seqind']=seqInd
            seqPath=os.path.join(runpath,'s'+seqInd)
            jobScript=config.jobScript
            try:
              os.mkdir(seqPath)
            except OSError:
              if not args.redo:
                print >>sys.stderr,"runpath {} exists and this is not a redo run. Exiting".\
                    format(seqPath)
                sys.exit(1)
            initDir(seqPath,runpath,cpFileList,meta=seqMeta)
          pid=execCmd(command,seqPath,args.cmd+' --seqind '+seqInd,jobScript)
          if not args.fireaway:
            returnCode=watchJob(pid)
            if killed:
              answer=raw_input("Kill sequence[y]?")
              if (answer in ['','y','Y']):
                print >>sys.stderr,"sequence terminated at iteration {}".format(iteration)
                break
            elif returnCode!=0:
              print >>sys.stderr,"running sequence failed at iteration {} :".\
                  format(iteration),returnCode
              sys.exit(2)
    else:
      if not args.show:
        initDir(runpath,sourcePath,cpFileList,meta=meta)
        pid=execCmd(command,runpath,args.cmd,config.jobScript)
        if not args.description:
          # ask user for description, possibly initializing from previous choice
          if args.redo:
            try:
              description=meta['desc']
            except KeyError:
              print 'empty desc returned from jobfile'
              description=''
          else:
            description=''
          if useRL:
            try:
              readline.read_history_file('runjob.history')
            except IOError:
              pass
            readline.set_startup_hook(lambda: readline.insert_text(description))
          description=raw_input('Description please:')
          if useRL:
            readline.set_startup_hook()
            readline.write_history_file('runjob.history')
          meta['desc']=description
        else:
          meta['desc']=args.description
        findjobs.saveJobMeta(os.path.join(runpath,config.jobFile),meta)
      else:
        pid=findjobs.loadJobMeta(os.path.join(runpath,config.jobFile))['pid'].split("--")
      if not args.fireaway:
        watchJob(pid)
