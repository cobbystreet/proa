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


import os, glob,fnmatch,re,sys,string,traceback,os.path
import jobhelper
import inspect
import scipy
import numpy as np
import time
from os.path import join as pJoin
from os.path import isfile,getmtime

config=jobhelper.loadConfig()

meter=None
running=True
useServer=False
cacheGplFiles=[]
lastallfd=[]
lastintlen=[]

def findFiles(directory, pattern,dirItems=None):
  """
  Iterator over files in a directory that match a patter.

  Parameters:
  -----------

  directory: String
    The directory in which to look for files

  pattern: String
    A shell glob pattern for files to find

  dirItems: List (optional)
    If present, only subdirectory names that are present in
    "dirItems" will be scanned

  Returns:
  --------
  fileIterator: An iterator for the matching files.
  """
  for root, dirs, files in os.walk(directory,followlinks=True):
    if dirItems!=None:
      # assign to contents of dirs instead of dirs to keep the reference
      # for os.walk alive
      dirs[:]=[d for d in dirs if d in dirItems]
    dirs.sort(reverse=True)
    for basename in files:
      if fnmatch.fnmatch(basename, pattern):
        filename = pJoin(root, basename)
        yield filename

def ignoreFields(x,ignore):
  r={}
  for (a,b) in x.items():
    if (not a in ignore):
      r[a]=b
  return r


def uniqrun(seq,ignore=[]):
  seen = set()
  seen_add = seen.add
  r=[]
  for x in seq:
    b=ign_fields(x[1],ignore)
    c=str(b)
    if c not in seen:
      seen.add(c)
      r.append((x[0],b,x[2]))
  return r


floatre="[-+]?[0-9]*\.?[0-9]+([deE][-+]?[0-9]+)?"

def loadJobMeta(filename):
  meta=[line.split("=",1) for line in open(filename,'r').read().split('\n') if line!='']
  return {m[0]:m[1] for m in meta if len(m)==2}

def saveJobMeta(filename,meta):
  file=open(filename,'w')
  print >>file,"\n".join(["{}={}".format(key,value) for key,value in meta.items()])

