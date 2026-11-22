Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

idePath = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "gublanide.py")
If Not fso.FileExists(idePath) Then
    MsgBox "could not find gublanide.py beside this launcher.", vbCritical, "gublan studio"
    WScript.Quit 1
End If

shell.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
command = "pythonw """ & idePath & """"
If WScript.Arguments.Count > 0 Then
    filePath = fso.GetAbsolutePathName(WScript.Arguments(0))
    command = command & " """ & filePath & """"
End If

On Error Resume Next
shell.Run command, 0, False
If Err.Number <> 0 Then
    errorMessage = Err.Description
    MsgBox "could not start gublan studio: " & errorMessage, vbCritical, "gublan studio"
    WScript.Quit 1
End If
