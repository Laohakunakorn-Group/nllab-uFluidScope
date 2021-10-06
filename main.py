# GUI control of microfluidics-microscope setup
# composed of Wago 750 PLC
# CoolLED pE-300
# and Mad City Labs Microstage
# using PyQt5 and Pymodbus
# N Laohakunakorn, University of Edinburgh, 2021

import serial 
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from pyqtgraph import PlotWidget, plot
import pyqtgraph as pg
pg.setConfigOption('background','w') # set background default to white
pg.setConfigOption('antialias',True)

import time, atexit
from time import sleep
import numpy as np
import traceback, sys
from pymodbus.client.sync import ModbusTcpClient
from ctypes import cdll, c_int, c_uint, c_double

### Configure ethernet communication for Wago
IP = '192.168.1.3' # Set IP address here
client = ModbusTcpClient(IP)
print('IP address of Wago is ', IP)

### Configure serial communication for CoolLED
PORTNAME = 'COM3' # set port name here
ser = serial.Serial() 
ser.baudrate = 9600
ser.port = PORTNAME
ser.bytesize = 8 
ser.parity = 'N'
ser.stopbits = 1
ser.timeout = 0 # second

# MCL functions

class Madstage():
    def __init__(self):
        # provide valid path to MicroDrive.dll. MicroDrive.h and MicroDrive.lib should also be in the same folder
        path_to_dll = './MicroDrive.dll'
        self.madlib = cdll.LoadLibrary(path_to_dll)
        self.handler = self.mcl_start()
        atexit.register(self.mcl_close)
    def mcl_start(self):
        """
        Requests control of a single Mad City Labs Microstage.
        Return Value:
            Returns a valid handle or returns 0 to indicate failure.
        """
        mcl_init_handle = self.madlib['MCL_InitHandle']
        
        mcl_init_handle.restype = c_int
        handler = mcl_init_handle()
        if(handler==0):
            print("MCL init error")
            return -1
        print("Success!")
        return  handler


    def mcl_close(self):
        """
        Releases control of all MCL stages controlled by this instance of the DLL.
        """
        mcl_release_all = self.madlib['MCL_ReleaseAllHandles']
        mcl_release_all()

    def mcl_serial(self):
        """
        Get serial number
        """
        mcl_serial_no = self.madlib['MCL_GetSerialNumber']
        mcl_serial_no.restype = c_int
        return  mcl_serial_no(c_int(self.handler))

    def mcl_move(self,axis,velocity,distance):
        """
        Move axis
        """     
        mcl_movecmd = self.madlib['MCL_MDMove']
        mcl_movecmd.restype = c_int
        return mcl_movecmd(c_uint(axis), c_double(velocity), c_double(distance), c_int(self.handler))

# GUI
# This part does not change:
##########################################
##########################################
class WorkerSignals(QObject):
    '''defines signals from running worker thread
    '''
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)


class Worker(QRunnable):
    '''worker thread
    '''
    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        # Add the callback to our kwargs
        self.kwargs['results'] = self.signals.result

    @pyqtSlot()
    def run(self):
        '''initialise runner function with passed args, kwargs
        '''
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
##########################################
##########################################

