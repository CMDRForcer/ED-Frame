ED-Frame 1.0.9 - Portable Windows Edition
===================================================================

1. Extract the complete ZIP archive.
2. Start ED-Frame.exe.
3. Keep the _internal folder next to ED-Frame.exe.

Python and the INSTALL_REQUIREMENTS step are not required for this portable build.

This release works with catalog server 0.9.4. NAV includes A-B-A trading loops,
Carrier commodity offers, a manual starting system and unlimited commodity radius.
A coordinated cockpit and asynchronous startup improve everyday use. NAV search
inputs survive page changes within the session. Trading suggestions show regional
coverage and original quote ages; prices and stock can change before arrival.
Large cold searches can still take time.

When upgrading, quit the old app completely, including its tray process, before
starting this version. Extract into a new folder; existing profiles are reused.

User settings, service credentials, caches and Journal cursors are stored under
%LOCALAPPDATA%\ED-Frame and are not written into this folder.

Current documentation:
- ED-Frame-1.0-Guide-EN.md (English: features, installation and privacy)
- ED-Frame-1.0-Guide-DE.md (Deutsch: Funktionen, Installation und Datenschutz)
- _internal/README.md (detailed workspace overview)

The enclosed 1.5.5 PDF manuals are historical references, not current 1.0 guides.

ED-Frame's own catalog server supports mining/merit routes, markets, station
services and module/ship searches. The ED-Frame and EDDN community connections
are enabled by default for new profiles. Disable them under Connections to use
retained local data without those services. ED-Frame shares supported anonymous
public observations, not Commander identities, raw Journal files, builds or keys.
Frontier CAPI and INARA require separate setup.

1.0 starts a new public release line and succeeds the older EDEC/ED-Frame builds,
including 1.5.43. Extract this release into a separate folder; your existing
Commander profile remains under %LOCALAPPDATA%\ED-Frame.

Project: https://github.com/CMDRForcer/ED-Frame
License: GNU General Public License v3.0

ED-Frame is an independent third-party project and is not affiliated with
Frontier Developments. Elite Dangerous is a trademark of Frontier Developments plc.
