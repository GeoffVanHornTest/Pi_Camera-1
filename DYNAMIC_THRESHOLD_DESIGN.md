# Dynamic Threshold Design: Lighting-Aware Motion Detection

## Overview

Instead of static thresholds, the motion detection system should **adapt detection sensitivity based on detected lighting environment**. Scene brightness analysis combined with scene change magnitude provides a natural way to classify operating modes and apply optimal thresholds for each.

---

## Current Tuning Guidance Summary

From BRIGHTNESS_ANALYSIS.md, the baseline parameters are:

| Parameter | Current | Test 2 Recommended | Test 1 Fallback | Purpose |
|-----------|---------|---|---|---|
| **MOTION_THRESHOLD_NIGHT** | 7500 | 8000–9000 | 7500 | MOG2 detection sensitivity |
| **SCENE_CHANGE_THRESHOLD** | 15.0 | 20.0 | 20.0 | Frame-to-frame brightness delta |
| **INSTANT_STEP_THRESHOLD** | 8.0 | 6.0 | 8.0 | Sudden brightness spike detection |
| **MIN_BLOB_COHERENCE** | 0.30 | 0.40 | 0.35 | Motion blob shape quality |
| **Blue Channel Gate** | None | `blue_mean < 130` | N/A | Reject if too dark in blue channel |
| **Luma Gate** | None | `luma_mean > 95` | `luma_mean > 105` | Reject if too bright overall |

---

## Lighting Environment Classification

The system currently uses a single `BRIGHTNESS_THRESHOLD=60` to toggle between day/night mode. **We should expand this to classify more granular lighting states** based on frame-level and clip-level brightness metrics:

### Environment Classes

```
┌─────────────────────────────────────────────────────────────┐
│ Lighting Environment Classification                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  DAYTIME (Luma > 80)                                        │
│  ├─ Condition: Natural daylight, sufficient ambient light   │
│  ├─ Characteristics: High luma, high blue channel           │
│  ├─ False Positive Profile: Very rare (7.8% baseline)       │
│  ├─ Strategy: Minimal gating, rely on MOG2 motion detection │
│  └─ Thresholds:                                             │
│     • SCENE_CHANGE_THRESHOLD = 15.0 (default)              │
│     • MIN_BLOB_COHERENCE = 0.30 (default)                  │
│     • MOTION_THRESHOLD = 7500 (day mode)                    │
│                                                              │
│  TWILIGHT/DUSK (Luma 60–80)                                 │
│  ├─ Condition: Transitional lighting, weak but visible      │
│  ├─ Characteristics: Medium luma, variable blue             │
│  ├─ False Positive Profile: Moderate (15–25%)               │
│  ├─ Strategy: Graduated gating, begin blue channel checks   │
│  └─ Thresholds:                                             │
│     • SCENE_CHANGE_THRESHOLD = 17.0                         │
│     • MIN_BLOB_COHERENCE = 0.35                             │
│     • MOTION_THRESHOLD = 8000                               │
│     • Blue Channel Gate: Only if luma < 70                  │
│                                                              │
│  NIGHT W/O IR (Luma 20–60)                                  │
│  ├─ Condition: Dark but visible (streetlight, ambient)      │
│  ├─ Characteristics: Low luma, low blue (visible spectrum)  │
│  ├─ False Positive Profile: Unknown (no data)               │
│  ├─ Strategy: Moderate luma gating                          │
│  └─ Thresholds:                                             │
│     • SCENE_CHANGE_THRESHOLD = 18.0                         │
│     • MIN_BLOB_COHERENCE = 0.35                             │
│     • MOTION_THRESHOLD = 8500                               │
│     • Luma Gate: Reject if luma > 80 (anomaly)              │
│                                                              │
│  NIGHT W/ IR LIGHTS (Luma 80–115, Blue ~110–150)            │
│  ├─ Condition: IR-illuminated night scene (Test 2 optimal)  │
│  ├─ Characteristics: High luma, high blue (IR reflectance)  │
│  ├─ False Positive Profile: 38% without gating, ~15% w/gate │
│  ├─ Strategy: Aggressive dual-threshold gating              │
│  └─ Thresholds:                                             │
│     • SCENE_CHANGE_THRESHOLD = 20.0 (high)                  │
│     • MIN_BLOB_COHERENCE = 0.40 (strict)                    │
│     • MOTION_THRESHOLD = 8500                               │
│     • Luma Gate: REJECT if luma > 95                        │
│     • Blue Gate: REJECT if blue < 130 (no legit motion)     │
│     • INSTANT_STEP_THRESHOLD = 6.0 (sensitive to real move) │
│                                                              │
│  NIGHT W/O IR FILTER (Luma 85–115, Blue ~85–95)             │
│  ├─ Condition: IR lights on but no IR filter (Test 3 issue) │
│  ├─ Characteristics: High luma, LOW blue (no filter)        │
│  ├─ False Positive Profile: 52% (avoid this config)         │
│  ├─ Strategy: Avoid if possible; high false positive rate   │
│  └─ Thresholds: As NIGHT W/ IR LIGHTS but with caveats      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Dynamic Threshold Selection Algorithm

### Step 1: Classify Lighting Environment (per-frame)

```python
def classify_lighting_env(luma_mean, blue_mean, previous_env):
    """
    Classify the current lighting environment based on brightness metrics.
    
    Returns: (env_class, confidence)
    env_class: 'DAYTIME', 'TWILIGHT', 'NIGHT_NO_IR', 'NIGHT_WITH_IR', 'ANOMALY'
    confidence: 0.0-1.0 indicating certainty
    """
    
    # Heuristic 1: Use luma and blue channel together
    if luma_mean > 80:
        if blue_mean > 100:
            return 'DAYTIME', 0.95
        else:
            # High luma but low blue = anomaly (possible sensor issue)
            return 'ANOMALY', 0.7
    
    elif 60 <= luma_mean <= 80:
        return 'TWILIGHT', 0.85
    
    elif luma_mean < 60:
        # Night time - distinguish by blue channel
        if blue_mean > 110:  # IR lights active
            return 'NIGHT_WITH_IR', 0.90
        elif 85 <= blue_mean <= 110:
            # Uncertain - might be IR lights OFF or dim
            return 'NIGHT_NO_IR', 0.65
        else:
            return 'NIGHT_NO_IR', 0.90
    
    # Fallback: use previous state for stability
    return previous_env, 0.5