class MainWindow(QMainWindow):

    def __init__(self, client, stage, ser, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)


        self.setWindowTitle("Microfluidics microscope controller")
        self.setFixedSize(600,800)

        self.generalLayout = QVBoxLayout()
        self._centralWidget = QWidget(self)
        self.setCentralWidget(self._centralWidget)
        self._centralWidget.setLayout(self.generalLayout)

        # Wago controls
        buttons = {'1': (0, 0),
                   '2': (0, 1),
                   '3': (0, 2),
                   '4': (0, 3),
                   '5': (0, 4),
                   '6': (0, 5),
                   '7': (0, 6),
                   '8': (0, 7),
                   '9': (1, 0),
                   '10': (1, 1),
                   '11': (1, 2),
                   '12': (1, 3),
                   '13': (1, 4),
                   '14': (1, 5),
                   '15': (1, 6),
                   '16': (1, 7),
                   '17': (2, 0),
                   '18': (2, 1),
                   '19': (2, 2),
                   '20': (2, 3),
                   '21': (2, 4),
                   '22': (2, 5),
                   '23': (2, 6),
                   '24': (2, 7)
                  }

        INPUT = '0000'+'0000'+'0000'+'0000'+'0000'+'0000'
        self.A = INPUT

        INPUT = '1111'+'1111'+'1111'+'1111'+'1111'+'1111'
        self.B = INPUT

        INPUT = '1010'+'1010'+'1010'+'1010'+'1010'+'1010'
        self.C = INPUT

        INPUT = '0101'+'0101'+'0101'+'0101'+'0101'+'0101'
        self.D = INPUT

        self._createDisplayBin()
        self._createButtons(buttons)
        self._createStateButton()
        self._createInputField()
        self._createSelectorButtons()
        self._createStartButton()
        self._createStatusField()
        self.getButtonsState()

        # MCL controls
        MCLbuttons = {'-X': (1, 0),
                   '+Y': (0, 1),
                   '-Y': (2, 1),
                   '+X': (1, 2)
                  }

        self._createMCLButtons(MCLbuttons)
        self._createMCLInput()
        self._createVfield()
        self._createDfield()
        self.resetMCLButtonsState()

        # LED controls

        LEDbuttons = {'LED ON': (0, 0)
                  }
        self._createLEDButtons(LEDbuttons)
        self.resetLEDButtonsState()

        self.show()
        self.threadpool = QThreadPool()
        print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

        

    # Auxilary functions
    # For Wago
    def _createStateButton(self):
        self.l = QPushButton("Set state")
        self.l.pressed.connect(self.setButtonsState) # when button pressed, set state
        self.generalLayout.addWidget(self.l)
    def _createStartButton(self):
        self.horizonLayout = QHBoxLayout()
        b1 = QPushButton("Start routine 1")
        b1.pressed.connect(self.runfunction1) # when button pressed, runfunction: this starts an asynchronous loop inside the main loop
        b2 = QPushButton("Start routine 2")
        b2.pressed.connect(self.runfunction2) # when button pressed, runfunction: this starts an asynchronous loop inside the main loop
        b3 = QPushButton("Start routine 3")
        b3.pressed.connect(self.runfunction3) # when button pressed, runfunction: this starts an asynchronous loop inside the main loop
        b4 = QPushButton("Start routine 4")
        b4.pressed.connect(self.runfunction4) # when button pressed, runfunction: this starts an asynchronous loop inside the main loop
        self.bc = QLabel("Command")
        self.horizonLayout.addWidget(b1)
        self.horizonLayout.addWidget(b2)
        self.horizonLayout.addWidget(b3)
        self.horizonLayout.addWidget(b4)
        self.horizonLayout.addWidget(self.bc)
        self.generalLayout.addLayout(self.horizonLayout)
    def _createInputField(self):
        self.horizonLayout = QHBoxLayout()
        self.label = QLabel("Input:")
        self.label.setFixedWidth(120)
        self.k = QLineEdit()
        self.k.setText(self.A)
        self.horizonLayout.addWidget(self.label)
        self.horizonLayout.addWidget(self.k)
        self.generalLayout.addLayout(self.horizonLayout)
    def _createStatusField(self):
        self.horizonLayout = QHBoxLayout()
        self.label = QLabel("Status:")
        self.label.setFixedWidth(120)
        self.b4 = QLineEdit()
        self.b4.setText('OK')
        self.horizonLayout.addWidget(self.label)
        self.horizonLayout.addWidget(self.b4)
        self.generalLayout.addLayout(self.horizonLayout)
    def _createDisplayBin(self):
        self.horizonLayout = QHBoxLayout()
        self.label = QLabel("Binary command:")
        self.label.setFixedWidth(120)
        self.displayBin = QLineEdit()
        self.displayBin.setFixedHeight(35)
        self.displayBin.setAlignment(Qt.AlignRight)
        self.displayBin.setReadOnly(True)
        self.horizonLayout.addWidget(self.label)
        self.horizonLayout.addWidget(self.displayBin)
        self.generalLayout.addLayout(self.horizonLayout)
    def _createSelectorButtons(self):
        self.horizonLayout = QHBoxLayout()
        self.ll = QPushButton("All on")
        self.ll.pressed.connect(lambda: self.writeInputCommand(self.B)) # when button pressed, set state
        self.ll.pressed.connect(self.setButtonsState) # when button pressed, set state
        self.lll = QPushButton("All off")
        self.lll.pressed.connect(lambda: self.writeInputCommand(self.A)) # when button pressed, set state
        self.lll.pressed.connect(self.setButtonsState) # when button pressed, set state
        self.horizonLayout.addWidget(self.ll)
        self.horizonLayout.addWidget(self.lll)
        self.generalLayout.addLayout(self.horizonLayout)
    def _createButtons(self,buttons):
        self.buttons = {}
        buttonsLayout = QGridLayout()

        for btnText, pos in buttons.items():
            self.buttons[btnText] = QPushButton(btnText)
            self.buttons[btnText].setFixedSize(60,60)
            self.buttons[btnText].setCheckable(True)
            self.buttons[btnText].clicked.connect(self.getButtonsState) # when button clicked, get state
            buttonsLayout.addWidget(self.buttons[btnText], pos[0], pos[1])
        self.generalLayout.addLayout(buttonsLayout)

    # For MCL
    def _createMCLInput(self):
        self.horizonLayout = QHBoxLayout()
        self.label = QLabel("Input:")
        self.label.setFixedWidth(120)
        self.MCL = QLineEdit()
        self.horizonLayout.addWidget(self.label)
        self.horizonLayout.addWidget(self.MCL)
        self.generalLayout.addLayout(self.horizonLayout)

    def _createVfield(self):
        self.horizonLayout = QHBoxLayout()
        self.label = QLabel("Velocity (mm/s):")
        self.label.setFixedWidth(120)
        self.V = QLineEdit()
        self.V.setText('1')
        self.horizonLayout.addWidget(self.label)
        self.horizonLayout.addWidget(self.V)
        self.generalLayout.addLayout(self.horizonLayout)

    def _createDfield(self):
        self.horizonLayout = QHBoxLayout()
        self.label = QLabel("Distance (um):")
        self.label.setFixedWidth(120)
        self.D = QLineEdit()
        self.D.setText('50')
        self.horizonLayout.addWidget(self.label)
        self.horizonLayout.addWidget(self.D)
        self.generalLayout.addLayout(self.horizonLayout)

    def _createMCLButtons(self,MCLbuttons):
        self.MCLbuttons = {}
        MCLbuttonsLayout = QGridLayout()

        for btnText, pos in MCLbuttons.items():
            self.MCLbuttons[btnText] = QPushButton(btnText)
            self.MCLbuttons[btnText].setFixedSize(60,60)
            self.MCLbuttons[btnText].setCheckable(True)
            self.MCLbuttons[btnText].clicked.connect(self.getMCLButtonsState) # when button clicked, get state
            MCLbuttonsLayout.addWidget(self.MCLbuttons[btnText], pos[0], pos[1])
        self.generalLayout.addLayout(MCLbuttonsLayout)

    # for LED
    def _createLEDButtons(self,LEDbuttons):
        self.LEDbuttons = {}
        LEDbuttonsLayout = QGridLayout()

        for btnText, pos in LEDbuttons.items():
            self.LEDbuttons[btnText] = QPushButton(btnText)
            self.LEDbuttons[btnText].setFixedSize(100,60)
            self.LEDbuttons[btnText].setCheckable(True)
            self.LEDbuttons[btnText].clicked.connect(self.getLEDButtonsState) # when button clicked, get state
            LEDbuttonsLayout.addWidget(self.LEDbuttons[btnText], pos[0], pos[1])
        self.generalLayout.addLayout(LEDbuttonsLayout)



    # slots

    # For Wago
