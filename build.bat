@echo off
echo Building AI Context Aggregator executable...
pyinstaller --onefile --windowed --name AIContextAggregator main.py
echo Done. Executable is in dist\AIContextAggregator.exe
pause