def gimmeAll(dir=None,checksize=False,jobTypes=None,node=None):
  """
  Search job output data directory "dir" for jobs.

  Parameters
  ----------

  dir : string or list of strings
    The directory in which gimmeAll performs a recursive search
    The interpretation depends on the global variable "useServer"
    if useServer==True:
      "dir" should be of the form "loginnode:path"
      If the "path" part is a relative path, the "loginnode"'1
        "baseDir" will be prepended.
      If the "path" part is missing, the entire "baseDir" on
        the "loginnode" will be searched
    if useServer==False:
      "dir" is taken to be an absolute path on the local machine.

  checksize : Boolean
    Compute the cumulative size for all directories. This can
    be VERY slow.

  meter : class
    A class that will take progress reports

  Returns
  -------
  
  allfd : list of list
    Each entry in the list describes on job found.
    The sub list contains:
      meta data (dictionary)
      parameters (dictionary)
      sets of parameters that occur more than once (dictionary)
      last change of the success file (seconds since epoch)
      last time the job was checked (seconds since epoch)
  """
  global lastallfd
  import xml.etree.ElementTree as ET

  if not running:
    return []

  if jobTypes==None:
    jobTypes=jobhelper.loadJobTypes()

  if useServer:
    if meter!=None:
      meter.reportProgress(False,0,inspect.getouterframes(inspect.currentframe())[1][2])
    import dataserver
    if dir==None:
      dir=[(k,config.login[k]['baseDir']) for k in config.login]
    else:
      if isinstance(dir,list):
        dir=[d.split(':') for d in dir]
      else:
        dir=[dir.split(':')]
    allJobs=[]
    for d in dir:
      if not running:
        break
      if (len(d)==1) or (d[1]==''):
        try:
          d[1]=config.login[d[0]]['baseDir']
        except KeyError:
          print >>sys.stderr,"No loginnode with name '{}' found.".format(d[0])
          continue
      if (not os.path.isabs(d[1])):
        d[1]=os.path.join(config.login[d[0]]['baseDir'],d[1])
      try:
        allJobs+=dataserver.makeRequest(config.login[d[0]]['IP'],config.login[d[0]]['port']\
                                        ,('g',(d[1],checksize,jobTypes,d[0]),config.varMods),meter)
      except IOError:
        print >>sys.stderr,'dataServer "{}" ({}) is not responding'.\
          format(d[0],config.login[d[0]]['IP'])
    return allJobs

  if dir==None:
    if node==None:
      print >>sys.stderr,'Either "dir" or "node" parameter need to be given to findjobs:gimmeAll if not run with "useServer"'
      return []
    dir=config.login[node]['baseDir']

  allfd=[]
  if meter!=None:
    meter.reportProgress(True,1,1,'Preparing to scan "{}"'.format(dir))
    allFiles=[f for f in findFiles(dir,config.jobFile)]
    meter.reportProgress(True,1,len(allFiles),'Scanning "{}"'.format(dir))
  else:
    allFiles=findFiles(dir,config.jobFile)
  count=0
  for fullname in allFiles:
    if not running:
      break
    if meter!=None:
      meter.reportProgress(False,1,count)
      count+=1
    path,name=os.path.split(fullname)
    pastres=[x for x in lastallfd if x['meta']['dir']==path]
    curtime=time.time()
    if (len(pastres)>0):
      print >>sys.stderr,'c',
      curset=pastres[0]
    else:
      print >>sys.stderr,'n',
      curset={'meta':{},'params':{},'psets':{},'logtime':0,'checktime':0}
      lastallfd.append(curset)
    allfd.append(curset)

    if getmtime(pJoin(path,config.jobFile))>curset['checktime']:
      curset['meta']=loadJobMeta(pJoin(path,config.jobFile))
      if 'runtype' in curset['meta']:
        # legacy conversion...
        curset['meta']['jobtype']=curset['meta']['runtype']
        del curset['meta']['runtype']
        saveJobMeta(pJoin(path,config.jobFile),curset['meta'])
      curset['meta']['origdir']=curset['meta']['dir']
      curset['meta']['dir']=path
      curset['meta']['suc']=False
      curset['meta']['node']=node
      curset['logtime']=0
    jobTypeName=curset['meta']['jobtype']
    jobType=jobTypes.find('jobtype[@name="{}"]'.format(jobTypeName))
    if jobType==None:
      print >>sys.stderr,"unknown jobtype {}".format(jobTypeName)
      continue

    jobTypeHash=hash(ET.tostring(jobType))

    # Has the input file changed since last gimmeAll pass?
    if ((getmtime(pJoin(path,curset['meta']['input']))>curset['checktime'])\
       # Or has the jobType changed?
       or (jobTypeHash!=curset.get('jobTypeHash',0))):
      filedata={}
      filesets={}
      curset['params']=filedata
      curset['psets']=filesets
      curset['jobTypeHash']=jobTypeHash
      if jobType.attrib['inputtype']=='text':
        inputContent=open(pJoin(path,curset['meta']['input']),'r').read()

        if jobTypeName in jobFields:
          fields=jobFields[jobTypeName]
        else:
          fields=[]
          for i in jobType.findall("field"):
            fields.append([i.attrib["name"]\
                           ,re.compile(i.text.replace("FLRE",floatre))\
                           ,int(i.attrib["count"])])
          jobFields[jobTypeName]=fields
        for f in fields:
          result=f[1].search(filecont)
          if (result):
            if (f[0] in filedata.keys()):
              # this field has been found alread. create a set
              if (f[0] in filesets.keys()):
                filesets[f[0]].append(result.group(f[2]))
              else:
                filesets[f[0]]=[result.group(f[2])]
            else:
              filedata[f[0]]=result.group(f[2])
          else:
            if (not (f[0] in filedata.keys())):
              filedata[f[0]]=float('NaN')
      elif jobType.attrib['inputtype']=='python':
        oldPath=list(sys.path)
        oldMods=list(sys.modules)
        try:
          # Provide an environment as close as to execution as possible.
          sys.path=config.pythonPath+sys.path
          os.chdir(path)
          params=jobhelper.getInput(curset['meta']['input'],path,curset['meta'].get('seqind',None))
          for k in jobType.findall("variable"):
            name=k.attrib['name']
            filedata[name]=getattr(params,name,'nan')
        except Exception:
          print >>sys.stderr,'E',
          pass
        finally:
          sys.path[:]=oldPath # Restore
          # Clean up the module list. Remove anything that might have been loaded
          # while completing the request
          newMods=[mod for mod in sys.modules if not (mod in oldMods)]
          for mod in newMods:
            del sys.modules[mod]
    else:
      filedata=curset['params']
      filesets=curset['psets']
    filedata['dirsize']='-1'

    try:
      successtime=getmtime(pJoin(path,jobType.find('success').attrib['filename']))
      if successtime>curset['logtime']:
        curset['logtime']=successtime
        if (checksize):
          from subprocess import check_output
          curset['meta']['dirsize']=check_output(["du",path]).split("\t")[0]
        if re.search(jobType.find('success').text,\
                     open(pJoin(path,jobType.find('success').attrib['filename']),'r').read()):
          curset['meta']['suc']=True
    except (IOError,OSError):
      curset['meta']['suc']=False
    curset['checktime']=curtime
  if meter!=None:
    meter.reportProgress('last',1,len(allFiles))
  print >>sys.stderr,""
  print >>sys.stderr,'lastallfd:',len(lastallfd),len(allfd)
  return allfd

