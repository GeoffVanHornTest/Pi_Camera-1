# Implementation Guide: Dynamic Threshold System

Quick-start guide for implementing adaptive motion detection thresholds based on lighting environment.

---

## Quick Reference: Threshold Profiles

Use these starting values. Tune based on validation dataset results.

```python
# config.py - Threshold profiles by lighting environment

THRESHOLD_PROFILES = {
    'DAYTIME': {
        'scene_change_threshold': 15.0,
        'instant_step_threshold': 8.0,
        'min_blob_coherence': 0.30,
        'motion_threshold': 7500,
        'apply_luma_gate': False,
        'apply_blue_gate': False,
        'luma_max': None,
        'blue_min': None,
    },
    'TWILIGHT': {
        'scene_change_threshold': 17.0,
        'instant_step_threshold': 7.5,
        'min_blob_coherence': 0.35,
        'motion_threshold': 8000,
        'apply_luma_gate': True,
        'apply_blue_gate': False,
        'luma_max': 85,
        'blue_min': None,
    },
    'NIGHT_NO_IR': {
        'scene_change_threshold': 18.0,
        'instant_step_threshold': 8.0,
        'min_blob_coherence': 0.35,
        'motion_threshold': 8500,
        'apply_luma_gate': True,
        'apply_blue_gate': False,
        'luma_max': 80,
        'blue_min': None,
    },
    'NIGHT_WITH_IR': {
        'scene_change_threshold': 20.0,
        'instant_step_threshold': 6.0,
        'min_blob_coherence': 0.40,
        'motion_threshold': 8500,
        'apply_luma_gate': True,
        'apply_blue_gate': True,
        'luma_max': 95,
        'blue_min': 130,
    },
    'ANOMALY': {
        'scene_change_threshold': 25.0,
        'instant_step_threshold': 10.0,
        'min_blob_coherence': 0.50,
        'motion_threshold': 10000,
        'apply_luma_gate': True,
        'apply_blue_gate': False,
        'luma_max': 90,
        'blue_min': None,
    },
}

# Environment classification thresholds
BRIGHTNESS_THRESHOLD_DAY = 80
BRIGHTNESS_THRESHOLD_TWILIGHT = 60
BRIGHTNESS_THRESHOLD_NIGHT = 40
BLUE_CHANNEL_THRESHOLD_IR = 110
```

---

## Step 1: Add Helper Functions for Brightness Metrics

```python
# In motion_detection.py or utils.py

import numpy as np
import cv2

def calculate_luma(frame):
    """
    Calculate luminance (Y channel) from BGR frame.
    Luma = 0.299*R + 0.587*G + 0.114*B (ITU-R BT.601)
    Range: 0-255
    """
    b, g, r = cv2.split(frame)
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    return np.mean(luma)


def calculate_blue_channel(frame):
    """
    Calculate mean of blue channel.
    Useful for IR illumination detection.
    Range: 0-255
    """
    b = frame[:, :, 0]  # OpenCV uses BGR order
    return np.mean(b)


def calculate_grey(frame):
    """
    Calculate grayscale (average of RGB).
    Less perceptually accurate than luma, but simple.
    """
    return np.mean(frame)


def calculate_scene_change(luma_current, luma_previous):
    """
    Calculate frame-to-frame brightness change.
    Magnitude indicates scene activity or transitions.
    """
    return abs(luma_current - luma_previous)
```

---

## Step 2: Implement Environment Classifier

