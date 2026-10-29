// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <cstdint>
#include <cstring>
#include <span>

namespace BbEffectFlags {

// Bloodborne 1.09: 0x22c4cb3 clears SSAO when the context's capability bit 3
// (+0x48) is absent. 0x22a3efb uses the target at +0x10d0 via 0xe669a0,
// then dereferences its result without a null check at 0x22a3f07.
// A live preference must not re-enable this pass on a context without its target.
inline bool SsaoEnabled(std::span<const std::uint8_t> context, bool requested) {
    constexpr std::size_t target = 0x10d0;
    if (!requested || context.size() < target + 0x1b9) {
        return false;
    }
    std::uint64_t capabilities = 0;
    std::memcpy(&capabilities, context.data() + 0x48, sizeof(capabilities));
    if (!(capabilities & 8)) {
        return false;
    }
    // The same selector as guest 0xe669a0. A target may not yet be initialized,
    // even when the context is configured to support SSAO.
    const bool alternate = context[target + 0x1b8] && context[target + 0x189];
    std::uint64_t resource = 0;
    std::memcpy(&resource, context.data() + target + (alternate ? 0xc0 : 0x68), sizeof(resource));
    return resource != 0;
}

// Setup (0x22c39f0) runs after the constructor whose tail reports the context, so these say
// only whether a live preference may turn a pass back on; a context without support keeps
// the switch the game left.

// 0x22c3d8f builds the half-size velocity maps (+0xce0, +0xd38; 0x2266420 keeps each resource
// at +0x18) and the motion blur object (+0x28b0) only with capability 0x420, and 0x22c3e62
// clears motion blur otherwise. 0x229ef1b and 0x22ab35b take [+0xcf8] and [+0xd50] unchecked.
inline bool MotionBlurSupported(std::span<const std::uint8_t> context) {
    if (context.size() < 0xd58) {
        return false;
    }
    std::uint64_t capabilities = 0;
    std::uint64_t velocity = 0;
    std::uint64_t velocity_other = 0;
    std::memcpy(&capabilities, context.data() + 0x48, sizeof(capabilities));
    std::memcpy(&velocity, context.data() + 0xcf8, sizeof(velocity));
    std::memcpy(&velocity_other, context.data() + 0xd50, sizeof(velocity_other));
    return (capabilities & 0x420) && velocity != 0 && velocity_other != 0;
}

// 0x22c4e36 builds the game's anti-aliasing (FXAA, +0x1bc8 via 0xe58b00) only with capability
// 0x10, and 0x22c4e75 clears it otherwise.
inline bool GameAaSupported(std::span<const std::uint8_t> context) {
    if (context.size() < 0x50) {
        return false;
    }
    std::uint64_t capabilities = 0;
    std::memcpy(&capabilities, context.data() + 0x48, sizeof(capabilities));
    return (capabilities & 0x10) != 0;
}

// Screen-space reflections (the community startup patch, 2026-10-28). The patch turns +0x2974
// on at 0x22c4fd0, which setup runs only with capability 0x10000; the game builds the SSR
// targets only with 0x800 (0x22c427a): Prev HDR +0x1078 (texture +0x1090, target +0x10a8, built
// flag +0x1088 from 0x2266032) and the SSR output +0xe40 (+0xe58, view +0xe68, target +0xe70).
// The pass also takes the scaled depth of +0x24f8 (+0x2520, both built: +0x25b0) and the
// full-size depth [+0xf48], none of them checked (0x22a48cd, 0x22a4a83, 0x22b1575).
inline bool SsrSupported(std::span<const std::uint8_t> context) {
    if (context.size() < 0x2980) {
        return false;
    }
    const auto u64_at = [&](std::size_t offset) {
        std::uint64_t value = 0;
        std::memcpy(&value, context.data() + offset, sizeof(value));
        return value;
    };
    return (u64_at(0x48) & 0x800) && context[0x1088] && u64_at(0x1090) && u64_at(0x10a8) &&
           u64_at(0xe58) && u64_at(0xe68) && u64_at(0xe70) && context[0x25b0] && u64_at(0x2520) &&
           context[0x296f] && u64_at(0xf48);
}

// Each setup builds a new Prev HDR, and each frame reads it (0x22a4997) before the same frame's
// copy of the scene refreshes it (0x22aa07c, the last test of +0x2974 in 0x22a0a30). So the
// first SSR frame after a load sampled a history no frame of that setup had written. After
// setup the context keeps SSR off; at its first copy gate SSR turns on, so that frame records
// the copy and the next one reflects a written history.
//
// A frame tests +0x2974 at the depth downsample (0x22a37e2, only with +0x296f), the SSR pass
// (0x22a48aa), the lighting's binds of the SSR output [+0xe68] (without SSR a global fallback
// texture) and the copy (0x22aa07c, skipped on pass 0x36). The lighting binds it at 0x22a5466 only
// in a context of mode 2 ([+0x68], 0x22a4b99), then at 0x22a7384, which mode 1 reaches alone. The
// experiments below clear it for some of these tests and put it back for the others.
struct SsrHistory {
    std::uint64_t context = 0;
    bool wanted = false; ///< SSR was requested and the context has everything it needs
    bool primed = false; ///< the copy that writes the history was recorded
    bool unlit = false; ///< experiment 128 keeps the SSR output out of the lighting
    bool lit_hidden = false; ///< +0x2974 cleared for this frame's lighting: set back at the copy
    bool frozen = false; ///< experiment 256: Prev HDR written once since the bit was set
    bool freeze_zeroed = false; ///< a copy skipped for it: set back at the next downsample
};

/// Experiment bits (the second number of BB_TOGGLE_FILE) for A/B tests in a smeared scene, one at
/// a time (128 and 256 together only keep their switches balanced). 64 holds SSR off in the
/// tracked contexts, each primed again once it is cleared. It takes precedence: while it is set
/// nothing sets +0x2974 back, and its copy gate drops the state of the other two.
inline constexpr std::uint64_t SsrHoldOff = 64;
/// SSR and the copy into Prev HDR still run every frame, but the lighting composites the fallback
/// texture: Prev HDR never holds reflections, and the SSR pass reads a history without them.
inline constexpr std::uint64_t SsrUnlit = 128;
/// One bounce: the first copy after the bit is set writes Prev HDR and the later ones are skipped,
/// so SSR and the lighting reflect that one history every frame. Set after 64, it holds a frame
/// without reflections. Cleared, the next copy unfreezes it.
inline constexpr std::uint64_t SsrFreeze = 256;

/// An experiment has to end or set +0x2974 back: the downsample's and copy's gates must look.
inline bool SsrPending(const SsrHistory& slot) {
    return slot.unlit || slot.lit_hidden || slot.frozen || slot.freeze_zeroed;
}

/// At setup's exit, for a context whose SSR the patch turned on (+0x2974 then goes to 0).
inline SsrHistory SsrAfterSetup(std::uint64_t context, bool supported) {
    return {context, supported, false};
}

/// The other experiments' state goes with experiment 64; +0x2974 stays as it is.
inline void SsrDropExperiments(SsrHistory* slot) {
    slot->unlit = slot->lit_hidden = slot->frozen = slot->freeze_zeroed = false;
}

/// +0x2974 that an experiment cleared goes back to 1 at whichever of the downsample and the copy
/// comes first: the one meant to set it back does not always run (a pass without the copy, a
/// frame without the downsample), and SSR would stay off.
inline std::uint8_t SsrPutBack(SsrHistory* slot, std::uint8_t ssr) {
    if (!slot->lit_hidden && !slot->freeze_zeroed) {
        return ssr;
    }
    slot->lit_hidden = slot->freeze_zeroed = false;
    return 1;
}

/// Before the depth downsample's test, a frame's first: the value +0x2974 gets (`ssr`: its value
/// now, `bits`: the experiment bits). With 64 the state stays for the copy gate, which drops it
/// and keeps SSR off: dropped here, a copy that no longer sees 64 would have nothing to set back
/// and leave SSR off until the next setup.
inline std::uint8_t SsrAtDownsample(SsrHistory* slot, std::uint64_t bits, std::uint8_t ssr) {
    if (!slot || !slot->wanted || (bits & SsrHoldOff)) {
        return ssr;
    }
    return SsrPutBack(slot, ssr);
}

/// Before each of the lighting's tests (0x22a5466, 0x22a7384): a second one sees the value the
/// first stored and keeps it.
inline std::uint8_t SsrAtLighting(SsrHistory* slot, std::uint64_t bits, std::uint8_t ssr) {
    if (!slot || !slot->wanted || !slot->primed || !ssr ||
        (bits & (SsrHoldOff | SsrUnlit)) != SsrUnlit) {
        return ssr;
    }
    slot->unlit = slot->lit_hidden = true;
    return 0;
}

/// Before the copy gate's test: the value +0x2974 gets.
inline std::uint8_t SsrAtCopy(SsrHistory* slot, std::uint64_t bits, std::uint8_t ssr) {
    if (!slot) {
        return ssr;
    }
    if (bits & SsrHoldOff) {
        SsrDropExperiments(slot);
        slot->primed = false;
        return 0;
    }
    if (!slot->wanted) {
        return ssr;
    }
    ssr = SsrPutBack(slot, ssr);
    if (!(bits & SsrUnlit)) {
        slot->unlit = false;
    }
    if (!slot->primed) {
        slot->primed = true;
        ssr = 1;
    }
    if (!(bits & SsrFreeze) || !ssr) {
        slot->frozen = false;
        return ssr;
    }
    if (!slot->frozen) {
        slot->frozen = true; // this copy writes the history reflected until the bit is cleared
        return 1;
    }
    slot->freeze_zeroed = true;
    return 0;
}

} // namespace BbEffectFlags
