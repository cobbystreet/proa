import numpy as np
def GWP(x,sig,m,p0,t,q0):
  sigt=np.sqrt(sig/(np.sqrt(2*np.pi)*(sig**2+1j*t/(2*m))))
  wf=sigt*np.exp((2*sig**2*p0+1j*(x-q0))**2/(4*sig**2+1j*t*2/m)-sig**2*p0**2+1j*p0*q0)
  return wf
