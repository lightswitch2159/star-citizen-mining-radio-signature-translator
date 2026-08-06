# Building a Windows installer for SC RS Scanner

This produces a single `SCRSScannerSetup.exe` you can hand to other Windows
players. They just double-click it, click through the wizard, and get a
Start Menu entry — no Python, no Tesseract, no pip, nothing else to install.

You only need to do this once (or again each time you update the app).
Do this on a Windows machine.

## 1. Get Python (if you don't have it)

Download from [python.org](https://www.python.org/downloads/) (3.9+).
During install, check **"Add python.exe to PATH."**

## 2. Get a portable copy of Tesseract to bundle

1. Install Tesseract normally, once, using the
   [UB-Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki).
   Default install location: `C:\Program Files\Tesseract-OCR`.
2. Copy that **entire folder** into this packaging folder, so you end up
   with:
   ```
   packaging\windows\tesseract_bundle\tesseract.exe
   packaging\windows\tesseract_bundle\tessdata\eng.traineddata
   packaging\windows\tesseract_bundle\ (all the DLLs alongside tesseract.exe)
   ```
   (You can trim `tessdata\` down to just `eng.traineddata` and
   `osd.traineddata` to save space — the others are for languages this app
   never uses.)

This copy becomes part of the final installer, so end users never touch
Tesseract at all — the app finds and uses this bundled copy automatically.

## 3. Build the app folder

Double-click `build.bat` (or run it from a command prompt) in this folder.
It will:
- create a throwaway virtual environment
- install this project's dependencies + PyInstaller into it
- run PyInstaller using `sc_rs_scanner.spec`

Output: `packaging\windows\dist\SC RS Scanner\` — a folder containing
`SC RS Scanner.exe` and everything it needs. You can test it directly by
running that `.exe`.

If this step fails, the error message will say why (missing Python,
missing `tesseract_bundle`, a failed pip install, etc.) — fix that and
run `build.bat` again.

## 4. Turn it into a one-click installer

1. Install [Inno Setup](https://jrsoftware.org/isinfo.php) (free).
2. Open `installer.iss` in the Inno Setup Compiler and click **Compile**
   (or run `iscc installer.iss` from a command prompt with Inno Setup on
   PATH).

Output: `packaging\windows\installer_output\SCRSScannerSetup.exe`.

That's the file to send to other players. It installs without needing
admin rights, adds a Start Menu shortcut, offers a desktop shortcut, and
includes a proper uninstaller.

## Notes

- **Updating the app**: after changing any `.py` file in the project root,
  just re-run `build.bat` then re-compile `installer.iss`.
- **Antivirus / SmartScreen warnings**: PyInstaller executables are
  frequently (and incorrectly) flagged by some antivirus engines and
  Windows SmartScreen, since they're unsigned and bundle a Python runtime.
  This is a false positive, but it's common enough that your friends may
  see a "Windows protected your PC" prompt — they'll need to click "More
  info" → "Run anyway." Getting rid of this entirely requires a paid code
  signing certificate, which is out of scope here.
- **Icon**: the installer uses the default Windows app icon. If you want a
  custom one, save an `.ico` file as `packaging\windows\icon.ico` and
  uncomment the `icon=` line in `sc_rs_scanner.spec`.
