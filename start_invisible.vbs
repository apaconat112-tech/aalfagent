Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "c:\aiagent\venv\Scripts\python.exe c:\aiagent\userbot_summarizer.py --listen", 0, False
