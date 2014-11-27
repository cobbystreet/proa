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

#from scipy import *
import numpy as np 
import sys
import re
import os 
import tempfile
import traceback
import subprocess
import xml.etree.ElementTree as ET
import time
import threading
#from threading import *

tiny=1e-8
filePos=0

storedPlots=[]
toberemoved=[]

def emptyStore(removeFiles=True):
  """
  Remove all collected plots.

  The global storage "storedPlots" is emptied and temporary files
  in the global list "toberemoved" are deleted.

  Parameters
  ----------
  
  removeFiles : boolean
    If removeFiles is given and temporary plot files were created,
    they will be removed from disk.
  """
  global storedPlots
  global toberemoved
  if (removeFiles):
    for aplot in toberemoved:
      try:
        os.remove(aplot)
      except OSError:
        print >>sys.stderr,"can't remove previous plot file "+aplot
    toberemoved=[]
  storedPlots=[]

def storePlot(plotstring,plotdata=None):
  """
  Store a plot for later plotting.

  A gnuplot plot parameter string must be specified. This
  should NOT include a data file specification if data to be
  plotted is supplied as well.

  Parameters
  ----------
  
  plotstring : string
    Gnuplot plot command string. See examples.
  plotdata : ndarray (optional)
    Data to be plot.

  Examples:
  >>> a=arange(10).reshape(10,2)
  >>> storePlot('u 1:2 w lp',a)
  """
  storedPlots.append([plotstring,plotdata])

def plot(x,func,args=tuple(),pComplex=False,name="",extraArgs=""):
  """
  Plot a function.
  """
  try:
    p=func(x,*args)
  except TypeError:
    p=array(func)
  dat=concatenate((x[:,newaxis].real,p[:,newaxis].real,p[:,newaxis].imag),axis=1)
  if (pComplex):
    storePlot("u 2:3 w l lt 1 lw 2 title 'contour'"+extraArgs,dat)
  else:
    storePlot("u 1:2 w l title '"+name+".R'"+extraArgs,dat)
    storePlot("u 1:3 w l title '"+name+".I'"+extraArgs,dat)

def d2plot(func,x=None,y=None,args=tuple(),pmax=None,extraArgs=""):
  """
  Plot a 2D complex valued function.

  The color corresponds to the argument, the shade to the magnitude.

  x: Array to pass as first argument to
  func: The function to be plotted.
  args: Additional arguments to func
  pmax: If defined, this sets the maximum magnitude, everything beyond is capped.
  """
  try:
    p=func(x,*args)
  except TypeError:
    p=array(func)
    if x==None:
      x=np.array(np.meshgrid(arange(p.shape[0]),arange(p.shape[1]))).T
    
  pa=abs(p)
  pp=arctan2(p.imag,p.real)
  def sclim(x):
    y=abs(x)/(pi*2/3)
    y[y>1]=1.
    y=(1.0-y)**0.5
    #y=sin((1.0-y)*pi/2)**1.25
    return y
  r=sclim(pp)
  pp[pp<0]+=2*pi
  g=sclim(pp-pi*2/3)
  b=sclim(pp-pi*4/3)
  l=0.299*r+0.587*g+0.114*b
  l=0.2126*r+0.7152*g+0.0722*b
  l=0.499*r+0.487*g+0.314*b
  l=1.0/l
  l=l/l.max()
  #l=1.0+0.*1./l
  try:
    pm=float(pmax)
  except (ValueError,NameError,TypeError):
    pm=pa.max()
    #	print >>sys.stderr,l.max(),l.min(),r.max(),r.min()
    #	print >>sys.stderr,pm
  pa=pa/pm
  pa[pa>1.0]=1.
  l=pa#*l
  rgb=concatenate((r[:,:,newaxis],g[:,:,newaxis],b[:,:,newaxis]),axis=2)
  rgb[:,:,:]*=l[:,:,newaxis]*256

  dat=concatenate((x,rgb),axis=2)
  storePlot("u 1:2:3:4:5 w rgbimage"+extraArgs,dat)

