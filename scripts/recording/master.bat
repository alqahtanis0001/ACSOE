@echo off
REM ===========================================================================
REM  ACSOE - start recording on this machine (the master).
REM
REM  WHAT THIS DOES
REM  It starts the supervisor, and the supervisor starts the recorder and keeps
REM  restarting it for as long as this window is open. The recorder connects to
REM  Kraken and writes market data into data\raw and data\summaries.
REM
REM  It never runs the recorder directly. If the recorder crashes - and it has,
REM  twice - the supervisor notices within a second and starts it again. Running
REM  record.py by hand gives you no such thing.
REM
REM  HOW TO MAKE IT START ON ITS OWN
REM  Press Win+R, type   shell:startup   and press Enter. Drop a shortcut to
REM  THIS FILE into the folder that opens. Recording then begins when you log in,
REM  with nothing to type.
REM
REM  IS IT SAFE TO CLOSE THIS WINDOW?
REM  Yes. Closing it stops the recorder, and stopping the recorder damages
REM  nothing: the archive is append-only and every line is flushed as it is
REM  written, so the worst a hard close can do is leave the final line of a file
REM  half-written. The import tooling already recognises that and reads the file
REM  anyway - it is never repaired, because a recording is immutable.
REM
REM  Safe does not mean free. The market does not come back, and order book and
REM  spread cannot be recovered afterwards from anywhere: Kraken's free archives
REM  carry OHLCV and no bid, ask, spread or depth. Every minute this window is
REM  closed is a minute missing from the archive for good. Close it when you need
REM  to; reopen it as soon as you can.
REM
REM  IS IT SAFE TO OPEN IT TWICE?
REM  Yes, and nothing bad happens. The second one will not record. The recorder
REM  takes an exclusive lock on the archive directory, so the second copy finds it
REM  held, says so, and waits quietly - checking every thirty seconds - until the
REM  first one stops. Two recorders writing one archive would interleave their
REM  lines and corrupt it silently; the lock is what makes that impossible rather
REM  than merely unlikely.
REM
REM  WHAT YOU WILL SEE
REM  Six lines, refreshing in place. That is the whole interface:
REM
REM      RECORDING - <this machine>
REM      started    <when this window was opened>
REM      uptime     <how long it has been recording>
REM      today      <megabytes written today>
REM      last write <how long ago the last line landed>
REM      restarts   <how many times the recorder has been restarted>
REM
REM  "last write" is the number to look at. On a healthy recorder it reads 0s.
REM
REM  The recorder's own output is not shown here - it would overwrite the block
REM  every second. It goes to logs\supervisor__<source>__<date>.log, together
REM  with every launch, every exit code and every restart.
REM
REM  Everything else - which machines are recording, what the archive covers,
REM  where the holes are, importing from another machine - is the manager web
REM  app, not this window. Start it with:
REM      python scripts\recording\manager\serve.py
REM ===========================================================================

REM Render UTF-8 correctly. The status block contains an em dash, and a console
REM left on the default code page shows it as mojibake - which looks like a broken
REM program at the exact moment you are checking whether recording started.
chcp 65001 > nul

REM Run from the repository root whatever folder the shortcut was launched from.
REM %~dp0 is THIS FILE's own directory, so a shortcut in shell:startup - which
REM launches with a working directory of C:\Windows\system32 - still finds the
REM repository. Relying on the working directory is how a startup shortcut ends up
REM recording somewhere under C:\Windows\system32, or not starting at all.
cd /d "%~dp0..\.."

REM Prefer the project's virtual environment; fall back to whatever `python` is.
if exist ".venv\Scripts\python.exe" (set "ACSOE_PY=.venv\Scripts\python.exe") else (set "ACSOE_PY=python")

title ACSOE recording - master

"%ACSOE_PY%" scripts\recording\supervise.py --config config\recorder.yaml

REM If the supervisor itself exits, hold the window open so the reason is
REM readable instead of vanishing with the console.
echo.
echo The supervisor has stopped. Nothing is being recorded.
pause
