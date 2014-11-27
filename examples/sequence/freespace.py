#!/usr/bin/env python

import sys
import os
import numpy as np
import time

import function
import jobhelper

if (len(sys.argv)>3) and (sys.argv[2]=='--seqind'):
  seqInd=[int(i) for i in sys.argv[3].split(',')]
else:
  seqInd=None
params=jobhelper.getInput(sys.argv[1],seqInd=seqInd)

print >>sys.stdout,"starting propagation"

data=open('datafile','w')
x=np.arange(params.xmin,params.xmax,params.xstep)
for t in np.arange(0,params.tE,params.tD):
  y=function.GWP(x,params.sig,params.m,params.p,t,params.q)
  for ax,ay in zip(x,y):
    print >>data,'J',ax,ay.real,ay.imag
  print >>data,'J E'
  print >>sys.stderr,"time:",t
  time.sleep(params.wait)

data.close()
print >>sys.stdout,'finished'
