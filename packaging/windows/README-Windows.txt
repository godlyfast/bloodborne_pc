Bloodborne (bbport) for Windows 10/11

You need your own dump of Bloodborne (CUSA03173, version 1.09) and a GPU with Vulkan 1.3 and a
current driver (AMD Adrenalin, NVIDIA GeForce, Intel Arc).

1. Unpack the zip anywhere (not into Program Files).
2. Start Bloodborne.exe, choose the game folder (the one with eboot.bin), press Play.
3. In the game: Insert (or L3+R3) opens the port's settings menu.

Everything the port writes stays in this folder: bbport.ini (settings), user\ (saves),
out\ (prepared game files), logs\ (one log per run). For a report send the newest file from logs\.

This build has only the new memory model: the GPU uses the game's memory in place. If the driver
cannot do that, the game stops at start with a line beginning "STOP: the GPU driver cannot use the
game's memory in place" — please send that log.

Online play: the launcher's Online section, two pools as on Linux: Seamless Hunt (your shadNet
account from seamlesshunt.com, BBSC seamless co-op) or The Hunter's Dream (sign-in with Discord);
UPnP and a connection check. The online module and its libraries are in online\ (bbnet20.dll):
to try another build of it (a newer BBSC), replace that folder.
Mods: the launcher's Mods section (unpack each mod into its own folder in mods\, choose the load
order) and shadPS4 XML patches for 01.09 (patches\).
FSR 4.1.1: the port ships nothing of AMD's. In the launcher choose the FSR 4.1.1 upscaler, then
"Build from an AMD DLL..." and pick amd_fidelityfx_upscaler_dx12.dll 4.1.x (OptiScaler and many
games have it); a minute or two later the set is in fsr4_411\. FSR 4.1.2's models (RDNA2, Lite):
pick the driver's amdxcffx64.dll (Adrenalin 26.10.1+, under C:\Windows\System32\DriverStore\
FileRepository\u0*\) together with the upscaler DLL. The recording runs on vkd3d-proton and DXVK
(tools\fsr4cap\bin, LGPL-2.1 / zlib), so any GPU with Vulkan can build the set.
DLSS (GeForce RTX): when bin\bbport_dlss.dll and bin\nvngx_dlss.dll are in the package, choose
DLSS in the in-game menu (Insert) or the launcher; Frame Generation needs RTX 40/50 and
bin\nvngx_dlssg.dll.
