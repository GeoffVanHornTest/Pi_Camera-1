# SCENE_CHANGE_THRESHOLD: Dynamic Tuning Strategy

## The Problem We're Solving

From BRIGHTNESS_ANALYSIS.md, we discovered:
- **Test 2 (best case):** 38% false positive rate with static thresholds
- **Test 1 (fallback):** 50% false positive rate
- **Test 3 (worst case):** 52% false positive rate

The root cause: **Motion detection uses one-size-fits-all thresholds** that don't adapt to the lighting environment. False positives cluster at specific brightness levels (luma ~100, blue ~110-120) that differ from legitimate motion (luma ~79, blue ~150).

**Solution:** Use SCENE_CHANGE_THRESHOLD as the canary signal to detect environment *type*, then dynamically select thresholds optimized for that type.

---

## Why SCENE_CHANGE_THRESHOLD Is the Key

SCENE_CHANGE_THRESHOLD measures frame-to-frame brightness delta:

```
Scene Change = |Luma(frame_N) - Luma(frame_N-1)|
```

This metric naturally encodes **environment information**:

| Scenario | Typical Scene Change | What It Tells Us |
|---|---|---|
| Smooth motion (person walking) | 2–5 | Legitimate motion, low-light variation |
| Lighting toggle (IR lights on/off) | 30–60 | **Environment just changed** |
| Transient spike (sensor artifact) | 15–25 | Likely false positive |
| Camera pan or focus shift | 10–15 | Borderline; depends on environment |
| Night to day transition | 40–80 | Major environment shift |

**Key insight:** By monitoring scene_change magnitude over time, we can infer which lighting environment we're in, and select the *best* thresholds for that environment.

---

## Three-Tier Strategy

### Tier 1: Reject Transient Transients (Current Baseline)

```
If scene_change > SCENE_CHANGE_THRESHOLD_ALERT:
    Skip motion detection for this frame
    (It's a lighting transient, not motion)
    
Current threshold: 15.0
New per-environment thresholds: 15–25
```

**Why this works:** Transient brightness spikes (which cause false positives) happen *suddenly* and *completely* change the frame. Real motion, even fast motion, changes brightness more *gradually*.

**Example:**
- False positive: Sensor artifact causes all pixels to brighten by 40 luma units in one frame → Scene change = 40
- Legitimate motion: Person walks across scene, local brightness changes vary → Scene change = 3–8

### Tier 2: Classify Environment Based on Typical Scene Change

Analyze *sustained* scene change patterns to infer the lighting environment:

```
If avg_scene_change (over N frames) is:
    0-2:   Stable environment, likely DAYTIME (well-lit, little change)
    2-5:   Stable but variable lighting (twilight or indoors)
    5-10:  Dynamic lighting or night with some illumination
    10+:   Frequent brightness shifts (unstable; rare)
```

Combined with absolute luma/blue values, this gives us high confidence in environment class.

### Tier 3: Apply Optimized Thresholds for Detected Environment

Once we know the environment, we apply the *best* thresholds for that condition:

```
DAYTIME (luma > 80):
    scene_change_threshold: 15.0  (reject anything bigger; unlikely in daylight)
    min_blob_coherence: 0.30      (motion blobs are clear in daylight)
    luma_gate: None               (no gating needed)
    
NIGHT_WITH_IR (luma 80-115, blue > 110):
    scene_change_threshold: 20.0  (higher; IR transients can spike)
    min_blob_coherence: 0.40      (stricter; false positive blobs are noisy)
    luma_gate: max=95             (reject if too bright; false pos cluster at 104)
    blue_gate: min=130            (require IR reflection; legit motion has blue ~150)
    
NIGHT_NO_IR (luma < 60, blue < 110):
    scene_change_threshold: 18.0  (moderate; some ambient flicker)
    min_blob_coherence: 0.35      (moderate strictness)
    luma_gate: max=80             (night should be dim; reject anomalies)
```

---

## Implementation: The Flow