```python
# In motion_detection.py

class LightingEnvironmentClassifier:
    """
    Classifies lighting conditions based on frame brightness metrics.
    Maintains state to smooth transitions between environments.
    """
    
    def __init__(self):
        self.current_env = 'DAYTIME'
        self.confidence = 1.0
        self.history = []  # For smoothing
        self.max_history = 10
    
    def classify(self, luma, blue, scene_change=0):
        """
        Classify environment based on brightness metrics.
        
        Args:
            luma: Luminance (0-255)
            blue: Blue channel mean (0-255)
            scene_change: Frame-to-frame brightness delta
        
        Returns:
            (env_class, confidence)
        """
        
        # Rule 1: Bright environment (luma > 80)
        if luma > 80:
            if blue > 100:
                return 'DAYTIME', 0.95
            else:
                # High luma, low blue = unusual
                return 'ANOMALY', 0.70
        
        # Rule 2: Twilight (60-80 luma)
        elif 60 <= luma <= 80:
            return 'TWILIGHT', 0.85
        
        # Rule 3: Dark environment (luma < 60)
        else:
            # Distinguish by blue channel
            if blue > 110:
                # High blue in darkness = IR illumination
                return 'NIGHT_WITH_IR', 0.90
            elif 90 <= blue <= 110:
                # Medium blue = uncertain, might be very dim day
                return 'NIGHT_NO_IR', 0.65
            else:
                # Low blue = clear night without IR
                return 'NIGHT_NO_IR', 0.90
    
    def update(self, luma, blue, scene_change=0):
        """
        Update environment state with hysteresis (smoothing).
        Prevents rapid oscillation at environment boundaries.
        """
        env_candidate, confidence = self.classify(luma, blue, scene_change)
        
        # High confidence: switch immediately
        if confidence > 0.8:
            self.current_env = env_candidate
            self.confidence = confidence
        else:
            # Low confidence: stay in current state unless very confident
            # This prevents flickering at twilight boundaries
            if env_candidate == self.current_env:
                self.confidence = max(self.confidence, confidence)
            elif confidence > 0.7:
                self.current_env = env_candidate
                self.confidence = confidence
        
        # Log for debugging
        self.history.append({
            'timestamp': None,  # Add timestamp in real implementation
            'luma': luma,
            'blue': blue,
            'env': self.current_env,
            'confidence': self.confidence,
        })
        
        if len(self.history) > self.max_history:
            self.history.pop(0)
        
        return self.current_env, self.confidence
    
    def get_current_env(self):
        """Get current environment classification."""
        return self.current_env
    
    def get_debug_info(self):
        """Return debug info for logging."""
        return {
            'current_env': self.current_env,
            'confidence': self.confidence,
            'history_size': len(self.history),
        }
```

---

## Step 3: Integrate into Motion Detection Loop

