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

running=True
useServer=False
cacheGplFiles=[]
lastallfd=[]
lastintlen=[]

def findFiles(directory, pattern,dirItems=None):
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

  dir : string
    The directory in which gimmeAll performs a recursive search

  checksize : Boolean
    Compute the cumulative size for all directories. This can
    be VERY slow.

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

  if not running:
    return []

  if jobTypes==None:
    jobTypes=jobhelper.loadJobTypes()

  if useServer:
    import dataserver
    if dir==None:
      dir=[(k,config.login[k]['baseDir']) for k in config.login]
    else:
      if dir is list:
        dir=[d.split(':') for d in dir]
      else:
        dir=[dir.split(':')]
    allJobs=[]
    for d in dir:
      if d[1]=='':
        d[1]=config.login[d[0]]['baseDir']
      try:
        allJobs+=dataserver.makeRequest(config.login[d[0]]['IP'],config.login[d[0]]['port']\
                                      ,('g',(d[1],checksize,jobTypes,d[0]),config.varMods))
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
  for fullname in findFiles(dir,config.jobFile):
    if not running:
      break
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
    jobtype=jobTypes.find('jobtype[@name="{}"]'.format(curset['meta']['jobtype']))
    if jobtype==None:
      print >>sys.stderr,"unknown jobtype {}".format(curset['meta']['jobtype'])
      continue

    # has the input file changed since last gimmeAll pass?
    if getmtime(pJoin(path,curset['meta']['input']))>0:#curset['checktime']:
      filedata={}
      filesets={}
      curset['params']=filedata
      curset['psets']=filesets
      if jobtype.attrib['inputtype']=='text':
        inputContent=open(pJoin(path,curset['meta']['input']),'r').read()

        if jobtype.attrib['name'] in jobFields:
          fields=jobFields[jobtype.attrib['name']]
        else:
          fields=[]
          for i in jobtype.findall("field"):
            fields.append([i.attrib["name"]\
                           ,re.compile(i.text.replace("FLRE",floatre))\
                           ,int(i.attrib["count"])])
          jobFields[jobtype.attrib['name']]=fields
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
      elif jobtype.attrib['inputtype']=='python':
        try:
          params=jobhelper.getInput(curset['meta']['input'],path,curset['meta'].get('seqind',None))
          for k in jobtype.findall("variable"):
            name=k.attrib['name']
            filedata[name]=getattr(params,name,'nan')
        except SyntaxError:
          pass
    else:
      filedata=curset['params']
      filesets=curset['psets']
    filedata['dirsize']='-1'

    try:
      successtime=getmtime(pJoin(path,jobtype.find('success').attrib['filename']))
      if successtime>curset['logtime']:
        curset['logtime']=successtime
        if (checksize):
          from subprocess import check_output
          curset['meta']['dirsize']=check_output(["du",path]).split("\t")[0]
        if re.search(jobtype.find('success').text,\
                     open(pJoin(path,jobtype.find('success').attrib['filename']),'r').read()):
          curset['meta']['suc']=True
    except (IOError,OSError):
      curset['meta']['suc']=False
    curset['checktime']=curtime
  print >>sys.stderr,""
  print >>sys.stderr,'lastallfd:',len(lastallfd),len(allfd)
  return allfd

def getintlen(allfd):
    global lastintlen
    for i in range(len(allfd)):
        pastres=[j for (j,x) in zip(range(len(lastintlen)),lastintlen) if x[2]==allfd[i][2]]
        if (len(pastres)>0):
            curset=pastres[0]
        else:
            lastintlen.append([0,'nan',allfd[i][2]])
            curset=len(lastintlen)-1
        try:
            t=getmtime(allfd[i][2]+"/BELout")
            if (not ('BEL' in allfd[i][1])) or (str(allfd[i][1]['BEL'])=='nan'):
                allfd[i][1]['BEL']='some'
            if ((t>lastintlen[curset][0]) or (lastintlen[curset][1]=='nan')):
              from subprocess import check_output
              grepOut=check_output("grep '^R' "+allfd[i][2]+"/BELout | tail -n 1",\
                                   stderr=None,shell=True)
              res=str(float(grepOut.split()[1]))
            # allfd[i][1]['intlen']=str(float(check_output(["tail","-n","1",allfd[i][2]+"/"+"BELout"],stderr=None).split(" ")[1]))
              lastintlen[curset][0]=t
            else:
              res=lastintlen[curset][1]
        except OSError:
            allfd[i][1]['BEL']='nan'
            res='nan'
        except IndexError as ex:
