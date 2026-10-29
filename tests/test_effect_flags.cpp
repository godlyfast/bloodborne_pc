// SPDX-License-Identifier: GPL-2.0-or-later
#include "bbport_effect_flags.h"
#include "bbport_clear_format.h"

#include <array>
#include <cassert>
#include <cstdio>
#include <optional>

int main() {
    std::array<std::uint8_t, 0x29a0> context{};
    const auto put = [&](std::size_t offset, std::uint64_t value) {
        std::memcpy(context.data() + offset, &value, sizeof(value));
    };
    // A menu/auxiliary context must stay off despite the user's enabled preference.
    assert(!BbEffectFlags::SsaoEnabled(context, true));
    put(0x10d0 + 0x68, 0x1040000000ull);
    assert(!BbEffectFlags::SsaoEnabled(context, true));
    put(0x48, 8);
    assert(BbEffectFlags::SsaoEnabled(context, true));
    assert(!BbEffectFlags::SsaoEnabled(context, false));
    // Follow both selector flags exactly; do not use a nonselected target as fallback.
    context[0x10d0 + 0x1b8] = 1;
    assert(BbEffectFlags::SsaoEnabled(context, true));
    context[0x10d0 + 0x189] = 1;
    assert(!BbEffectFlags::SsaoEnabled(context, true));
    put(0x10d0 + 0xc0, 0x1041000000ull);
    assert(BbEffectFlags::SsaoEnabled(context, true));
    // Removing/reinitializing a target must disable the pass again.
    put(0x10d0 + 0xc0, 0);
    assert(!BbEffectFlags::SsaoEnabled(context, true));
    assert(!BbEffectFlags::SsaoEnabled(std::span(context).first(0x1288), true));
    std::puts("effect-flags: SSAO context capability and target selection OK");

    // Motion blur: only where setup built both velocity maps (capability 0x420).
    context = {};
    assert(!BbEffectFlags::MotionBlurSupported(context));
    put(0xcf8, 0x1042000000ull);
    put(0xd50, 0x1043000000ull);
    assert(!BbEffectFlags::MotionBlurSupported(context));
    put(0x48, 0x2207); // the game's 128x128 context: no 0x420
    assert(!BbEffectFlags::MotionBlurSupported(context));
    put(0x48, 0x20);
    assert(BbEffectFlags::MotionBlurSupported(context));
    put(0x48, 0x400);
    assert(BbEffectFlags::MotionBlurSupported(context));
    // Capability without the maps (setup not done, or released): not yet.
    put(0xd50, 0);
    assert(!BbEffectFlags::MotionBlurSupported(context));
    put(0xd50, 0x1043000000ull);
    put(0xcf8, 0);
    assert(!BbEffectFlags::MotionBlurSupported(context));
    assert(!BbEffectFlags::MotionBlurSupported(std::span(context).first(0xd50)));
    std::puts("effect-flags: motion blur context capability and velocity maps OK");

    // The game's anti-aliasing: capability 0x10 only.
    context = {};
    assert(!BbEffectFlags::GameAaSupported(context));
    put(0x48, 0x2207 & ~0x10ull);
    assert(!BbEffectFlags::GameAaSupported(context));
    put(0x48, 0x10);
    assert(BbEffectFlags::GameAaSupported(context));
    assert(!BbEffectFlags::GameAaSupported(std::span(context).first(0x48)));
    std::puts("effect-flags: game AA context capability OK");

    // SSR: capability 0x800 and every target the pass reads.
    context = {};
    assert(!BbEffectFlags::SsrSupported(context));
    const auto ssr_ready = [&] {
        context = {};
        put(0x48, 0x1d1fe1f); // the scene context the patch turns SSR on in
        context[0x1088] = 1;
        put(0x1090, 0x1044000000ull);
        put(0x10a8, 0x1045000000ull);
        put(0xe58, 0x1046000000ull);
        put(0xe68, 0x1047000000ull);
        put(0xe70, 0x1048000000ull);
        context[0x25b0] = 1;
        put(0x2520, 0x1049000000ull);
        context[0x296f] = 1;
        put(0xf48, 0x104a000000ull);
    };
    ssr_ready();
    assert(BbEffectFlags::SsrSupported(context));
    for (const std::size_t pointer : {0x1090, 0x10a8, 0xe58, 0xe68, 0xe70, 0x2520, 0xf48}) {
        ssr_ready();
        put(pointer, 0);
        assert(!BbEffectFlags::SsrSupported(context));
    }
    for (const std::size_t flag : {0x1088, 0x25b0, 0x296f}) {
        ssr_ready();
        context[flag] = 0;
        assert(!BbEffectFlags::SsrSupported(context));
    }
    for (const std::uint64_t caps : {0x422014ull, 0x2207ull, 0x3200ull, 0x200ull, 0x10000ull}) {
        ssr_ready();
        put(0x48, caps); // no 0x800: no Prev HDR or SSR output was built
        assert(!BbEffectFlags::SsrSupported(context));
    }
    ssr_ready();
    put(0x48, 0x800);
    assert(BbEffectFlags::SsrSupported(context));
    assert(!BbEffectFlags::SsrSupported(std::span(context).first(0x2970)));
    std::puts("effect-flags: SSR context capability and targets OK");

    // SSR history: off after setup, on at the first copy gate, then the game's own value.
    using BbEffectFlags::SsrAtCopy;
    assert(SsrAtCopy(nullptr, 0, 0) == 0); // contexts the port does not track follow the game
    assert(SsrAtCopy(nullptr, 0, 1) == 1);
    BbEffectFlags::SsrHistory slot = BbEffectFlags::SsrAfterSetup(0x1028863340, false);
    assert(slot.context == 0x1028863340 && !slot.wanted && !slot.primed);
    assert(SsrAtCopy(&slot, 0, 0) == 0); // unsupported: SSR stays off
    assert(!slot.primed);
    slot = BbEffectFlags::SsrAfterSetup(0x1028863340, true);
    assert(slot.wanted && !slot.primed);
    assert(SsrAtCopy(&slot, 0, 0) == 1); // first gate: the copy is recorded, SSR from the next frame
    assert(slot.primed);
    assert(SsrAtCopy(&slot, 0, 1) == 1);
    assert(SsrAtCopy(&slot, 0, 0) == 0); // switched off afterwards (debug menu): stays off
    slot = BbEffectFlags::SsrAfterSetup(0x1028863340, true); // set up again (a load)
    assert(!slot.primed);
    assert(SsrAtCopy(&slot, 0, 0) == 1);
    std::puts("effect-flags: SSR history priming OK");

    // The experiments, a frame at a time: the byte each of the game's tests of +0x2974 sees.
    struct Frame {
        std::uint8_t downsample, pass, lighting, copy;
        bool operator==(const Frame&) const = default;
    };
    constexpr std::uint64_t hold = BbEffectFlags::SsrHoldOff;
    constexpr std::uint64_t unlit = BbEffectFlags::SsrUnlit;
    constexpr std::uint64_t freeze = BbEffectFlags::SsrFreeze;
    std::uint8_t ssr = 0;
    int mode = 2; // [+0x68]: the lighting tests at 0x22a5466 only in mode 2, at 0x22a7384 in both
    // `bits` before the downsample, `late` from the copy on (a toggle within a frame).
    const auto frame = [&](std::uint64_t bits, std::optional<std::uint64_t> late = {}) {
        Frame f{};
        ssr = f.downsample = BbEffectFlags::SsrAtDownsample(&slot, bits, ssr);
        f.pass = ssr; // 0x22a48aa is not hooked
        const std::uint8_t first = mode == 2 ? BbEffectFlags::SsrAtLighting(&slot, bits, ssr) : ssr;
        ssr = f.lighting = BbEffectFlags::SsrAtLighting(&slot, bits, first);
        assert(mode != 2 || first == f.lighting); // the second bind keeps what the first stored
        ssr = f.copy = SsrAtCopy(&slot, late.value_or(bits), ssr);
        return f;
    };
    const auto steady = [&] {
        slot = BbEffectFlags::SsrAfterSetup(0x1028863340, true);
        ssr = 0;
        assert((frame(0) == Frame{0, 0, 0, 1})); // the priming frame
        assert((frame(0) == Frame{1, 1, 1, 1}));
        assert(!BbEffectFlags::SsrPending(slot));
    };
    // Contexts the port does not track, and those without SSR targets, follow the game.
    for (const std::uint64_t bits : {hold, unlit, freeze, unlit | freeze}) {
        assert(BbEffectFlags::SsrAtDownsample(nullptr, bits, 1) == 1);
        assert(BbEffectFlags::SsrAtLighting(nullptr, bits, 1) == 1);
        BbEffectFlags::SsrHistory off = BbEffectFlags::SsrAfterSetup(0x1028863340, false);
        assert(BbEffectFlags::SsrAtLighting(&off, bits, 1) == 1);
        assert(SsrAtCopy(&off, bits, 1) == (bits & hold ? 0 : 1)); // 64 as before
        assert(!BbEffectFlags::SsrPending(off));
    }
    for (const int binds : {2, 1}) {
        mode = binds;
        // No bits: every test sees 1, nothing pending (the gates' fast paths).
        steady();
        for (int i = 0; i < 3; ++i) {
            assert((frame(0) == Frame{1, 1, 1, 1}));
        }
        // 128: SSR runs and the copy still happens, every frame; the lighting never sees it.
        for (int i = 0; i < 4; ++i) {
            assert((frame(unlit) == Frame{1, 1, 0, 1}));
            assert(slot.unlit && !slot.lit_hidden && BbEffectFlags::SsrPending(slot));
        }
        assert((frame(0) == Frame{1, 1, 1, 1})); // cleared: the next copy ends it
        assert(!BbEffectFlags::SsrPending(slot));
        // 128 cleared between the lighting and the copy: the switch is still set back.
        assert((frame(unlit, 0) == Frame{1, 1, 0, 1}));
        assert(!BbEffectFlags::SsrPending(slot));
        // 128, then a pass without the copy (0x36): the next downsample sets it back.
        ssr = BbEffectFlags::SsrAtDownsample(&slot, unlit, ssr);
        ssr = BbEffectFlags::SsrAtLighting(&slot, unlit, ssr);
        assert(ssr == 0 && slot.lit_hidden);
        assert((frame(unlit) == Frame{1, 1, 0, 1}));
        assert((frame(0) == Frame{1, 1, 1, 1}) && !BbEffectFlags::SsrPending(slot));
        // 64 -> 256: the first copy after 64 is of a frame without reflections, then it stays.
        assert((frame(hold) == Frame{1, 1, 1, 0}));
        assert(!slot.primed);
        assert((frame(hold) == Frame{0, 0, 0, 0}));
        assert((frame(freeze) == Frame{0, 0, 0, 1})); // primed and frozen at one copy
        assert(slot.primed && slot.frozen && !slot.freeze_zeroed);
        for (int i = 0; i < 4; ++i) {
            assert((frame(freeze) == Frame{1, 1, 1, 0}));
            assert(slot.frozen && slot.freeze_zeroed);
        }
        // Cleared: the downsample sets it back and copies resume.
        assert((frame(0) == Frame{1, 1, 1, 1}));
        assert(!BbEffectFlags::SsrPending(slot));
        assert((frame(0) == Frame{1, 1, 1, 1}));
        // 256 from a running scene: this frame is the frozen one.
        assert((frame(freeze) == Frame{1, 1, 1, 1}));
        assert((frame(freeze) == Frame{1, 1, 1, 0}));
        // 256 cleared between the lighting and the copy: that copy unfreezes it.
        assert((frame(freeze, 0) == Frame{1, 1, 1, 1}));
        assert(!BbEffectFlags::SsrPending(slot));
        // A frame without the downsample (+0x296f): the copy sets it back first.
        assert((frame(freeze) == Frame{1, 1, 1, 1}));
        assert((frame(freeze) == Frame{1, 1, 1, 0}));
        ssr = SsrAtCopy(&slot, freeze, ssr);
        assert(ssr == 0 && slot.frozen && slot.freeze_zeroed); // still frozen
        ssr = SsrAtCopy(&slot, 0, ssr);
        assert(ssr == 1 && !BbEffectFlags::SsrPending(slot));
        // 64 set between a skipped copy and the next downsample: nothing sets the switch back.
        assert((frame(freeze) == Frame{1, 1, 1, 1}));
        assert((frame(freeze) == Frame{1, 1, 1, 0}));
        assert((frame(hold) == Frame{0, 0, 0, 0}));
        assert(!slot.primed && !BbEffectFlags::SsrPending(slot));
        assert((frame(hold | freeze | unlit) == Frame{0, 0, 0, 0}));
        assert((frame(0) == Frame{0, 0, 0, 1}) && slot.primed); // primed again
        assert((frame(0) == Frame{1, 1, 1, 1}));
        // 64 seen by the downsample but gone by the copy: that copy sets the switch back (and
        // still skips under 256), else SSR would stay off with nothing left to end.
        assert((frame(freeze) == Frame{1, 1, 1, 1}));
        assert((frame(freeze) == Frame{1, 1, 1, 0}));
        assert((frame(hold, freeze) == Frame{0, 0, 0, 0}));
        assert(slot.primed && slot.frozen && slot.freeze_zeroed);
        assert((frame(0) == Frame{1, 1, 1, 1}) && !BbEffectFlags::SsrPending(slot));
        assert((frame(freeze) == Frame{1, 1, 1, 1}));
        assert((frame(freeze) == Frame{1, 1, 1, 0}));
        assert((frame(hold, 0) == Frame{0, 0, 0, 1}) && !BbEffectFlags::SsrPending(slot));
        assert((frame(0) == Frame{1, 1, 1, 1}));
        ssr = BbEffectFlags::SsrAtDownsample(&slot, unlit, ssr); // 128, a pass without the copy
        ssr = BbEffectFlags::SsrAtLighting(&slot, unlit, ssr);
        assert(ssr == 0 && slot.lit_hidden);
        assert((frame(hold, 0) == Frame{0, 0, 0, 1}) && !BbEffectFlags::SsrPending(slot));
        assert((frame(0) == Frame{1, 1, 1, 1}));
        // 64 set while the lighting's switch is cleared: the copy keeps it off.
        assert((frame(unlit, hold) == Frame{1, 1, 0, 0}));
        assert(!slot.primed && !BbEffectFlags::SsrPending(slot));
        // 64 with 128 in a running scene: 64 alone.
        steady();
        assert((frame(hold | unlit) == Frame{1, 1, 1, 0}));
        assert(!slot.primed && !BbEffectFlags::SsrPending(slot));
        // 128 and 256 together (not meant for use): balanced, and clearing them at any test leaves
        // nothing pending and SSR on.
        for (int when = 0; when < 3; ++when) {
            steady();
            assert((frame(unlit | freeze) == Frame{1, 1, 0, 1}));
            assert((frame(unlit | freeze) == Frame{1, 1, 0, 0}));
            assert((frame(unlit | freeze) == Frame{1, 1, 0, 0}));
            if (when == 0) {
                assert((frame(0) == Frame{1, 1, 1, 1}));
            } else if (when == 1) {
                assert((frame(unlit | freeze, 0) == Frame{1, 1, 0, 1}));
            } else {
                assert((frame(unlit | freeze, unlit) == Frame{1, 1, 0, 1})); // 256 first, then 128
                assert((frame(0) == Frame{1, 1, 1, 1}));
            }
            assert(!BbEffectFlags::SsrPending(slot) && slot.primed);
            assert((frame(0) == Frame{1, 1, 1, 1}));
        }
        // A new setup ends the experiments with a new Prev HDR.
        assert((frame(freeze) == Frame{1, 1, 1, 1}));
        assert((frame(freeze) == Frame{1, 1, 1, 0}));
        slot = BbEffectFlags::SsrAfterSetup(0x1028863340, true);
        ssr = 0;
        assert(!BbEffectFlags::SsrPending(slot));
        assert((frame(freeze) == Frame{0, 0, 0, 1}) && slot.frozen);
        assert((frame(0) == Frame{1, 1, 1, 1}) && !BbEffectFlags::SsrPending(slot));
    }
    std::puts("effect-flags: SSR experiments OK");

    // The compute clear's replacement (Rasterizer::IsComputeImageClear): only on an image created
    // in the format the shader writes; experiment 512 replaces on any image again. The decision
    // only: whether the texture cache hands back such an image, and what vkCmdClearColorImage
    // writes into it, need the game (the A/B with bit 512).
    {
        // VkFormat values; the zero value is VK_FORMAT_UNDEFINED, as for vk::Format.
        enum class Format : int {
            Undefined = 0,
            R8G8B8A8Unorm = 37,
            R8G8B8A8Srgb = 43,
            R32Sfloat = 100,
        };
        using BbClearFormat::Verdict;
        const auto decide = [](Format requested, Format created, bool allow) {
            return BbClearFormat::Decide(requested, created, allow);
        };
        // The smear (2026-10-29): R8G8B8A8Unorm written into an image created as R32Sfloat.
        assert(decide(Format::R8G8B8A8Unorm, Format::R32Sfloat, false) == Verdict::Mismatch);
        assert(decide(Format::R32Sfloat, Format::R8G8B8A8Unorm, false) == Verdict::Mismatch);
        // Same size and class, another encoding: the Vulkan clear would encode sRGB.
        assert(decide(Format::R8G8B8A8Unorm, Format::R8G8B8A8Srgb, false) == Verdict::Mismatch);
        // The formats agree: replaced, whatever the bit.
        assert(decide(Format::R8G8B8A8Unorm, Format::R8G8B8A8Unorm, false) == Verdict::Replace);
        assert(decide(Format::R8G8B8A8Unorm, Format::R8G8B8A8Unorm, true) == Verdict::Replace);
        assert(decide(Format::R32Sfloat, Format::R32Sfloat, false) == Verdict::Replace);
        // A pair without a Vulkan format: the shader runs, also on an image of no format.
        assert(decide(Format::Undefined, Format::R32Sfloat, false) == Verdict::Unmapped);
        assert(decide(Format::Undefined, Format::Undefined, false) == Verdict::Unmapped);
        // Experiment 512: every one of them replaced, as before.
        assert(decide(Format::R8G8B8A8Unorm, Format::R32Sfloat, true) == Verdict::ReplaceMismatch);
        assert(decide(Format::R8G8B8A8Unorm, Format::R8G8B8A8Srgb, true) ==
               Verdict::ReplaceMismatch);
        assert(decide(Format::Undefined, Format::R32Sfloat, true) == Verdict::ReplaceMismatch);
        // Its bit is none of the SSR experiments' (the copy gate masks them, not this one).
        static_assert((BbClearFormat::AllowMismatch & (BbEffectFlags::SsrHoldOff |
                                                       BbEffectFlags::SsrUnlit |
                                                       BbEffectFlags::SsrFreeze)) == 0);
        static_assert(BbClearFormat::Decide(Format::R32Sfloat, Format::R32Sfloat, false) ==
                      Verdict::Replace);
    }
    std::puts("effect-flags: image clear format check OK");
}