```python
# In main video processing loop

from config import THRESHOLD_PROFILES
from motion_detection import (
    calculate_luma, calculate_blue_channel, calculate_scene_change,
    LightingEnvironmentClassifier
)

class MotionDetector:
    def __init__(self):
        self.background_subtractor = cv2.createBackgroundSubtractorMOG2()
        self.env_classifier = LightingEnvironmentClassifier()
        self.prev_luma = None
    
    def process_frame(self, frame):
        """
        Process single frame with adaptive thresholds.
        
        Returns:
            {
                'motion_detected': bool,
                'reason': str,
                'env': str,
                'metrics': {...}
            }
        """
        
        # 1. Calculate brightness metrics
        luma = calculate_luma(frame)
        blue = calculate_blue_channel(frame)
        scene_change = (
            calculate_scene_change(luma, self.prev_luma)
            if self.prev_luma is not None else 0
        )
        
        # 2. Classify environment and get thresholds
        env, confidence = self.env_classifier.update(luma, blue, scene_change)
        thresholds = THRESHOLD_PROFILES[env]
        
        # 3. Apply scene change gate (reject rapid transients)
        if scene_change > thresholds['scene_change_threshold']:
            result = {
                'motion_detected': False,
                'reason': 'scene_change_gate',
                'gate_value': scene_change,
                'gate_threshold': thresholds['scene_change_threshold'],
                'env': env,
                'luma': luma,
                'blue': blue,
            }
            self.prev_luma = luma
            return result
        
        # 4. Apply luma gate if enabled
        if thresholds['apply_luma_gate']:
            if luma > thresholds['luma_max']:
                result = {
                    'motion_detected': False,
                    'reason': 'luma_gate',
                    'gate_value': luma,
                    'gate_threshold': thresholds['luma_max'],
                    'env': env,
                    'luma': luma,
                    'blue': blue,
                }
                self.prev_luma = luma
                return result
        
        # 5. Apply blue channel gate if enabled
        if thresholds['apply_blue_gate']:
            if blue < thresholds['blue_min']:
                result = {
                    'motion_detected': False,
                    'reason': 'blue_gate',
                    'gate_value': blue,
                    'gate_threshold': thresholds['blue_min'],
                    'env': env,
                    'luma': luma,
                    'blue': blue,
                }
                self.prev_luma = luma
                return result
        
        # 6. Standard MOG2 motion detection
        fg_mask = self.background_subtractor.apply(frame)
        motion_pixels = cv2.countNonZero(fg_mask)
        
        motion_detected = motion_pixels > thresholds['motion_threshold']
        
        # 7. Blob coherence check (if motion found)
        if motion_detected:
            contours, _ = cv2.findContours(
                fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            if contours:
                # Filter by coherence (blob quality)
                valid_contours = [
                    c for c in contours
                    if self._blob_coherence(c) > thresholds['min_blob_coherence']
                ]
                motion_detected = len(valid_contours) > 0
            else:
                motion_detected = False
        
        result = {
            'motion_detected': motion_detected,
            'reason': 'motion_detection_complete',
            'motion_pixels': motion_pixels,
            'motion_threshold': thresholds['motion_threshold'],
            'env': env,
            'env_confidence': confidence,
            'luma': luma,
            'blue': blue,
            'scene_change': scene_change,
        }
        
        self.prev_luma = luma
        return result
    
    def _blob_coherence(self, contour):
        """
        Calculate blob coherence (compactness).
        Higher values indicate more compact, real motion blobs.
        Lower values indicate noise or sparse pixels.
        """
        if cv2.contourArea(contour) == 0:
            return 0.0
        
        # Solidity: ratio of contour area to convex hull area
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        contour_area = cv2.contourArea(contour)
        
        if hull_area == 0:
            return 0.0
        
        solidity = contour_area / hull_area
        return solidity
```

---

## Step 4: Logging and Validation

```python
# In your main loop

import json
import csv
from datetime import datetime

class MotionDetectionLogger:
    def __init__(self, log_file='motion_detection.log', csv_file='motion_detection.csv'):
        self.log_file = log_file
        self.csv_file = csv_file
        self.csv_fields = [
            'timestamp', 'frame_number', 'motion_detected', 'env', 'env_confidence',
            'luma', 'blue', 'scene_change', 'reason', 'gate_value', 'gate_threshold'
        ]
        
        # Initialize CSV with headers
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.csv_fields)
            writer.writeheader()
    
    def log(self, frame_number, result):
        """Log motion detection result."""
        
        # CSV row
        row = {
            'timestamp': datetime.now().isoformat(),
            'frame_number': frame_number,
            'motion_detected': result['motion_detected'],
            'env': result['env'],
            'env_confidence': result.get('env_confidence', ''),
            'luma': round(result.get('luma', 0), 2),
            'blue': round(result.get('blue', 0), 2),
            'scene_change': round(result.get('scene_change', 0), 2),
            'reason': result['reason'],
            'gate_value': result.get('gate_value', ''),
            'gate_threshold': result.get('gate_threshold', ''),
        }
        
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.csv_fields)
            writer.writerow(row)
        
        # Optional: JSON log for rich data
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(row) + '\n')


# Usage in main loop:
# 
# detector = MotionDetector()
# logger = MotionDetectionLogger()
# 
# cap = cv2.VideoCapture('video.mp4')
# frame_num = 0
# 
# while True:
#     ret, frame = cap.read()
#     if not ret:
#         break
#     
#     result = detector.process_frame(frame)
#     logger.log(frame_num, result)
#     
#     if result['motion_detected']:
#         print(f"Motion at frame {frame_num}")
#     
#     frame_num += 1
```

