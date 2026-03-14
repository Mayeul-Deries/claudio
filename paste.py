import time
import pyperclip
import pyautogui
import win32gui

# List of typical class names for editable controls in Windows.
# Note: browsers (Chrome/Edge/Firefox) often don't expose their internal editable elements 
# as standard Windows controls, so detecting them perfectly is hard. We will assume 
# if a browser is active, the user might be in a text field.
EDITABLE_CLASSES = [
    "Edit", 
    "RichEdit20W", 
    "RichEdit50W", 
    "RICHEDIT50W",
    "Notepad",
    "Chrome_WidgetWin_1", # Chrome/Edge
    "MozillaWindowClass", # Firefox
    "Notion",             # Notion electron app
    "ApplicationFrameWindow", # UWP apps
]

def is_editable_field_focused() -> bool:
    """
    Attempt to heuristically determine if an editable field is currently focused.
    """
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return False
            
        classname = win32gui.GetClassName(hwnd)
        
        # Check against known editable classes or heavy text-input apps
        if any(cls in classname for cls in EDITABLE_CLASSES):
            return True
            
        return False
    except Exception as e:
        print(f"Error checking window focus: {e}")
        return False

def copy_and_paste(text: str):
    """
    1. Copies text to clipboard.
    2. Checks if we should attempt to auto-paste.
    3. Triggers Ctrl+V if appropriate.
    """
    if not text:
        return
        
    print(f"Copying to clipboard: {text}")
    pyperclip.copy(text)
    
    # Wait a tiny bit for clipboard to settle
    time.sleep(0.05)
    
    if is_editable_field_focused():
        print("Editable field detected, simulating Ctrl+V...")
        pyautogui.hotkey('ctrl', 'v')
    else:
        print("No obvious editable field detected, just copying to clipboard.")
