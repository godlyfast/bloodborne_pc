The first version of object motion vectors is built, the game launches, and there are no startup errors. But I have not tested it in the game itself yet: the G-buffer shaders with the new code only compile when a level loads, so the main test is still ahead.

How it works:
- The vertex shader of every G-buffer draw saves the final vertex positions and reads the positions of the same vertices from the previous frame.
- The pixel shader writes the difference to an additional G-buffer target.
- Where an object moved, FSR gets this vector; everywhere else it gets the camera vector.
- Positions are saved only for moving draws: those whose vertex shader constants changed (object matrix, bones). Static geometry wastes no memory.
- This covers any animation computed by the vertex shader: skinning, weapons, cloth, enemies.

Please load into the game and reply "done". I will check the log: how many draws are moving and for how many of them previous-frame positions were found. Then run around with the saw on your back. For comparison I can toggle object vectors on the fly, leaving only camera vectors.