---

## Step 5: Validation Against Brightness Analysis Data

After implementation, validate against the 4 test datasets:

```python
# validate.py - Compare predicted vs actual classifications

import csv
import pandas as pd
from config import THRESHOLD_PROFILES

def validate_environment_classification(brightness_csv, dataset_name):
    """
    Validate that the classifier correctly identifies environments
    and correctly distinguishes false positives from legitimate motion.
    """
    
    df = pd.read_csv(brightness_csv)
    
    # Group by filename (clip name)
    results = {
        'total_clips': 0,
        'correct_classification': 0,
        'false_positives_filtered': 0,
        'legitimate_motion_passed': 0,
        'errors': []
    }
    
    for idx, row in df.iterrows():
        clip_name = row['clip_name']
        luma = row['luma_mean']
        blue = row['blue_mean']
        is_false_positive = '_motion_' in clip_name  # Naming convention
        
        # Classify
        classifier = LightingEnvironmentClassifier()
        env, confidence = classifier.classify(luma, blue)
        
        thresholds = THRESHOLD_PROFILES[env]
        
        # Predict if this clip would trigger motion
        motion_would_trigger = True
        
        if thresholds['apply_luma_gate']:
            if luma > thresholds['luma_max']:
                motion_would_trigger = False
        
        if motion_would_trigger and thresholds['apply_blue_gate']:
            if blue < thresholds['blue_min']:
                motion_would_trigger = False
        
        # Evaluate
        results['total_clips'] += 1
        
        if is_false_positive and not motion_would_trigger:
            results['false_positives_filtered'] += 1
        elif not is_false_positive and motion_would_trigger:
            results['legitimate_motion_passed'] += 1
        else:
            results['errors'].append({
                'clip': clip_name,
                'luma': luma,
                'blue': blue,
                'env': env,
                'is_fp': is_false_positive,
                'passed_filters': motion_would_trigger,
            })
    
    return results


# Example usage:
# results = validate_environment_classification(
#     'analysis_results/brightness_03_Test2_Aug12_Filter-ON_Lights-ON_50clips.csv',
#     'Test 2'
# )
# 
# print(f"Dataset: Test 2")
# print(f"Total clips: {results['total_clips']}")
# print(f"False positives filtered: {results['false_positives_filtered']}")
# print(f"Legitimate motion passed: {results['legitimate_motion_passed']}")
# print(f"Errors: {len(results['errors'])}")
```

---

## Next Steps

1. **Copy code snippets** into your motion detection codebase
2. **Run validation** against brightness_*.csv files to verify gates work
3. **Tune thresholds** based on validation results (adjust luma_max, blue_min, etc.)
4. **Test on new clips** with Test 2 hardware (Filter ON + Lights ON)
5. **Monitor and log** all detections to find remaining edge cases

---

## Troubleshooting

**Problem:** Classifier oscillates between TWILIGHT and DAYTIME
- **Solution:** Increase hysteresis window or widen luma thresholds (60→65)

**Problem:** Blue channel gate is too strict, missing some legitimate motion
- **Solution:** Lower blue_min from 130 to 120 or 110 and re-validate

**Problem:** Luma gate rejects too much legitimate motion
- **Solution:** Increase luma_max from 95 to 105 (but monitor false positives)

**Problem:** Scene change gate triggers on real motion
- **Solution:** Increase scene_change_threshold or make it environment-specific

---

## References

- **DYNAMIC_THRESHOLD_DESIGN.md** — Full design documentation
- **BRIGHTNESS_ANALYSIS.md** — Statistical basis for thresholds
- **CSV Data:** analysis_results/*.csv files with per-frame brightness metrics
