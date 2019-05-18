###############################################################################
#                                                                             #
# original file:    4_multi_core.py                                           #
#                                                                             #
# authors: Andre Heil  - avh34                                                #
#          Jingyao Ren - jr386                                                #
#                                                                             #
# date:    December 1st 2015                                                  #
#                                                                             #
# edited by: Michael Rivera  - mr858										  #
#            Henri Clarke - hxc2											  #
#                                                                             #
# edit date: May 9th 2019                                                     #
#                                                                             #
# original brief:   This file uses multicore processing to track your face.   #
#                   This is similar to 1_single_core.py except now we utilize #
#                   all four cores to create a more fluid video.              #
#                                                                             #
###############################################################################


### Imports ###################################################################

from picamera.array import PiRGBArray
from picamera import PiCamera
from functools import partial

import socket
import sys

import cv2
import os
import time
import numpy as np

from bluedot.btcomm import BluetoothClient
from signal import pause

import RPi.GPIO as GPIO

### Setup #####################################################################

resX = 320
resY = 240

cx = resX / 2
cy = resY / 2

# Setup the camera
camera = PiCamera()
camera.resolution = ( resX, resY )
camera.framerate = 60

# Use this as our output
rawCapture = PiRGBArray( camera, size=( resX, resY ) )

# The face cascade file to be used
face_cascade = cv2.CascadeClassifier('/home/pi/opencv-2.4.9/data/lbpcascades/lbpcascade_frontalface.xml')

t_start = time.time()
fps = 0

mode = -1
ipServer = None

# Bluetooth
def data_received(data):
    global mode
    global ipServer
    global pl
    global pr
    if data == "d" and mode == 5: # Transition from wait state to writing
        mode = 1
    elif data == 'h': # Wiggle
        mode = 2
    elif data == 'r': # Drive state
        mode = 3
    elif data == 'c': # Write state
        mode = 1
    elif data == 'b': # Home state
        mode = 0
        pl.ChangeDutyCycle(0)
        pr.ChangeDutyCycle(0)
    elif data == 'stop': # Stop driving
        pl.ChangeDutyCycle(0)
        pr.ChangeDutyCycle(0)
    elif mode == 3: # Compute direction of driving
        deg = float(data)
        uptimer = 0.0
        uptimel = 0.0
        if deg > 90:
            uptimer = 1.3
            uptimel = 1.7 - .4 * ((float(deg) - 90) / 90)
            print('q2: ' + str(uptimel) +', ' + str(uptimer))
        elif deg > 0:
            uptimel = 1.7
            uptimer = 1.7 - .4 * ((float(deg) ) / 90)
            print('q1: ' + str(uptimel) +', ' + str(uptimer))
        elif deg > - 90:
            uptimer = 1.7
            uptimel = 1.3 + .4 * ((float(deg) + 90) / 90)
            print('q4: ' + str(uptimel) +', ' + str(uptimer))
        else:
            uptimel = 1.3
            uptimer = 1.3 + .4 * ((float(deg) + 180) / 90)
            print('q3: ' + str(uptimel) +', ' + str(uptimer))
        pl.ChangeDutyCycle(dcOf(uptimel))
        pl.ChangeFrequency(freqOf(uptimel))
        pr.ChangeDutyCycle(dcOf(uptimer))
        pr.ChangeFrequency(freqOf(uptimer))
    elif mode == -1: # Obtain ip for socket
        ipServer = data
        mode = 0
    print(data)

# Polling Bluetooth connection
conn = True
client = None
while(conn):
    conn = False
    try:
        client = BluetoothClient("B8:27:EB:9A:90:25",data_received)
    except:
        conn = True


### Helper Functions ##########################################################

YOLK = 250, 165, 0
LIGHTBLUE = 160, 200, 255

# Obtain faces information from classifier
def get_faces(img):
    gray = cv2.cvtColor( img, cv2.COLOR_BGR2GRAY )
    faces = face_cascade.detectMultiScale( gray )

    return faces

# Draw face information onto image and rotate servos
def draw_frame(img, faces):
    global fps
    global time_t
    global pr
    global pl
    global mode
    wx = 0
    wc = 0
    # Draw a rectangle around every face
    for ( x, y, w, h ) in faces:
        cv2.rectangle( img, ( x, y ),( x + w, y + h ), YOLK, 2 )
        cv2.putText(img, "frend no." + str( len( faces ) ), ( x, y ), cv2.FONT_HERSHEY_SIMPLEX, 0.5, LIGHTBLUE, 2 )
        wx += x + x + w
        wc += 2
    if mode == 0 or mode == 1 or mode == 5:
        if wc == 0:
            pl.ChangeDutyCycle(0)
            pr.ChangeDutyCycle(0)
        else:
            upT = 1.5 + .04 * ((float(wx/wc) - 160)/(160))
            updateServos(upT)

    # Calculate and show the FPS
    fps = fps + 1
    sfps = fps / (time.time() - t_start)
    cv2.putText(img, "FPS : " + str( int( sfps ) ), ( 10, 10 ), cv2.FONT_HERSHEY_SIMPLEX, 0.5, ( 0, 0, 255 ), 2 )

    return img

### Servo Setup ##########################################################

GPIO.setmode(GPIO.BCM)
GPIO.setup(12,GPIO.OUT)
GPIO.setup(26,GPIO.OUT)
GPIO.setup(5,GPIO.IN,pull_up_down=GPIO.PUD_UP)

isRunning = True

def myButton(channel):
    global isRunning
    isRunning = False

GPIO.add_event_detect(5,GPIO.FALLING,callback=myButton,bouncetime=300)

pl = GPIO.PWM(12,46.5)
pr = GPIO.PWM(26,46.5)
pr.start(0)
pl.start(0)

def freqOf(uptime):
    return (1.0 / ((20+uptime) * .001))
def dcOf(uptime):
    return (100 * uptime / (20 + uptime))
def updateServos(uptime):
    pl.ChangeDutyCycle(dcOf(uptime))
    pl.ChangeFrequency(freqOf(uptime))
    pr.ChangeDutyCycle(dcOf(uptime))
    pr.ChangeFrequency(freqOf(uptime))



### Main ######################################################################

shift = -1

for frame in camera.capture_continuous( rawCapture, format="bgr", use_video_port=True ):
    image = frame.array
    faces = get_faces(image)
    dframe = draw_frame(image, faces)
    rawCapture.truncate( 0 )
    if not isRunning:
        break
    if mode == 1: # Write state
        client.send("w")
        s = socket.socket()
        cv2.imwrite("test.png",dframe) # Save image locally
        s.connect((ipServer,9999))
        f = open('test.png','rb') # Read local image to socket
        l = f.read(1024)
        while(l):
            s.send(l)
            l = f.read(1024)
        f.close()
        s.close()
        mode = 5 # Switch to wait state
        print(dframe[0][0])
    if mode == 2: # Wiggle
        updateServos(1.5 + shift * .2)
        shift = shift * -1

GPIO.cleanup()
