Output docs/01-baseline.gif
Set FontSize 14
Set Width 1500
Set Height 900
Set Padding 16
Set TypingSpeed 30ms
Hide
Type "export VIRTUAL_ENV_DISABLE_PROMPT=1 PS1='$ ' && source .venv/bin/activate && clear"
Enter
Sleep 1s
Show
Type "python benchmarks/roundtrip_harness.py --parser benchmarks/baseline/MarkdownParser_phase1.py --failures | sed '/== ids/,$d' | cut -c1-165"
Enter
Sleep 12s
