# NOKIATTSNVDA

Experimental build infrastructure for a lower-latency Nokia TTS NVDA add-on on
Windows on ARM.

The GitHub Actions workflow builds the ARM guest portion of Unicorn 2.1.4 as a
native Windows ARM64 DLL. It also attempts an ARM64EC build for compatibility
with x64/ARM64EC host processes. Both builds are intentionally limited to the
ARM guest backend required by the Nokia speech engine.
