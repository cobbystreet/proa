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
import signal
import re
import new
import sys
import traceback
import numpy as np
import cProfile
import plot
import subprocess
import xml.etree.ElementTree as ET

import nogui

import jobhelper
config=jobhelper.loadConfig()

try:
  import wx
except ImportError:
  raise ImportError,"The wxPython module is required to run this program in GUI mode."

from StyledTextCtrl import PythonSTC;

class proa(wx.Frame):
  def __init__(self,parent,id,title):
    wx.Frame.__init__(self,parent,id,title)
    self.parent = parent
    self.data={}
    self.extra={}
    self.ukeys={}
    self.allstores={}
    self.alldata={}
    self.myreset=None
    self.initialize()

  def initialize(self):
    from wx.lib.newevent import NewEvent
    box=wx.GridSizer()
    sizer = wx.GridBagSizer()
    self.maxSC=4
    self.plotsets=ET.ElementTree(ET.Element("allsets"))
    self.actPS="default"

    panel=wx.Panel(self,-1)
    panel.SetAutoLayout(True)

    box.Add(panel,1,wx.EXPAND)

    # All of these items are right of the "reset" text input box.

    self.rButton = wx.Button(panel,-1,label="Reset")
    sizer.Add(self.rButton, (0,self.maxSC))
    self.Bind(wx.EVT_BUTTON, self.OnPressReset, self.rButton)

    self.setCB=wx.ComboBox(self,-1,self.actPS,style=wx.CB_DROPDOWN)
    sizer.Add(self.setCB,(1,self.maxSC))
    self.Bind(wx.EVT_TEXT_ENTER,self.OnSelectSet,self.setCB)
    self.Bind(wx.EVT_COMBOBOX,self.OnSelectSet,self.setCB)

    self.useServerCB = wx.CheckBox(panel,-1,"Use DataServer")
    self.Bind(wx.EVT_CHECKBOX, self.OnClickUSCB, self.useServerCB)
    sizer.Add(self.useServerCB,(2,self.maxSC))

    self.restartButton = wx.Button(panel,-1,label="Restart Server")
    sizer.Add(self.restartButton, (3,self.maxSC))
    self.Bind(wx.EVT_BUTTON, self.OnPressRestart, self.restartButton)

    resetHeight=4

    self.reset = PythonSTC(panel,-13)
    self.reset.SetText(u"\n"*string.count(config.resetPrefix,"\n")\
                       +"\nprint >>gnuplot,'reset'")
    self.reset.SetUseTabs(False)
    self.reset.SetTabWidth(2)
    self.reset.HideLines(0,string.count(config.resetPrefix,"\n"))
    sizer.Add(self.reset,(0,0),(resetHeight,self.maxSC),wx.EXPAND)
    self.reset.Bind(wx.EVT_CHAR, self.OnKey)

    # Now comes everything right of the "plot" text input box. 

    self.pButton = wx.Button(panel,-1,label="Plot")
    sizer.Add(self.pButton, (resetHeight,self.maxSC))
    self.Bind(wx.EVT_BUTTON, self.OnPressPlot, self.pButton)

    self.raiseplot = wx.CheckBox(panel,-1,"Raise GnuPlot")
    self.raiseplot.SetValue(True)
    sizer.Add(self.raiseplot,(resetHeight+1,self.maxSC))

    plotHeight=2

    self.plot = PythonSTC(panel,-1)
    self.plot.SetText(u"\n"*string.count(config.plotPrefix,"\n")+\
                      "\nprint >>gnuplot,'plot x'")
    self.plot.SetUseTabs(False)
    self.plot.SetTabWidth(2)
    self.plot.HideLines(0,string.count(config.plotPrefix,"\n"))
    sizer.Add(self.plot,(resetHeight,0),(plotHeight,self.maxSC),wx.EXPAND)
    self.plot.Bind(wx.EVT_CHAR, self.OnKey)

    # Everything below here is below the "plot" text input box. 

    self.scs=[]
    self.scids=[]
    self.mystore=[]
    self.allstores={}
    for i in range(self.maxSC):
        self.scs.append(wx.SpinCtrl(panel,-1))
        self.scids.append(self.scs[i].GetId())
        self.scs[i].SetRange(0,10000)
        sizer.Add(self.scs[i], (resetHeight+plotHeight,i))
        self.Bind(wx.EVT_SPINCTRL,self.OnSC,self.scs[i])
        self.scs[i].Bind(wx.EVT_CHAR, self.OnKey)
    self.scs[1].SetRange(-3,2)


    self.label = wx.StaticText(panel,-1,label=u'Hello !\nagain')
    self.label.SetBackgroundColour(wx.BLUE)
    self.label.SetForegroundColour(wx.BLACK)
    self.label.SetFont(wx.Font(7,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,\
                               wx.FONTWEIGHT_NORMAL))
    sizer.Add( self.label, (resetHeight+plotHeight+1,1),(1,self.maxSC), wx.EXPAND )

    self.progress = wx.Gauge(self, -1, 100)
    sizer.Add( self.progress, (resetHeight+plotHeight+1,0),(1,1), wx.EXPAND)


    self.datasize=wx.StaticText(panel,-1,label=u'none loaded')
    self.datasize.SetFont(wx.Font(8,wx.FONTFAMILY_DEFAULT,\
                                  wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL))
    sizer.Add( self.datasize, (resetHeight+plotHeight+2,0),(1,self.maxSC), wx.EXPAND )


    sizer.AddGrowableCol(self.maxSC-1)
    sizer.AddGrowableRow(resetHeight-1)
    sizer.AddGrowableRow(resetHeight+plotHeight-1)
    panel.SetSizerAndFit(sizer)
    self.SetSizerAndFit(box)
    self.reset.SetFocus()
    self.Show(True)

    try:
      self.plotsets.parse("plot.xml")
      for i in self.plotsets.findall("plotset"):
        self.setCB.Append(i.attrib["name"])
      self.setCB.SetValue(self.setCB.GetItems()[0])
      self.actPS=self.setCB.GetValue()
    except IOError:
      self.setCB.Append(self.actPS)

    try:
      dataServer=self.plotsets.findall("dataServer")[0]
      self.useServer=dataServer.attrib['use']=='True'
    except IndexError:
      a=ET.SubElement(self.plotsets.getroot(),"dataServer")
      a.set("use","True")
      self.useServer=True
    self.useServerCB.SetValue(self.useServer)

    # Geometry of the main window
    geometry=self.plotsets.find("geometry")
    if geometry!=None:
      self.MoveXY(int(geometry.attrib["x"]),int(geometry.attrib["y"]))
      self.SetSizeWH(int(geometry.attrib["width"]),int(geometry.attrib["height"]))

    # Geometry of the gnuplot window
    geometry=self.plotsets.find("gplGeometry")
    if geometry!=None:
      self.gplGeometry=[int(geometry.attrib[k]) for k in ["x","y","width","height"]]
    else:
      self.gplGeometry=[-1,-1,-1,-1]

    # Geometry of the Wigner function window
    geometry=self.plotsets.find("wfGeometry")
    if geometry!=None:
      self.wfGeometry=[int(geometry.attrib[k]) for k in ["x","y","width","height"]]
    else:
      self.wfGeometry=[-1,-1,-1,-1]


    self.Bind(wx.EVT_CLOSE, self.OnExit)

    # These are for filling a window that shows pixel data
    self.RecDataEvent, self.EVT_REC_DATA = NewEvent()
    self.Bind(self.EVT_REC_DATA, self.OnRecieveData)

    # This is for the resetThread to be able to post results.
    self.DataLabelEvent, self.EVT_DATA_LABEL = NewEvent()
    self.Bind(self.EVT_DATA_LABEL, self.OnDataLabelChange)

  def SetFirstSpinRange(self,a):
    self.scs[0].SetRange(0,a)

  def OnExit(self,event):
    if (self.myreset!=None) and (self.myreset.running):
      self.myreset.stop()
    plot.emptyStore()

    self.saveSet()

    gplGeometry=plot.doRaise(config.gplID)
    if (gplGeometry!=None):
      geometry=self.plotsets.find("gplGeometry")
      if geometry==None:
        geometry=ET.SubElement(self.plotsets.getroot(),"gplGeometry")
      geometry.set("x",str(gplGeometry[0]))
      geometry.set("y",str(gplGeometry[1]))
      geometry.set("width",str(gplGeometry[2]))
      geometry.set("height",str(gplGeometry[3]))
    wfGeometry=plot.doRaise("WignerFunction")
    if (wfGeometry!=None):
      geometry=self.plotsets.find("wfGeometry")
      if geometry==None:
        geometry=ET.SubElement(self.plotsets.getroot(),"wfGeometry")
      geometry.set("x",str(wfGeometry[0]))
      geometry.set("y",str(wfGeometry[1]))
      geometry.set("width",str(wfGeometry[2]))
      geometry.set("height",str(wfGeometry[3]))

    (width,height)=self.GetSizeTuple()
    (x,y)=self.GetScreenPositionTuple()
    geometry=self.plotsets.find("geometry")
    if geometry==None:
      geometry=ET.SubElement(self.plotsets.getroot(),"geometry")
    geometry.set("width",str(width))
    geometry.set("height",str(height))
    geometry.set("x",str(x))
    geometry.set("y",str(y))

    dataServer=self.plotsets.find('dataServer')
    if dataServer==None:
      dataServer=ET.SubElement(self.plotsets.getroot(),'dataServer')
    dataServer.set('use',['False','True'][self.useServer])
    self.plotsets.write("plot.xml")
    self.Destroy()

  def saveSet(self):
    # find name of last set in plotset list
    a=self.plotsets.find("plotset[@name='"+self.actPS+"']")
    if (a == None):
      # or create a new one otherwise
      a=ET.SubElement(self.plotsets.getroot(),"plotset")
      a.set("name",self.actPS)

    # try to save cursor position
    cursorPos=a.find('cursor')
    if cursorPos==None:
      cursorPos=ET.SubElement(a,"cursor")
    cursorPos.set('reset',str(self.reset.GetCurrentPos()))
    cursorPos.set('plot',str(self.plot.GetCurrentPos()))

    # try to save value of "reset" text
    rText=a.find("reset")
    if rText==None:
      rText=ET.SubElement(a,"reset")
    rText.text=string.lstrip(self.reset.GetText(),"\n")

    # try to save value of "plot" text
    pText=a.find("plot")
    if pText==None:
      pText=ET.SubElement(a,"plot")
    pText.text=string.lstrip(self.plot.GetText(),"\n")

    spins=a.findall("sc")
    for i in range(self.maxSC):
      if i<len(spins):
        b=spins[i]
      else:
        b=ET.SubElement(a,"sc")
      b.text=str(self.scs[i].GetValue())

  def OnSelectSet(self,event):
    # The value of the comboBox has changed

    # find name of new set in combobox list
    try:
      t=self.setCB.GetItems().index(self.setCB.GetValue())
      # an old one has been selected
    except Exception as inst:
      # or insert otherwise (i.e. a new name has been entered
      self.setCB.Append(self.setCB.GetValue())

    self.saveSet()

    # try to save current data
    try:
      self.alldata[self.actPS]=self.data
    except Exception as inst:
      raise
      self.alldata[self.actPS]={}
    # try to save previously stored plots
    try:
      self.allstores[self.actPS]=self.mystore
    except Exception as inst:
      raise
      self.allstores[self.actPS]=[]

    # select new plotset
    self.actPS=self.setCB.GetValue()
    a=self.plotsets.find("plotset[@name='"+self.actPS+"']")
    if (a!=None):
      self.reset.SetText(u"\n"*string.count(config.resetPrefix,"\n")+a.find("reset").text)
      self.reset.HideLines(0,string.count(config.resetPrefix,"\n")-1)
      self.plot.SetText(u"\n"*string.count(config.plotPrefix,"\n")+a.find("plot").text)
      self.plot.HideLines(0,string.count(config.plotPrefix,"\n")-1)
      spins=a.findall("sc")
      for i in range(self.maxSC):
        if i<len(spins):
          self.scs[i].SetValue(int(spins[i].text))
        else:
          self.scs[i].SetValue(0)
      cursorPos=a.find('cursor')
      if cursorPos!=None:
        self.reset.GotoPos(int(cursorPos.attrib['reset']))
        self.plot.GotoPos(int(cursorPos.attrib['plot']))

    # restore previously saved data
    try:
      self.data=self.alldata[self.actPS]
    except Exception as inst:
      self.data={}
    # restore previously saved plot storage
    try:
      self.mystore=self.allstores[self.actPS]
    except Exception as inst:
      self.mystore=[]

  def OnSC(self,event):
    # One of the spinControls has changed
    self.OnPressPlot(event)

  def OnKey(self,event):
    keycode = event.GetKeyCode()

    # Changing through the plot/reset tabs
    if ((keycode in [wx.WXK_LEFT,wx.WXK_RIGHT]+range(ord("0"),ord("9")))\
        and (event.AltDown())):
      try:
        t=self.setCB.GetItems().index(self.actPS)
      except Exception as inst:
        try:
          t=self.setCB.GetItems().index(self.setCB.GetValue())
        except Exception as inst:
          t=0
      try:
        if (keycode== wx.WXK_LEFT):
          t=t-1
        else:
          if (keycode== wx.WXK_RIGHT):
            t=t+1
            if t>=self.setCB.GetCount():
              t=0
          else:
            t=keycode-ord("0")
        self.setCB.SetValue(self.setCB.GetItems()[t])
        self.OnSelectSet(event)
      except Exception as inst:
        self.label.SetLabel(str(inst))
    else:
      tabOrder=[self.reset,self.plot]+self.scs
      if ((keycode == wx.WXK_UP) and (event.AltDown())):
        for ind in range(len(tabOrder)):
          if (event.GetId()==tabOrder[ind].GetId()):
            tabOrder[ind-1].SetFocus()
            break
      elif ((keycode == wx.WXK_DOWN) and (event.AltDown())):
        for ind in range(len(tabOrder)):
          if (event.GetId()==tabOrder[ind].GetId()):
            tabOrder[(ind+1)%len(tabOrder)].SetFocus()
            break
      else:
        if ((keycode == 13) and (event.ControlDown())):
          if (event.ShiftDown()):
            self.OnPressReset(event)
          else:
            self.OnPressPlot(event)
        elif ((keycode == 27) and (event.ControlDown())):
          if (self.myreset!=None) and (self.myreset.running):
            self.myreset.stop()
        else:
          event.Skip()

  def OnClickUSCB(self,event):
    self.useServer=self.useServerCB.GetValue()

  def OnPressReset(self,event):
    self.datasize.SetLabel("reading data... (Abort with CTRL+ESC)")

    self.saveSet()
    self.plotsets.write("plot.xml")
    if (self.myreset!=None) and (self.myreset.running!=False):
      self.myreset.stop()
    self.myreset=nogui.resetThread(self.reset.GetText()\
                                   ,[self.scs[i].GetValue() for i in range(self.maxSC)]\
                                   ,self,gplid=config.gplID,geometry=self.gplGeometry)

  def OnPressPlot(self,event):
      extracode=""
      if self.raiseplot.IsChecked():
        extracode='\nplot.doRaise("{}")\n'.format(config.gplID)
      self.saveSet()
      self.plotsets.write("plot.xml")

      self.mystore=nogui.doPlot(self,self.plot.GetText()+extracode,self.data\
                                ,[self.scs[i].GetValue() for i in range(self.maxSC)]\
                                ,self.extra,self.allstores,self.ukeys,self.SetFirstSpinRange)
      self.label.SetLabel("")

  def OnPressRestart(self,event):
    import dataserver
    for server in config.login:
      try:
        dataserver.makeRequest(config.login[server]['IP'],config.login[server]['port'],\
                               ('r',))
      except EOFError:
        # of course the connection will drop if we restart
        pass
      except IOError:
        print >>sys.stderr,'dataServer "{}" ({}) is not responding'.\
          format(server,config.login[server]['IP'])
        

  def GetBitmap( self, data):
    import wx
    image = wx.EmptyImage(data.shape[0],data.shape[1])
    image.SetData( data[::-1,:].tostring())
    wxBitmap = image.ConvertToBitmap()       # OR:  wx.BitmapFromImage(image)
    return wxBitmap

  def OnDataLabelChange(self,event):
    self.datasize.SetLabel(event.data)

  def OnRecieveData(self,event):
    """Display Data frame."""
    self.showMiniFrame(self.GetBitmap(event.data))

  def showMiniFrame(self,newBitmap=None):
    size=(200,200)
    pos=(100,100)
    if self.wfGeometry[2]!=-1:
      size=(self.wfGeometry[2],self.wfGeometry[3]) 
      pos=(self.wfGeometry[0],self.wfGeometry[1])
    try:
      self.bitmapWin.SetSize(size)
    except:
      self.bitmapWin = MyFrame(self, -1, "WignerFunction", size=size,pos=pos,\
                               style = wx.DEFAULT_FRAME_STYLE)
    if (newBitmap !=None):
      self.bitmapWin.gimmeBitmap(newBitmap)
      self.bitmapWin.SetSize((newBitmap.GetWidth(), newBitmap.GetHeight()))
    self.bitmapWin.Show(True)
    self.bitmapWin.OnPaint(wx.EVT_PAINT)



class MyFrame(wx.Frame):
  def __init__(self, parent, ID, title, pos=wx.DefaultPosition,
               size=wx.DefaultSize, style=wx.DEFAULT_FRAME_STYLE):

    wx.Frame.__init__(self, parent, ID, title, pos, size, style)
    self.Bind(wx.EVT_PAINT, self.OnPaint)

  def gimmeBitmap(self,newBitmap):
    self.myBitmap=newBitmap

  def OnPaint(self, evt):
    dc = wx.PaintDC(self)
    dc.DrawBitmap(self.myBitmap,    0,  0, True)

  def OnCloseMe(self, event):
    self.Close(True)

  def OnCloseWindow(self, event):
    self.Destroy()


if __name__ == "__main__":
  nogui.init()
  app = wx.App()
  frame = proa(None,-1,'PROA')
  app.MainLoop()