def update_environment_state(env_class, confidence, decay_rate=0.1):
    """
    Smooth environment transitions to avoid rapid threshold switching.
    Uses exponential moving average with hysteresis.
    """
    # If confidence is high, switch immediately
    if confidence > 0.8:
        return env_class
    
    # Otherwise, weight current + previous state
    # Prevents flicker at environment boundaries
    return env_class  # (simplified; real impl uses state machine)
```

### Step 2: Select Thresholds Based on Environment

```python
THRESHOLD_PROFILES = {
    'DAYTIME': {
        'scene_change_threshold': 15.0,
        'instant_step_threshold': 8.0,
        'min_blob_coherence': 0.30,
        'motion_threshold': 7500,
        'luma_gate': None,  # No gating in daylight
        'blue_gate': None,
        'description': 'Daytime - high confidence in MOG2 alone'
    },
    
    'TWILIGHT': {
        'scene_change_threshold': 17.0,
        'instant_step_threshold': 7.5,
        'min_blob_coherence': 0.35,
        'motion_threshold': 8000,
        'luma_gate': {'max': 85, 'reason': 'reject anomalies'},
        'blue_gate': None,  # Begin checking but not enforcing yet
        'description': 'Twilight - moderate gating'
    },
    
    'NIGHT_NO_IR': {
        'scene_change_threshold': 18.0,
        'instant_step_threshold': 8.0,
        'min_blob_coherence': 0.35,
        'motion_threshold': 8500,
        'luma_gate': {'max': 80, 'reason': 'night without IR should be dim'},
        'blue_gate': None,
        'description': 'Night without IR - low luma expected'
    },
    
    'NIGHT_WITH_IR': {
        'scene_change_threshold': 20.0,  # HIGH - reject bright transients
        'instant_step_threshold': 6.0,   # LOW - sensitive to real motion
        'min_blob_coherence': 0.40,      # STRICT - reject noise
        'motion_threshold': 8500,
        'luma_gate': {'max': 95, 'reason': 'IR + false pos cluster at 104'},
        'blue_gate': {'min': 130, 'reason': 'legit motion has high blue ~150'},
        'description': 'Night with IR - aggressive dual-gate (Test 2 optimal)'
    },
    
    'ANOMALY': {
        'scene_change_threshold': 25.0,  # Very high
        'instant_step_threshold': 10.0,  # Very low sensitivity
        'min_blob_coherence': 0.50,      # Very strict
        'motion_threshold': 10000,       # High threshold
        'luma_gate': {'max': 90, 'reason': 'unknown condition'},
        'blue_gate': None,
        'description': 'Anomaly - unknown state, minimal detection'
    },
}


def get_thresholds(env_class):
    """Get all motion detection thresholds for current environment."""
    return THRESHOLD_PROFILES.get(env_class, THRESHOLD_PROFILES['ANOMALY'])