def myfilter(allfd,key,value="",regex=""):
  try:
    allvalues=jobhelper.uniq([x['params'][key] for x in allfd])
  except KeyError:
    print >>sys.stderr, "Key '"+key+"' not valid."
    try:
      print >>sys.stderr, "available keys : "+str(allfd[0]['params'].keys())
    except IndexError:
      print >>sys.stderr, "list is empty"
    return []
  if (value!=""):
    allfd=filter(lambda x:str(x['params'][key])==str(value),allfd)
    if (len(allfd)==0):
      print >>sys.stderr, "Value '"+str(value)+"' not found in key '"+key+"'"
      frame,filename,line_number,function_name,lines,index=\
          inspect.getouterframes(inspect.currentframe())[1]
      print jobhelper.printerr("at {0} line {1}".format(filename,line_number),col=31)
      print >>sys.stderr, "available values : "+str(allvalues)
      return []
  if (regex!=""):
    allfd=filter(lambda x:re.search(regex,str(x['params'][key])),allfd)
    if (len(allfd)==0):
      print >>sys.stderr, "Regex '"+regex+"' not found in key '"+key+"'"
      frame,filename,line_number,function_name,lines,index=\
          inspect.getouterframes(inspect.currentframe())[1]
      print jobhelper.printerr("at {0} line {1}".format(filename,line_number),col=31)
      print >>sys.stderr, "available values : "+str(allvalues)
      return []
  return allfd

def applyFilters(allJobs,filters):
  """
  Filter a list of jobs.

  Only jobs that pass all filters are returned.

  Parameters:
  ----------

  allJobs: A list of jobs as returned my gimmeAll.

  filters: list of filters
    Each filter can be of either of the following forms
      A general test function: 
        Example:
          lambda x:x['meta']['jobtype']=='freespace'

      A list with the first element a test function, the second a key,
        and the third either 'params' or 'meta'.
        Example:
          [lambda x:x==freespace,'jobtype','meta']

        is equivalent to the above. The advantage of the second form
        is that applyFilters knows which dictionary and which key you
        are referring to and can provide help if the filter results in
        an empty list.
        The third entry in this list may be omitted in which case
        'params' is assumed.

    Note that the contents of the job descriptor are all strings, so
    you may need to do type conversion before numeric comparisons.
    Example:
      [lambda x:float(x)>0.3,'deltaT']

  Returns:
  --------

  filteredJobs : The list of jobs that passed all filters (may be []).
      
  """
  print >>sys.stderr,"Starting with {} fds.".format(len(allJobs))
  for f in filters:
    if isinstance(f,list):
      if len(f)>2:
        sel=f[2]
      else:
        sel='params'
      filteredJobs=filter(lambda x:(f[1] in x[sel]) and (f[0](x[sel][f[1]])),allJobs)
      print >>sys.stderr,"Reduced to {} due to filter {}".format(len(filteredJobs),f[2:0:-1])
    else:
      filteredJobs=filter(lambda x:f(x),allJobs)
    if (len(filteredJobs)==0):
      print >>sys.stderr, "Filter '"+str(f[0])+"' resulted in empty list"
      frame,filename,line_number,function_name,lines,index=\
          inspect.getouterframes(inspect.currentframe())[1]
      print jobhelper.printerr("at {0} line {1}".format(filename,line_number),col=31)
      if isinstance(f,list):
        try:
          key=f[1]
          allvalues=jobhelper.uniq([x[sel][key] for x in allJobs])
          print >>sys.stderr, "available values : "+str(allvalues)
        except KeyError:
          print >>sys.stderr, "Key '"+key+"' not valid."
          try:
            print >>sys.stderr, "available keys : "+str(allJobs[0][sel].keys())
          except IndexError:
            print >>sys.stderr, "list is empty"
