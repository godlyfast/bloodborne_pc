// SPDX-License-Identifier: GPL-2.0-or-later
// bbport: whether a clear shader (cs 8b355b5a) may be replaced by a Vulkan clear of the image the
// texture cache holds at its target (Rasterizer::IsComputeImageClear). vkCmdClearColorImage writes
// the color in the image's create format, and the cache can hold an image created in another
// format of the same size there: FindImage reuses one of any format of the same class through a
// view. R32Sfloat where the game now draws R8G8B8A8Unorm got the color as float bits; the SSR
// mask (ps 749e4f9e, 428x240) was garbage and the blur chain smeared the world for as long as the
// game kept those addresses (2026-10-29: within about ten loads with the SSR startup patch; with
// the game's shader, BB_HLE_OFF=4, none in about 80).
#pragma once

#include <cstdint>

namespace BbClearFormat {

/// Experiment bit (the second number of BB_TOGGLE_FILE): the clear is replaced on an image of any
/// format again, as before 2026-10-29, for a live A/B of the smear in one load.
inline constexpr std::uint64_t AllowMismatch = 512;

enum class Verdict {
    Replace,         ///< the image's create format is the one the shader writes
    Unmapped,        ///< the shader's data and number format have no Vulkan format: the shader runs
    Mismatch,        ///< the image was created in another format: the shader runs
    ReplaceMismatch, ///< either of the two, replaced anyway (experiment 512)
};

/// `requested`: the Vulkan format of the shader's target buffer (GcnToVk::TrySurfaceFormat of its
/// data and number format; the zero value, eUndefined, when the pair has none), `created`: the
/// image's create format. Not replaced, the shader runs and writes the game's memory, from which
/// the texture cache refreshes the image (as with BB_HLE_OFF=4, which kept those masks sharp).
template <typename Format>
constexpr Verdict Decide(Format requested, Format created, bool allow_mismatch) {
    if (requested != Format{} && requested == created) {
        return Verdict::Replace;
    }
    if (allow_mismatch) {
        return Verdict::ReplaceMismatch;
    }
    return requested == Format{} ? Verdict::Unmapped : Verdict::Mismatch;
}

} // namespace BbClearFormat