```

### Step 3: Apply Thresholds in Motion Detection Loop

```python
def detect_motion_adaptive(frame, background_model, env_class, prev_frame_metrics):
    """
    Motion detection with adaptive thresholds based on lighting environment.
    """
    thresholds = get_thresholds(env_class)
    
    # Standard MOG2 foreground detection
    fg_mask = background_model.apply(frame)
    
    # Calculate brightness metrics for this frame
    luma = calculate_luma(frame)
    blue = calculate_blue_channel(frame)
    
    # 1. Apply scene change gating (reject rapid, unexplained brightness swings)
    scene_change = abs(luma - prev_frame_metrics['luma'])
    if scene_change > thresholds['scene_change_threshold']:
        # Skip motion detection for this frame
        # (It's likely a scene change, not motion)
        return None, {'reason': 'scene_change', 'value': scene_change}
    
    # 2. Apply luma gate if specified
    if thresholds['luma_gate'] and luma > thresholds['luma_gate']['max']:
        return None, {
            'reason': 'luma_gate',
            'value': luma,
            'threshold': thresholds['luma_gate']['max']
        }
    
    # 3. Apply blue channel gate if specified
    if thresholds['blue_gate'] and blue < thresholds['blue_gate']['min']:
        return None, {
            'reason': 'blue_gate',
            'value': blue,
            'threshold': thresholds['blue_gate']['min']
        }
    
    # 4. Process motion blobs with environment-specific sensitivity
    motion_found = False
    if fg_mask.sum() > thresholds['motion_threshold']:
        # Find contours (motion blobs)
        blobs = find_motion_blobs(fg_mask)
        
        # Filter by coherence (blob quality)
        valid_blobs = [
            b for b in blobs 
            if blob_coherence(b) > thresholds['min_blob_coherence']
        ]
        
        if valid_blobs:
            # Instant step check: sudden intensity change in motion region
            intensity_change = calc_intensity_change(frame, prev_frame, valid_blobs)
            if intensity_change > thresholds['instant_step_threshold']:
                motion_found = True
    
    return motion_found, {'reason': 'detection_result', 'blobs': len(blobs)}
```

---

## Scene Change Threshold as Environment Signal

The **SCENE_CHANGE_THRESHOLD** serves dual purposes:

### Current Use (Reject Transient Brightness Spikes)
- Filters out rapid, unexplained changes in overall frame brightness
- Prevents false motion detection from sudden lighting changes

### Proposed New Use (Detect Environment Transitions)
When scene change magnitude exceeds a threshold persistently:
- Could indicate a *real* scene change (camera moved, lights toggled, etc.)
- Signals potential environment class transition
- Should trigger re-evaluation of lighting classification

```python
def detect_environment_transition(frame_metrics, history_window=5):
    """
    Detect if large scene changes suggest an environment transition
    (e.g., lights just turned on, or switched to IR mode).
    """
    recent_changes = history_window[-5:]
    avg_scene_change = mean([m['scene_change'] for m in recent_changes])
    
    # If scene change is consistently high, environment likely changed
    if avg_scene_change > 25:  # (very high threshold)
        print("Environment transition detected - re-classifying...")
        return True
    
    return False
```

---

## Implementation Priority

### Phase 1: Static Environment Detection (Week 1)
- Implement `classify_lighting_env()` function
- Create threshold profiles for each environment
- Test on historical clip datasets (verify correct classification)

### Phase 2: Adaptive Threshold Selection (Week 2)
- Integrate threshold selection into motion detection loop
- Apply scene change gating first (easiest win)
- Add luma/blue gates incrementally

### Phase 3: Smooth Transitions (Week 3)
- Implement hysteresis for environment switching
- Add environment transition detection
- Logging and metrics for debugging

### Phase 4: Validation (Week 4)
- Collect new test data with each configuration active
- Measure false positive rate per environment
- Tune gate thresholds based on real-world results

---

## Expected Outcomes

### By Environment:
| Environment | Expected False Rate | Detection Sensitivity | Notes |
|---|---|---|---|
| **DAYTIME** | <5% | High | Should be already low |
| **TWILIGHT** | <15% | Medium | Smooth transition zone |
| **NIGHT_NO_IR** | <25% | Medium | Limited data; conservative |
| **NIGHT_WITH_IR** | <20% | High | Main deployment scenario |
| **ANOMALY** | <5% | Low | Rare; safe to miss events |

### Overall Impact:
- Reduce false positive rate from 50% (Test 1) to ~15% (Test 2 w/ gates)
- Preserve >95% legitimate motion detection
- Enable confident nighttime deployment with IR configuration

---

## Logging and Diagnostics

For each motion event (detected or rejected), log:

```python
{
    'timestamp': timestamp,
    'env_class': 'NIGHT_WITH_IR',
    'luma': 104.3,
    'blue': 117.1,
    'scene_change': 3.2,
    'motion_found': False,
    'rejection_reason': 'luma_gate',
    'rejection_value': 104.3,
    'threshold_value': 95,
    'confidence': 0.92
}
```

This enables:
- Validation of environment classification accuracy
- Identification of threshold tuning opportunities
- Performance analysis per environment
- Easy rollback if thresholds are incorrect

---

## References

- **BRIGHTNESS_ANALYSIS.md** — Detailed brightness statistics from 240-clip study
- **Test 2 Results** — Filter ON + Lights ON showed best separation (38% false rate)
- **Baseline Patterns** — Daytime false rate only 8%, validates static threshold approach for daylight