# Must not let multiple routines start in parallel
    def runfunction1(self):
        worker = Worker(self.executefn1) # instantiate the Runnable subclass
        worker.signals.result.connect(self.action) # print the output each time a result comes in
        worker.signals.finished.connect(self.thread_complete) # then run thread complete
        # Execute
        self.threadpool.start(worker) # start
    def runfunction2(self):
        worker = Worker(self.executefn2) # instantiate the Runnable subclass
        worker.signals.result.connect(self.action) # print the output each time a result comes in
        worker.signals.finished.connect(self.thread_complete) # then run thread complete
        # Execute
        self.threadpool.start(worker) # start
    def runfunction3(self):
        worker = Worker(self.executefn3) # instantiate the Runnable subclass
        worker.signals.result.connect(self.action) # print the output each time a result comes in
        worker.signals.finished.connect(self.thread_complete) # then run thread complete
        # Execute
        self.threadpool.start(worker) # start
    def runfunction4(self):
        worker = Worker(self.executefn4) # instantiate the Runnable subclass
        worker.signals.result.connect(self.action) # print the output each time a result comes in
        worker.signals.finished.connect(self.thread_complete) # then run thread complete
        # Execute
        self.threadpool.start(worker) # start

    # Experimental routines programmed here
    def executefn1(self,results):
        for i in range(10):
            results.emit('A')
            time.sleep(1)
            results.emit('B')
            time.sleep(2)

    def executefn2(self,results):
        for i in range(10):
            results.emit('C')
            time.sleep(1)
            results.emit('D')
            time.sleep(1)

    def executefn3(self,results):
        for i in range(10):
            results.emit('A')
            time.sleep(1)
            results.emit('B')
            time.sleep(1)
            results.emit('C')
            time.sleep(2)

    def executefn4(self,results):
        for i in range(10):
            results.emit('A')
            time.sleep(0.5)
            results.emit('B')
            time.sleep(0.5)
            results.emit('C')
            time.sleep(0.5)
            results.emit('D')
            time.sleep(1)

    def thread_complete(self):
        print("Thread complete!")

    # Commands programmed here
    def action(self,results):
        if results=='A':
            self.bc.setText(results) # update text box
            self.writeInputCommand(self.A)
            self.setButtonsState()
        elif results=='B':
            self.bc.setText(results) # update text box
            self.writeInputCommand(self.B)
            self.setButtonsState()
        elif results=='C':
            self.bc.setText(results) # update text box
            self.writeInputCommand(self.C)
            self.setButtonsState()
        elif results=='D':
            self.bc.setText(results) # update text box
            self.writeInputCommand(self.D)
            self.setButtonsState()

    def getButtonsState(self):
        # read state of buttons and display bin/Hex
        state = []
        for btnText, pos in self.buttons.items():
            state.append(int(self.buttons[btnText].isChecked()))
        binstring = ''.join(['1' if x else '0' for x in state])
        self.displayBin.setText(binstring)
        self.displayBin.setFocus()
        self.b4.setText('OK')

        # Write command to Wago
        INPUT = binstring 
        for j in range(len(INPUT)):
            status = bool(int(INPUT[j]))
            client.write_coil(j, status)


