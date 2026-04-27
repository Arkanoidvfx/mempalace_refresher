Option Explicit

Dim shell
Dim pythonwExe
Dim command

If WScript.Arguments.Count < 1 Then
    WScript.Quit 1
End If

pythonwExe = WScript.Arguments(0)
command = """" & pythonwExe & """ -m mempalace_watcher desktop"

Set shell = CreateObject("WScript.Shell")
shell.Run command, 0, False
