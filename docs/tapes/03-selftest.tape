Output docs/03-selftest.gif
Set FontSize 14
Set Width 1500
Set Height 420
Set Padding 16
Set TypingSpeed 30ms
Hide
Type "export VIRTUAL_ENV_DISABLE_PROMPT=1 PS1='$ ' && source .venv/bin/activate && clear"
Enter
Sleep 1s
Show
Type "python benchmarks/roundtrip_harness.py --selftest | sed -n '/== simulated/,$p'"
Enter
Sleep 9s
