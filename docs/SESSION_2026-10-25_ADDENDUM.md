# Post-release addendum (25.10, ~03:30)

Laptop, runs with the mirror fix:
- Without a limiter: 29.5 FPS, spread still large (deviation 14.7 ms, p99 86 ms).
- **With a 28 FPS limiter: 27.6 FPS, perfectly even frames** (median 36 ms, deviation 0.66 ms, p99 38.6 ms, 0 long frames).

Conclusion: the ragged frametime on the laptop is cured by an FPS limit slightly below what the machine can do. Next step — make this the default for weak graphics cards (an auto-limiter based on average FPS) or suggest it in the launcher.
