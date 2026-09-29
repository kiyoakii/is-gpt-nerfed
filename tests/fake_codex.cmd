@echo off
rem Windows cannot exec a shebang script, so the tests point codex_bin at this wrapper instead of fake_codex.py.
setlocal
set PYTHONUTF8=1
python "%~dp0fake_codex.py" %*
