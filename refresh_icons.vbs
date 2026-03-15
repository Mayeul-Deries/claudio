Set WshShell = CreateObject("WScript.Shell")

' Desktop Shortcut
strDesktop = WshShell.SpecialFolders("Desktop")
Set objShortcut = WshShell.CreateShortcut(strDesktop & "\Claudio.lnk")
objShortcut.TargetPath = "c:\Users\mayeu\Desktop\mes-projets\claudio\launcher.vbs"
objShortcut.WorkingDirectory = "c:\Users\mayeu\Desktop\mes-projets\claudio"
objShortcut.IconLocation = "c:\Users\mayeu\Desktop\mes-projets\claudio\icon.ico"
objShortcut.Save

' Startup Shortcut
strStartupPath = WshShell.SpecialFolders("Startup")
Set objShortcut2 = WshShell.CreateShortcut(strStartupPath & "\Claudio.lnk")
objShortcut2.TargetPath = "c:\Users\mayeu\Desktop\mes-projets\claudio\launcher.vbs"
objShortcut2.WorkingDirectory = "c:\Users\mayeu\Desktop\mes-projets\claudio"
objShortcut2.IconLocation = "c:\Users\mayeu\Desktop\mes-projets\claudio\icon.ico"
objShortcut2.Save