#          return []
      return []
    allJobs=filteredJobs
  return allJobs

def selectJobs(allJobs,selection=0,specialDir=None,lim=20):
  """
  Select a certain set of jobs and print their characteristics.

  Parameters:
  -----------

  allJobs: List of jobs as returned from gimmeAll

  selection: Either a maximum index or a list of indices into the allJobs list

  specialDir: A list of directory names
    Jobs from allJobs will be chosen in addition to those specified by "selection"
    if their directory is in "specialDir". Since the indexing in "allJobs" 
    changes as new jobs are processed, "specialDir" can be used to add fixed jobs
    to the selection.
  
  lim: integer, the number of jobs printed to the console. This does not
    affect the selection.

  Returns:
  --------

  metas: List of 'meta' dictionaries of the selected jobs

  params: List of 'params' dictionaries of the selected jobs

  ukeys: List of keys for 'params' whose values change amongst the selected jobs.
    
  """
  try:
    metas=[x['meta'] for x in allJobs[selection:selection+1]]
    params=[x['params'] for x in allJobs[selection:selection+1]]
  except TypeError:
    metas=[allJobs[i]['meta'] for i in selection if i<len(allJobs)]
    params=[allJobs[i]['params'] for i in selection if i<len(allJobs)]

  if specialDir!=None:
    metas+=[x['meta'] for d in specialDir for x in allJobs if x['meta']['dir']==d]
    params+=[x['params'] for d in specialDir for x in allJobs if x['meta']['dir']==d]
 
  allJobs=allJobs[:lim]
  ukeys=getUkeys(allJobs,ignore=['repr'])
  sys.stderr.write('\033[m')
  for ind,fd in enumerate(reversed(allJobs)):
    if (fd['meta'] in metas):
      sys.stderr.write('\033[1m')
    try:
      uniqText=[(a,fd['params'][a]) for a in ukeys if a in fd['params'].keys()].__repr__()
      if (fd['meta'] in metas):
        params[ind]['repr']=uniqText
    except (IndexError,KeyError):
      pass
    try:
      print >>sys.stderr,len(allJobs)-1-ind,fd['meta']['node']+':'+fd['meta']['dir']\
        ,fd['meta']['time'],[(a,fd['params'][a]) for a in ukeys],fd['meta']['desc'],
    except (IndexError,KeyError):
      pass
    if (fd['meta'] in metas):
      sys.stderr.write('\033[m')
    sys.stderr.write('\n')
  print >>sys.stderr,"common",getCommon(allJobs,ukeys)
  return metas,params,ukeys


def getUkeys(allJobs,ignore=[]):
  try:
    keys=[a for a,b in allJobs[0]['params'].items() if (a not in ignore) and (len(jobhelper.uniq([x['params'][a] for x in allJobs if a in x['params'].keys()]))>1)]
    return keys
  except IndexError as ex:
    return []

def getCommon(allJobs,ukeys):
  try:
    return [(a,b) for a,b in allJobs[0]['params'].items() if ((not a in ukeys) and (scipy.array(b)==scipy.array(b)).all())]
  except IndexError as ex:
    return []


def testfile(dir,name,time=0,redoCommand=None):
  return (\
          # the file does not exist
          (not isfile(pJoin(dir,name))) \
           # the file is younger than "time"
          or   ((time!=0) and (getmtime(pJoin(dir,name))>time))
          # has dependencies and
          or ((redoCommand!=None) and (redoCommand[2]!=None) \
              # at least one of them is younger
              and np.array([isfile(pJoin(dir,dep))\
                            and (getmtime(pJoin(dir,dep))>getmtime(pJoin(dir,name)))\
                            for dep in redoCommand[2].split(',')]).any()))