def runPlots(d2=False,viafile=False,disp=False):
  global storedPlots
  global toberemoved
  if d2:
    plotcmd="splot ";
  else:
    plotcmd="plot ";
  a=0
  for aplot in storedPlots:
    try:
      if (a!=0):
        plotcmd=plotcmd+" , "
      if viafile:
        #tmp=tempfile.NamedTemporaryFile()
        (fd,filename)=tempfile.mkstemp(dir='/dev/shm/')
        afile=os.fdopen(fd,"w")
        aplot.append(afile)
        aplot.append(filename)
        toberemoved.append(filename)
        if (aplot[1] != None):
          plotcmd=plotcmd+ '"'+filename+'" '
      else:
        if disp:
          aplot.append(sys.stderr)
        else:
          aplot.append(None)
          if (aplot[1] != None):
            plotcmd=plotcmd+ '"-" '
      plotcmd=plotcmd+aplot[0]
      a=1
    except AttributeError:
      jobhelper.printerr('Plot error from command "'+aplot[0]+'"')
  if (not viafile):
    print >>gnuplot,plotcmd
  for aplot in storedPlots:
    if (aplot[1] != None):
      try:
        dumpGnuplot(aplot[1],tofile=aplot[2])
      except AttributeError:
        jobhelper.printerr('Data not valid in plot with command "'+aplot[0]+'"')
        if (viafile):
          aplot[2].close()
  if (viafile):
    print >>gnuplot,plotcmd
  gnuplot.flush()
  return plotcmd

def calcWigner(data,x):
  N=x.shape[0]
  dx=x[1]-x[0]
  #division by 2 is to compensate for missing factor 2.0 in FFT exponent
  dp=2.*np.pi/(dx*N)/2.0
  p=np.arange(-N/2,N/2,1.0)*dp
  wig=np.zeros((N,N))#,dtype='complex64')
  # pshift=zeros(N,dtype='complex64')
  # for sind in range(N):
  #       pshift[sind]=exp(1j*p[0]*(dx*sind))
  
  for xind in xrange(N):
    fa=np.concatenate((data[xind:].conj(),np.zeros(xind,dtype=complex)))
    fb=np.concatenate((np.zeros(N-xind-1,dtype=np.complex),\
                        data[:xind+1]))[::-1]
    wigtrans=abs(np.fft.ifft(fa*fb)*dx/np.pi)
    wig[:,xind]=np.fft.fftshift(wigtrans)
  return wig,p

def doRaise(title):
  try:
    activewindow=subprocess.check_output(['xdotool','getactivewindow'])
    output=subprocess.check_output(['xdotool','search','--name',title,'windowactivate',\
                                    'getwindowgeometry','windowactivate',activewindow])
    m=re.search('Position: ([0-9]+),([0-9]+).*Geometry: ([0-9]+)x([0-9]+)',output,re.DOTALL)
    if (m):
      return [int(x) for x in m.groups()]
  except subprocess.CalledProcessError:
    return None

def dumpGnuplot(data,tofile=None):
  """
  Send data to Gnuplot

  The ndarray "data" is sent either to a file or to the gnuplot output
  stream.

  Parameters
  ----------

  data : ndarray
    Data to be sent

  tofile : stream
    Destination for the data. If ==None, the default gnuplot stream
    will be used.
  """
  if tofile==None:
    tofile=gnuplot
  b=[0 for i in data.shape]
  b.pop()
  j=len(b)-1
  try:
    while (j>=0):
      # print b,
      c=data.view()
      for i in b:
        c=c[i]
      #s=" ".join(["{0:+0.8e}".format(float(a)) for a in c])
      c.tofile(tofile," ")
      print >>tofile
      j=len(b)-1
      b[j]+=1
      while ((j>=0) and (b[j]>=data.shape[j])):
        print >>tofile,""
        b[j]=0
        j-=1
        b[j]+=1
  except IndexError:
    j=j
  if (tofile is gnuplot):
    print >>tofile,"e"
  tofile.flush()

