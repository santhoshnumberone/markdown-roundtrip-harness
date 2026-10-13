Output docs/02-after.gif
Set FontSize 14
Set Width 1500
Set Height 700
Set Padding 16
Set TypingSpeed 30ms
Hide
Type "export VIRTUAL_ENV_DISABLE_PROMPT=1 PS1='$ ' && source .venv/bin/activate && clear"
Enter
Sleep 1s
Show
Type "python benchmarks/roundtrip_harness.py --failures | sed '/== ids/,$d' | cut -c1-165"
Enter
Sleep 7s
Type "python -m pytest -q 2>&1 | tail -3"
Enter
Sleep 6s
Type "python benchmarks/fuzz.py"
Enter
Sleep 6s