#            print >>sys.stderr,str(ex)
            res='nan'
        lastintlen[curset][1]=res
        allfd[i][1]['intlen']=res
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

def applyFilters(allfd,filters):
  print >>sys.stderr,"Starting with {} fds.".format(len(allfd))
  for f in filters:
    if len(f)>2:
      sel=f[2]
    else:
      sel='params'
    if len(f)>1:
      allfd=filter(lambda x:(f[1] in x[sel]) and (f[0](x)),allfd)
    else:
      allfd=filter(lambda x:f[0](x),allfd)
    print >>sys.stderr,"Reduced to {} due to filter {}".format(len(allfd),f[1:])
#    print >>sys.stderr,[x[1]['opname'] for x in allfd],[x[2] for x in allfd]
    if (len(allfd)==0):
      try:
        key=f[1]
        allvalues=jobhelper.uniq([x[sel][key] for x in allfd])
      except KeyError:
        print >>sys.stderr, "Key '"+key+"' not valid."
        try:
          print >>sys.stderr, "available keys : "+str(allfd[0][sel].keys())
        except IndexError:
          print >>sys.stderr, "list is empty"
        return []
      print >>sys.stderr, "Filter '"+str(f[0])+"' resulted in empty list"
      frame,filename,line_number,function_name,lines,index=\
          inspect.getouterframes(inspect.currentframe())[1]
      print jobhelper.printerr("at {0} line {1}".format(filename,line_number),col=31)
      print >>sys.stderr, "available values : "+str(allvalues)
      return []
  return allfd

def printJobs(allJobs,dnum=0,specialDir=None,lim=20,getIntlen=False):
  try:
    metas=[x['meta'] for x in allJobs[dnum:dnum+1]]
    params=[x['params'] for x in allJobs[dnum:dnum+1]]
  except TypeError:
    metas=[allJobs[i]['meta'] for i in dnum if i<len(allJobs)]
    params=[allJobs[i]['params'] for i in dnum if i<len(allJobs)]

  if specialDir!=None:
    metas+=[x['meta'] for x in allJobs if x['meta']['dir']==d for d in specialDir]
    params+=[x['params'] for x in allJobs if x['meta']['dir']==d for d in specialDir]
 
  allJobs=allJobs[:lim]
  if (getIntlen):
    allJobs=getintlen(allJobs)
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
      print >>sys.stderr,len(allJobs)-1-ind,fd['meta']['node']+':'+fd['meta']['dir'],fd['meta']['time']\
        ,[(a,fd['params'][a]) for a in ukeys],
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
  return \
    # the directory is a valid run directory
  (isfile(pJoin(dir,"output")) \
    # the file does not exist
  and (((not isfile(pJoin(dir,name))) \
        # it is older than output
        or (getmtime(pJoin(dir,name))<getmtime(pJoin(dir,"output"))))\
       # the file is younger than "time"
       or ((time!=0) and (getmtime(pJoin(dir,name))<time))
       # has dependencies and
       or ((redoCommand!=None) and (redoCommand[2]!=None) \
           # at least one of them is younger
           and array([isfile(pJoin(dir,dep))\
                      and (getmtime(pJoin(dir,dep))>getmtime(pJoin(dir,name)))\
                    for dep in redoCommand[2].split(',')]).any())))
           