# Must do proper error checking here
    def setButtonsState(self):
        # set buttons according to state specified in k
        inputs = self.k.text()
        if len(inputs)!=24:
            self.b4.setText('Error! Require 24-bit binary input')
            self.k.setText(self.A)
        else:
            j = 0
            for btnText, pos in self.buttons.items():
                self.buttons[btnText].setChecked(bool(int(inputs[j])))
                j+=1
            self.getButtonsState()
            self.b4.setText('OK')

    def writeInputCommand(self,inputs):
        # write programmatically defined inputs to k
        self.k.setText(inputs)


    # For MCL

    def getMCLButtonsState(self):
        # read state of buttons and trigger actions
        state = []
        for btnText, pos in self.MCLbuttons.items():
            state.append(int(self.MCLbuttons[btnText].isChecked()))
        binstring = ''.join(['1' if x else '0' for x in state])
        self.MCL.setText(binstring)

        # Write command
        INPUT = binstring 
        self.move(INPUT)
        self.resetButtonsState() # reset all buttons
        
    def resetMCLButtonsState(self):
        for btnText, pos in self.MCLbuttons.items():
                self.MCLbuttons[btnText].setChecked(False)

    def move(self,INPUT):
#       -X = 1000 -> +M1
#       +X = 0001 -> -M1
#       -Y = 0010 -> +M2
#       +Y = 0100 -> -M2

        if INPUT == '1000':
            axis = 1
            distance = float(self.D.text())*(1/1000) # convert to mm
        elif INPUT == '0001':
            axis = 1
            distance = -float(self.D.text())*(1/1000) # convert to mm
        elif INPUT == '0100':
            axis = 2
            distance = -float(self.D.text())*(1/1000) # convert to mm
        elif INPUT == '0010':
            axis = 2
            distance = float(self.D.text())*(1/1000) # convert to mm
        velocity = float(self.V.text())       
        stage.mcl_move(axis,velocity,distance)
        print('Move', axis, velocity, distance)


    # For LED

    def getLEDButtonsState(self):
        # read state of buttons and trigger actions
        state = []
        for btnText, pos in self.LEDbuttons.items():
            state.append(int(self.LEDbuttons[btnText].isChecked()))
        binstring = ''.join(['1' if x else '0' for x in state])

        # Write command
        INPUT = binstring 
        if bool(int(INPUT)):
            print('LED on')
            CMD = 'CSN\n'
            ser.write(CMD.encode())
        else:
            print('LED off')
            CMD = 'CSF\n'
            ser.write(CMD.encode())
     
    def resetLEDButtonsState(self):
        for btnText, pos in self.LEDbuttons.items():
                self.LEDbuttons[btnText].setChecked(False)

def handle_exit():
#   carry out exit functions here
    ser.close()
    print('Port closed')
    print('Exiting')

def main(client,stage,ser):

#   Startup items here
    print('Starting Wago')

    # Open port
    ser.open()
    print('Serial port open')

#   Exit items here
    atexit.register(handle_exit)

    # here is the app running
    app = QApplication(sys.argv)

    window = MainWindow(client,stage,ser)
    window.show()

    sys.exit(app.exec_())


if __name__=='__main__':

    #   Startup items here
    print('Starting MCL Microstage')
    # intialize
    stage = Madstage()
    print(stage.mcl_serial()) # get serial number
    main(client,stage,ser)
