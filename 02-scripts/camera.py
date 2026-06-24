# camera.py

from picamera2 import Picamera2
#the main camera object
from picamera2.encoders import H264Encoder
#compresses video using the Pi's built-in hardware encoder (fast, low CPU)
from picamera2.outputs import FfmpegOutput
#wraps that compressed video in an .mp4 container so it's playable on any device
import config

_camera = Picamera2()
#creates the camera object

_camera.configure(
    #create_video_configuration() tells picamera2 we want video mode 
    # (as opposed to still photo mode), at the resolution from our config file
    # "format": "BGR888" is the key one — cameras naturally output RGB (Red-Green-Blue), 
    # but OpenCV expects BGR (Blue-Green-Red). By telling picamera2 to flip the channel order here, 
    # every frame is already in the right format and we never have to convert

    _camera.create_video_configuration(
        main={"size": config.RESOLUTION, "format": "BGR888"}
    )
)

_camera.start()
#This runs once when the module is first imported — same pattern as os.makedirs() 
# in storage.py. By the time main.py calls any of our functions, 
# the camera is already warmed up and ready.


def get_frame():
    #  capture_array() takes a snapshot from the live camera feed and 
    # returns it as a NumPy array — a grid of pixel values that OpenCV 
    # knows how to work with.This is what the main loop will call on 
    # every single iteration to get a fresh frame for motion detection. 
    # It's fast because the camera is already running — we're just 
    # grabbing whatever it's currently seeing.

    return _camera.capture_array()


def start_recording(filepath):
    #H264Encoder() — H264 is a video compression format. 
    # The Pi 4 has a dedicated hardware chip for this, so it compresses 
    # video without eating your CPU. We create a fresh encoder each time a new clip starts.
    # FfmpegOutput(filepath) — takes the compressed H264 data and writes it 
    # into an .mp4 file at the path we pass in. ffmpeg is a standard tool already 
    # on the Pi that handles the container format.
    _camera.start_recording(H264Encoder(), FfmpegOutput(filepath))
    

def stop_recording():
    #tells picamera2 to finish writing the video file and shut down the encoder. 
    # The camera itself keeps running, so we can keep calling get_frame() after a clip ends.
    _camera.stop_recording()


def close():
    # fully shuts down the camera. This will be called in main.py 
    # when the user hits Ctrl+C, so the hardware is released cleanly 
    # instead of just dying mid-frame.
    _camera.stop()


