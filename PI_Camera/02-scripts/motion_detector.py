# motion_detector.py
import cv2
import time
import config

_bg_subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
_last_motion = 0

#Two module-level variables, same pattern as _camera in camera.py.

#_bg_subtractor — MOG2 stands for "Mixture of Gaussians 2". It works by 
# watching many frames over time and building a statistical model of 
# what the "background" looks like. When a new frame comes in, 
# anything that doesn't match that model gets painted white in a mask 
# — that's your moving object. detectShadows=False tells it 
# not to bother classifying shadows separately, which saves 
# CPU and keeps the mask simpler.

#_last_motion — stores the timestamp of the last time motion was detected. 
# Set to 0 so the very first motion event always triggers immediately 
# (same trick we used with _last_sent in notifier.py).

def detect(frame):
    global _last_motion
    # tells Python we want to modify the module-level variable, not create a new 
    # local one (same pattern as global _last_sent in notifier.py)

    fg_mask = _bg_subtractor.apply(frame)

   
            

#apply() is where the MOG2 magic happens. You hand it a frame, it compares 
# it against its background model, and returns a foreground mask 
# — a black-and-white image the same size as your frame where:

# White pixels = something moved here
# Black pixels = background, nothing changed
#The mask is noisy at this point — there'll be speckles and small blobs 
# from things like a leaf moving or a camera artifact. The next step is 
# where we filter those out.

    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    #fg_mask — the black-and-white image we just made
    # cv2.RETR_EXTERNAL — only return the outermost outline of each blob, ignore any holes inside
    # cv2.CHAIN_APPROX_SIMPLE — compress the outline down to just its corner points instead 
    # of storing every single pixel on the edge (saves memory, still accurate enough)

    motion_detected = False

    for contour in contours:
        #  start by assuming no motion. Then we loop through every contour and measure its area in pixels. 
        # If any single contour is larger than MOTION_THRESHOLD (which we set to 500 in config.py), 
        # something real moved — we set the flag and break out of the loop immediately 
        # since we don't need to check the rest.
        # This is the noise filter. A speck of dust or a compression artifact might produce a 
        # contour of 10–20 pixels. A person walking through frame will produce a contour of thousands of pixels. 
        # The threshold sits in between.

        if cv2.contourArea(contour) > config.MOTION_THRESHOLD:
            motion_detected = True
            break

    now = time.time()
    # how many seconds have passed since the last confirmed motion event

    if motion_detected and (now - _last_motion) > config.MOTION_COOLDOWN_SEC:
        # The if only returns True when motion was detected and enough time has passed. 
        # If motion is detected but we're still in cooldown, it falls through to return False, frame 
        # — silently ignored.
       
        _last_motion = now
        return True, frame
        # We always return the frame either way so main.py can use it regardless

    return False, frame

        