def openFile(dir,name,accept=[""],ommit=[],fielddrop=[],fieldsplit=' +',\
             redo=False,addparam="",forceRedo=False,redoCommand=None,forceReload=False):
  """
  Load a dataset from a file.

  Each input file may contain many different datasets that are
  differentiated by some marker.

  As an example, consider a file with these contents

  J -2.0 0.00272646246511 0.0
  J -1.0 1.41234252291 0.0
  J 0.0 0.00272646246511 0.0
  J 1.0 1.96145336762e-11 0.0
  J 2.0 5.25866406507e-25 0.0
  J E
  J -2.0 0.00227325660377 0.00194231103174
  J -1.0 1.40416016339 -0.0874198500234
  J 0.0 0.00227325660377 0.00194231103174
  J 1.0 -2.84726331593e-11 3.63116650092e-12
  J 2.0 1.04260353846e-24 6.79679755242e-25
  J E
  J -2.0 0.000856650893626 0.00378290065263
  J -1.0 1.38067551289 -0.169968922789
  J 0.0 0.000856650893626 0.00378290065263
  J 1.0 7.28222666532e-11 -4.20170562905e-11
  J 2.0 1.21045750364e-23 7.36211970085e-24
  J E

  This is a dataset identified by the marker 'J' at the beginning of each
  line. The dataset contains three blocks terminated with a line
  containing 'J E'. Each block contains five lines and each line contains
  three fields

  Such a dataset can be thought of as a multi dimensional array of values
  with the dimensions (3 blocks ,5 lines ,3 fields)
  
  To load such a dataset, the "accept" and "ommit" lists need to contain
  regular expressions for each dimension of the dataset.

  In the preceding example, the "accept" fields would be:

  ["J","J E"]

  This means, on the innermost level match all lines that contain the "J"
  character. One level higher up, match all lines that contain the sequence
  "J E". This could continue on with even more sequences to construct
  datasets of higher dimensionality.
  
  But in order not to mach the higher order lines with the lower order
  expressions, the "ommit" list may contain regular expressions that are
  to be excluded. So for instance:

  ["J E",""]

  Thus, the second order identifyer will not be matched on the first
  level. On the second level there is nothing to be omitted in this simple.
  example.
  
  "fieldsplit" may contain a regular expression with which to split each
  line into fields.

  If there are undesired fields in the data set (such as the marker), they
  may be removed by including them in the "fielddrop" list. For the
  present example, this would be

  ["J"]

  With these settings, the entire call would look like this

  findjobs.openFile(job,'datafile',['J ','J E'],['J E'],['J'])

  Parameters:
  -----------

  dir: Either a string with a directory on the local host or a
    'meta' dictionary of a job as returned by gimmeAll

  name: Filename to open

  Returns:
  --------

  alldata: ndarray with the data.
  """
  global cacheGplFiles

  if not running:
    return np.ndarray(0)

  if (forceRedo or redo) and (redoCommand==None):
    jobTypes=jobhelper.loadJobTypes()

    jobType=jobTypes.find('command[@name="{}"]'.format(name))
    if jobType!=None:
      redoCommand=[jobType.text,jobType.attrib["out"],jobType.attrib.get("depend",None)]
    else:
      redo=False
      forceRedo=False

  if useServer:
    try:
      if dir['node']==None:
        raise ValueError("Can't use a dataserver since there is no 'node' info in the meta set")
    except TypeError:
      raise TypeError("If you want me to use a dataserver to retrieve data,\n"\
        +"you need to supply the whole 'meta' set instead of just the directory")
    
    if meter!=None:
      meter.reportProgress(False,0,inspect.getouterframes(inspect.currentframe())[1][2])

    import dataserver
    return dataserver.makeRequest\
      (config.login[dir['node']]['IP'],config.login[dir['node']]['port'],\
       ('o'\
        ,(dir,name,accept,ommit,fielddrop,fieldsplit,redo,addparam,forceRedo,redoCommand,forceReload)\
        ,config.varMods),meter)

  if isinstance(dir,dict):
    meta=dir
    dir=meta['dir']

  redone=False

  ident=str(dir)+str(name)+str(accept)+str(ommit)+str(fielddrop)+str(fieldsplit)
  if ((forceRedo) or (redo and testfile(dir,name,redoCommand=redoCommand))):
    if redoCommand!=None:
      import subprocess
      cmd=redoCommand[0]+' '+addparam
      print >>sys.stderr,cmd
      # Redirect stderr to a pipe and capture so that a pythonic redirection of sys.stderr
      # will be used correctly. This is necessary for the dataserver to capture the command's
      # stderr.
      a=subprocess.Popen(cmd,stdout=open(dir+"/"+redoCommand[1],"w"),\
                         stderr=subprocess.PIPE,cwd=dir,shell=True)
      res=a.communicate()
      print >>sys.stderr,res[1]
      ident+=str(redoCommand)+addparam
    redone=True

  cached=[x for x in cacheGplFiles if x[0]==ident]

  if redone or (len(cached)==0) or (testfile(dir,name,cached[-1][2])) or forceReload:
    fullPath=pJoin(dir,name)
    myfile=open(fullPath,'r')
    mtime=getmtime(fullPath)
    print >>sys.stderr,'opening file "{}"'.format(fullPath),
    levelct=[0]*len(accept)
    lacre=[re.compile(a) for a in accept]
    lomre=[re.compile(a) for a in ommit]
    fdre=[re.compile(a) for a in fielddrop]
    splitre=re.compile(fieldsplit)
    fieldlen=0
    irn=0

    if meter!=None:
      
      filelength=os.path.getsize(fullPath)
      filepos=0
      meter.reportProgress(True,1,filelength,'Opening file "{}"'.format(fullPath))

    levelInd=[[] for i in accept]
    alldata=list()
    ins=myfile.readline()
    totalAccept=np.zeros(len(accept))
    totalOmmit=np.zeros(len(accept))
    while (ins != ""):
      if meter!=None:
        filepos+=len(ins) # +1 for the removed \n
        meter.reportProgress(False,1,filepos)
      if not running:
        break
      ins=ins.rstrip("\n")
      for i in range(len(accept)):
        if ((accept[i] == "") or (lacre[i].search(ins) != None)):
          totalAccept[i]+=1
          if ((i>=len(ommit)) or (ommit[i]=="") or (lomre[i].search(ins) == None)):
            if i==0:
              fields=[f for f in splitre.split(ins) if (f!='') and (not f in fielddrop)]
              if (fieldlen<len(fields)):
                fieldlen=len(fields)
              alldata.append(fields)
            else:
              levelInd[i].append(levelct[i-1])
              levelct[i-1]=0
            levelct[i]+=1
          else:
            totalOmmit[i]+=1

      ins=myfile.readline()
      irn+=1
    myfile.close()
    if meter!=None:
      meter.reportProgress('last',1,filepos,'Done reading. Matrix aligning result')

    print >>sys.stderr,'alldata match',totalAccept,'ommit match',totalOmmit#,levelInd,levelct

    try:
      levelInd[0].append(fieldlen)
      if levelct[-1]>0:
        levelInd.append([levelct[-1]])
      for i in range(len(levelct)-1):
        if (levelct[i]>0):
          levelInd[i+1].append(levelct[i])
      levelInd=levelInd[::-1]
      dims=[max(x) for x in levelInd]
      result=np.zeros(tuple(dims),dtype=object)
      result[...]='nan'
      rind=np.zeros(len(result.shape[:-1]),dtype=int)
      aind=np.zeros(len(result.shape[:-1]),dtype=int)
      adInd=0
      while adInd<len(alldata):
        fl=len(alldata[adInd])
        result[tuple(rind)][:fl]=np.array(alldata[adInd])
        dimInd=rind.shape[0]-1
        while dimInd>=0:
          rind[dimInd]+=1
          if rind[dimInd]<levelInd[dimInd][aind[dimInd]]:
            break
          rind[dimInd]=0
          aind[dimInd]+=1
          dimInd-=1
        adInd+=1
      if len(cached)>0:
        cached[-1][1]=result
        cached[-1][2]=mtime
      else:
        cacheGplFiles.append([ident,result,mtime])
    except:
#      traceback.print_exc(file=sys.stderr)
      adLen=len(alldata)
      try:
        levelct.reverse()
        levelct.append(fieldlen)
        result=np.resize(np.array(alldata),levelct)
      except:
        result=np.zeros(0)
        traceback.print_exc(file=sys.stderr)
        print >>sys.stderr,len(ommit)
        print >>sys.stderr,levelct
        print >>sys.stderr,adLen
        print >>sys.stderr,irn
    # print alldata[len(alldata)-1]
    # alldata=[[1,2],[3,4],[5,6],[7,8],[9,10],[11,12]]
    if (len(cacheGplFiles)>500):
        cacheGplFiles.pop(0)
  else:
    print >>sys.stderr,'c',
    result=cached[-1][1]
  return result

if __name__ == "__main__":
  print "findjobs can't be run as a program!"
