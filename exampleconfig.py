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

# This is an example PROA config file

# Construct a command that executes "cmd", redirects its output to "stdout"
# and prints a job identifier (pid, jobid, ...), and returns, leaving the
# job running in the background
def startCmd(cmd):
  # Compose runcommand for direct starting.

  # /usr/bin/time instead of shell builtin allows for redirecting its output
  # stdbuf makes the output unbuffered
  # cmd is started as a background process in a subshell
  # the pid of cmd is printed to apid then stdout is closed (exec 1>&-)
  # the 'wait' allows time to keep running as long as cmd does
  # a fifo is used so that the surrounding script waits until it actually has the pid

  return "mkfifo apid\n/usr/bin/time -o timeout bash -c 'stdbuf -o 0 -e 0 "+cmd+" >stdout 2>&1 & echo $! >apid ; exec 1>&- ; wait $! >/dev/null' 1>&- 2>&- 0>&- &\ncat apid\nunlink apid"

# How to submit a job "cmd" to be run in directory "path"
# The optional nodearg can be supplied by the caller of runjob.py to
# select a node to run on (if that is possible in the given scenario)
def submitJob(path,cmd,nodearg=None):
  import jobhelper
  # if no node name was specified, find a free one
  if nodearg==None:
    raise ValueError("You need to configure how slave nodes are selected in proaconfig.py")
  else:
    hostname=nodearg
  print 'Running on client:"'+hostname+'"'
  return hostname,jobhelper.sshCall(['./'+cmd],hostname,path,True,noTTY=True).strip(),path

# How to watch the output of the job "pid"
# This has to return a stream like object from which the output can be read
def watchJob(pid):
  import jobhelper
  cmdOut=jobhelper.sshCall(['stdbuf -o 0 tail -n 40','--pid='+pid[1],'-f '+pid[2]+'/stdout']\
                           ,pid[0],noWait=True,catch=True,noTTY=True)
  # cmdOut=subprocess.Popen('stdbuf -o 0 tail -n 40 --pid='+pid[1]+' -f '+pid[2]\
  #                         +'/stdout',\
  #                         shell=True,stdout=subprocess.PIPE,universal_newlines='')
  return cmdOut

# How to kill the output of the job "pid"
def killJob(pid):
  import jobhelper
  jobhelper.sshCall(['kill',pid[1]],pid[0])

# List of available login nodes
# Each login node is represented by its SSH-able host name.
# The dict for each login nodes contains:
#   'baseDir' directory for job output data storage
#   'startCmd' a function for composing a start command
#   'submitJob' a function for submitting a job
#   'watchJob' a function for watching a job
#   'killJob' a function for killing a job
#   'IP' address or name of dataServer
#   'port' of dataServer

raise ValueError("You need to configure login nodes in proaconfig.py!!!!")
login={'localhost':{'baseDir':'/tmp/data'\
                   ,'startCmd':startCmd,'submitJob':submitJob\
                   ,'watchJob':watchJob,'killJob':killJob\
                   ,'IP':'127.0.0.1','port':1128}}

# Name of a subdirectory of "baseDir" to which support files will be pushed
# before job execution.
supportDir='support'

# Paths to append to the PYTHONPATH environment variable on execution of jobs.
pythonPath=['./']

# Libraries to load via LD_PRELOAD
ldPreload=[]

# Description of job types with support files and input parameter fields
jobTypes='jobtypes.xml'

# Identifier file placed in each job directory with job meta data.
jobFile='.job'

# Script file used for creating the environment of the job
jobScript='runscript'

# Directory names used in job output data storage.
dirItems=[str(i) for i in range(10)]

# Limit the PROA program memory consumption
memLimit=2024


# Gnuplot terminal type
terminal='wxt'

# Modules that should be reloaded on every "reset" or "plot" call.
# This is only necessary if you are changing code in them.
varMods=['plot','findjobs','jobhelper']

# These python modules will be made available in the "reset" and "plot" calls.
# See below.
subImports="import re\nimport sys\nfrom scipy import *\nimport subprocess\nimport os\n"

tiny=1e-7

# Prefix for reset call. This is prepended to whatever is in the PROA reset text box.
resetPrefix=subImports+"def myreset(wxapp,s):\n  data={}\n  extra={}\n  ukeys={}\n  tiny="+str(tiny)+"\n  "

# Prefix for plot call. This is prepended to whatever is in the PROA plot text box.
plotPrefix=subImports+"def myplot(wxapp,data,s,extra,allstores,ukeys,SetRange):\n  tiny="+str(tiny)+"\n  "

#Id to be used to identify the plot window of PROA.
gplID="GnuPlot123"