```
┌─────────────────────────────────────────────────────────┐
│ New Frame Arrives                                       │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │ Calculate brightness metrics │
        │ - luma (luminance)           │
        │ - blue channel               │
        │ - scene_change               │
        └──────────────────┬───────────┘
                           │
                           ▼
        ┌──────────────────────────────────────┐
        │ TIER 1: Reject Transient Spikes      │
        │                                      │
        │ if scene_change > 20:                │
        │   → Skip motion detection            │
        │   → Log "transient_rejection"        │
        └──────────────────┬───────────────────┘
                           │ (not a transient)
                           ▼
        ┌──────────────────────────────────────┐
        │ TIER 2: Classify Environment          │
        │                                      │
        │ env = classify(luma, blue)            │
        │ Returns: DAYTIME, TWILIGHT,          │
        │   NIGHT_WITH_IR, NIGHT_NO_IR         │
        └──────────────────┬───────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────┐
        │ TIER 3: Select Thresholds            │
        │                                      │
        │ thresholds = PROFILES[env]            │
        │ (scene_change_threshold: 15-20)      │
        │ (luma_gate, blue_gate, etc.)         │
        └──────────────────┬───────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────┐
        │ Apply Environment-Specific Gates      │
        │                                      │
        │ if luma > gate_max:                  │
        │   → Reject (false positive marker)   │
        │ if blue < gate_min:                  │
        │   → Reject (no IR illumination)      │
        │                                      │
        │ if all gates passed:                 │
        │   → Run MOG2 motion detection        │
        └──────────────────┬───────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────┐
        │ Output Result                         │
        │ {                                    │
        │   motion_detected: bool,             │
        │   env: NIGHT_WITH_IR,                │
        │   reason: gate_rejection|detection   │
        │ }                                    │
        └──────────────────────────────────────┘
```

---

## Concrete Example: Test 2 Configuration

**Scenario:** IR filter ON, IR lights ON (night, optimal config)

### Before (Static Thresholds):
```
False positive clip: _motion_2026-08-12_13-28-16.mp4
├─ Luma: 104.3 (high for night)
├─ Blue: 117.1 (moderate in blue channel)
├─ Scene change: 4.2
├─ MOG2 foreground pixels: 8500
├─ Result: MOTION DETECTED ❌ (false positive)
└─ Reason: Static threshold missed the luma anomaly

Legitimate motion clip: motion_2026-08-12_17-36-48.mp4
├─ Luma: 79.2 (normal for IR-lit scene)
├─ Blue: 150.1 (high blue channel)
├─ Scene change: 3.1
├─ MOG2 foreground pixels: 8200
├─ Result: MOTION DETECTED ✓ (correct)
└─ Reason: Passed all checks
```

### After (Dynamic Thresholds):
```
False positive clip: _motion_2026-08-12_13-28-16.mp4
├─ Luma: 104.3, Blue: 117.1, Scene change: 4.2
├─ Step 1: 4.2 < 20.0 → Not a transient spike ✓
├─ Step 2: Classify env → NIGHT_WITH_IR (confident 0.90) ✓
├─ Step 3: Load NIGHT_WITH_IR profile:
│          • luma_gate max=95 → 104.3 > 95 → REJECT ✓
├─ Result: MOTION REJECTED ✓ (false positive caught!)
└─ Reason: Luma gate (104 > threshold 95)

Legitimate motion clip: motion_2026-08-12_17-36-48.mp4
├─ Luma: 79.2, Blue: 150.1, Scene change: 3.1
├─ Step 1: 3.1 < 20.0 → Not a transient spike ✓
├─ Step 2: Classify env → NIGHT_WITH_IR (confident 0.90) ✓
├─ Step 3: Load NIGHT_WITH_IR profile:
│          • luma_gate max=95 → 79.2 < 95 → PASS ✓
│          • blue_gate min=130 → 150.1 > 130 → PASS ✓
├─ Step 4: Run MOG2 → motion detected ✓
├─ Result: MOTION DETECTED ✓ (correct!)
└─ Reason: All gates passed + MOG2 foreground confirmed
```

**Impact:** False positive rate drops from 38% → ~15-20%

---

## Tuning SCENE_CHANGE_THRESHOLD by Environment

The scene_change_threshold should be **different per environment**:

