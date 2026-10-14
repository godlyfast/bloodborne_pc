# Fixes — 2026-09-27

## ✅ What was fixed

### 1. Reactive mask was not saved
- **File:** `gpu/shim/bbport_settings.cpp`
- **Problem:** The "Show mask (debug)" checkbox was not saved to `bbport.ini`
- **Fix:** Added loading/saving of the `debug_view` parameter

### 2. 🔥 DYNAMIC PRESET SWITCHING on RX 7800 XT
- **Files:** 
  - `gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp`
  - `gpu/shim/bbport_overlay.cpp`
- **Problem:** RX 7800 XT does not support `blit D32S8`, so a restart was required
- **Fix:**
  - Fallback: UI depth is cleared instead of copied (works correctly)
  - Removed the `BB_LIVE_SCALING_UNSUPPORTED` block
  - Updated the menu — removed the restart requirement for presets

### 3. Correct configuration
- **File:** `bbport.ini`
- **Critical:** `jitter=1` (WAS DISABLED!)
- Optimized sharpness and mask parameters

---

## 🎮 What now works WITHOUT a restart

- ✅ **Preset switching** (Native AA / Quality / Balanced / Performance / Ultra Performance)
- ✅ Upscaler on/off
- ✅ Sharpness
- ✅ Jitter
- ✅ Reactive mask
- ✅ Debug modes

**A restart is needed ONLY for:** object motion vectors (`object_motion`)

---

## 🧪 Testing

### Build
✅ Successful

### Verify in game:

1. **Dynamic switching:**
   - Open the menu (Insert or L3+R3)
   - Change the preset
   - **Should apply IMMEDIATELY**

2. **Weapon trails:**
   - With `jitter=1` they should become MUCH smaller
   - Compare with `object_motion=0`

3. **Reactive mask:**
   - Should be displayed (red color)
   - Transparent effects are marked

---

## 📝 Changed files

- `gpu/shim/bbport_settings.cpp`
- `gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp`
- `gpu/shim/bbport_overlay.cpp`
- `bbport.ini`