def openFile(dir,name,levelac=[""],levelom=[],fielddrop=[],fieldsplit=' +',\
             redo=True,addparam="",forceReDo=False,redoCommand=None):
  global cacheGplFiles

  if not running:
    return []

  if (forceReDo or redo) and (redoCommand==None):
    jobTypes=jobhelper.loadJobTypes()

    for i in jobTypes.findall("command"):
      if i.attrib["name"]==name:
        redoCommand=[i.text,i.attrib["out"],i.attrib.get("depend",None)]

  if useServer:
    try:
      if dir['node']==None:
        raise ValueError("Can't use a dataserver since there isno 'node' info in the meta set")
    except TypeError:
      raise TypeError("If you want me to use a dataserver to retrieve data,\n"\
        +"you need to supply the whole 'meta' set instead of just the directory")
      
    import dataserver
    return dataserver.makeRequest\
      (config.login[dir['node']]['IP'],config.login[dir['node']]['port'],\
       ('o'\
        ,(dir,name,levelac,levelom,fielddrop,fieldsplit,redo,addparam,forceReDo,redoCommand)\
        ,config.varMods))

  if isinstance(dir,dict):
    meta=dir
    dir=meta['dir']

  redone=False

  ident=str(dir)+str(name)+str(levelac)+str(levelom)+str(fielddrop)+str(fieldsplit)
  if ((forceReDo) or (redo and testfile(dir,name,redoCommand=redoCommand))):
    if redoCommand!=None:
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

  if (redone or not ident in [x[0] for x in cacheGplFiles] or 
      (testfile(dir,name,[x[2] for x in cacheGplFiles if x[0]==ident][0]))):
    myfile=open(pJoin(dir,name),'r')
    levelct=[0]*len(levelac)
    lacre=[re.compile(a) for a in levelac]
    lomre=[re.compile(a) for a in levelom]
    fdre=[re.compile(a) for a in fielddrop]
    splitre=re.compile(fieldsplit)
    fieldlen=0
    irn=0
    filelength=os.path.getsize(dir+"/"+name)
    levelInd=[[] for i in levelac]
    alldata=list()
    ins=myfile.readline()
    while (ins != ""):
      if not running:
        break
      ins=ins.rstrip("\n")
      for i in range(len(levelac)):
        if ((levelac[i] == "") or (lacre[i].search(ins) != None))\
           and ((i>=len(levelom)) or (levelom[i]=="") or (lomre[i].search(ins) == None)):
          if i==0:
            fields=[f for f in splitre.split(ins) if (f!='') and (not f in fielddrop)]
            if (fieldlen<len(fields)):
              fieldlen=len(fields)
            alldata.append(fields)
          else:
            levelInd[i].append(levelct[i-1])
            levelct[i-1]=0
          levelct[i]+=1
      filePos=myfile.tell()*100/filelength
      ins=myfile.readline()
      irn+=1
    myfile.close()

    # print 'alldata',levelInd,levelct

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
    except:
      # traceback.print_exc(file=sys.stderr)
      adLen=len(alldata)
      try:
        levelct.reverse()
        levelct.append(fieldlen)
        result=np.resize(np.array(alldata),levelct)
        cacheGplFiles.append((ident,result,getmtime(pJoin(dir,name))))
      except:
        result=np.zeros(0)
        traceback.print_exc(file=sys.stderr)
        print >>sys.stderr,len(levelom)
        print >>sys.stderr,levelct
        print >>sys.stderr,adLen
        print >>sys.stderr,irn
    # print alldata[len(alldata)-1]
    # alldata=[[1,2],[3,4],[5,6],[7,8],[9,10],[11,12]]
    if (len(cacheGplFiles)>500):
        cacheGplFiles.pop(0)
  else:
      print >>sys.stderr,'.',
      result=[x[1] for x in cacheGplFiles if x[0]==ident][0]
  return result

if __name__ == "__main__":
  print "findjobs can't be run as a program!"