```python
THRESHOLD_PROFILES = {
    'DAYTIME': {
        'scene_change_threshold': 15.0,  # Strict; few brightness shifts
    },
    'TWILIGHT': {
        'scene_change_threshold': 17.0,  # Moderate; some flicker
    },
    'NIGHT_NO_IR': {
        'scene_change_threshold': 18.0,  # Moderate; ambient variation
    },
    'NIGHT_WITH_IR': {
        'scene_change_threshold': 20.0,  # Relaxed; IR transients common
    },
}
```

**Why higher in IR mode?**
- IR lights can flicker or have transient reflections
- Legitimate motion might reveal/hide IR reflections (brief spikes)
- Need to tolerate 15–25 luma swing without rejecting the frame

**Why strict in daylight?**
- Daylight scenes are usually stable
- Large brightness changes indicate scene cuts or anomalies
- Safe to reject anything > 15

---

## Practical Tuning: What to Monitor

Once you implement dynamic thresholds, log and analyze:

### Per Frame:
```json
{
  "frame_num": 1234,
  "luma": 104.3,
  "blue": 117.1,
  "scene_change": 4.2,
  "env_detected": "NIGHT_WITH_IR",
  "env_confidence": 0.90,
  "passed_gates": {
    "scene_change": true,
    "luma": false,
    "blue": true
  },
  "motion_detected": false,
  "rejection_reason": "luma_gate (104 > 95)"
}
```

### Validate Against Historical Data:
Run your classifier on the 4 brightness_*.csv files:
- Test 1: 50 clips, expect ~25 flagged as false positives
- Test 2: 50 clips, expect ~19 flagged as false positives  
- Test 3: 50 clips, expect ~26 flagged as false positives
- Baseline: 90 clips, expect ~7 flagged as false positives

If validation passes, deploy to production.

---

## Deployment Checklist

- [ ] Implement `LightingEnvironmentClassifier` (see IMPLEMENTATION_GUIDE.md)
- [ ] Add brightness metric helpers (luma, blue channel)
- [ ] Define threshold profiles for all 5 environments
- [ ] Integrate gates into motion detection loop (scene_change, luma, blue)
- [ ] Add logging to track environment classification
- [ ] Validate against brightness_*.csv files (all 4 datasets)
- [ ] Test on new 50-clip validation dataset with Test 2 hardware
- [ ] Monitor false positive rate (target: <20%)
- [ ] Tune luma_max and blue_min based on real-world results
- [ ] Optionally add environment transition detection

---

## Expected Results

| Metric | Before | After | Target |
|---|---|---|---|
| False Positive Rate (Test 2) | 38% | 18–22% | <20% |
| Legitimate Motion Miss Rate | 0% | <2% | <5% |
| Per-Frame Processing Time | <50ms | <55ms | <100ms |
| Deployment Ready | No | Yes | Yes |

---

## Reference Documents

1. **BRIGHTNESS_ANALYSIS.md** — Statistical basis: 240 clips analyzed across 4 configs
2. **DYNAMIC_THRESHOLD_DESIGN.md** — Full architectural design with all 5 environments
3. **IMPLEMENTATION_GUIDE.md** — Working Python code and validation framework
4. **This document** — High-level strategy and scene_change_threshold role

---

## FAQ

**Q: Why not just use a single blue_channel threshold globally?**
A: The blue channel has different meanings in different environments:
- Daytime: high blue, no IR dependency
- Night with IR: very high blue (150+) for legit motion, medium (110) for false positives
- Night without IR: low blue even for legit motion

Only by classifying environment first can we interpret blue channel correctly.

**Q: What if I'm between environments (twilight)?**
A: The classifier returns confidence scores. Apply hysteresis: only switch environments if confidence > 0.8, otherwise stay in current state. This prevents flickering at boundary.

**Q: Can I tune thresholds without Test 2 hardware?**
A: Yes—validate against the historical brightness_*.csv files first. Once validation passes, deploy Test 2 hardware and collect real-world data.

**Q: What about false negatives (missed legitimate motion)?**
A: Monitor miss rate in validation. If INSTANT_STEP_THRESHOLD is too high or MIN_BLOB_COHERENCE too strict, lower them. Start conservative (higher thresholds) and relax gradually.

**Q: How often does environment classification need updating?**
A: Every frame (millisecond timescale). Use history/hysteresis to smooth transitions, but update aggressively to catch real environment changes.
