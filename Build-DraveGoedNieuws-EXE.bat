@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==== DraveGoedNieuws - EXE bouwen ====
py -3.12 -c "import PyQt6.QtMultimedia, neuvoice, onnxruntime, ctranslate2, sentencepiece, certifi" || (echo FOUT: py -3.12 mist een pakket (PyQt6, neuvoice, onnxruntime, ctranslate2, sentencepiece, certifi) & pause & exit /b 1)
py -3.12 -m PyInstaller --noconfirm --clean --onedir --windowed --name DraveGoedNieuws --icon assets\icon.ico ^
  --add-data "assets;assets" --hidden-import bronnen --hidden-import leon --hidden-import vertaal ^
  --collect-all neuvoice --collect-all onnxruntime --collect-all ctranslate2 --collect-all sentencepiece --collect-data certifi ^
  --exclude-module torch --exclude-module torchvision --exclude-module torchaudio --exclude-module tensorflow ^
  --exclude-module transformers --exclude-module matplotlib --exclude-module pandas --exclude-module scipy ^
  --exclude-module stanza --exclude-module argostranslate --exclude-module PyQt6.QtWebEngineCore --exclude-module tkinter goednieuws.py
if errorlevel 1 (echo FOUT: PyInstaller is mislukt & pause & exit /b 1)
if not exist "dist\DraveGoedNieuws\DraveGoedNieuws.exe" (echo FOUT: geen exe gemaakt & pause & exit /b 1)
xcopy /E /I /Y assets "dist\DraveGoedNieuws\assets" >nul
echo.
echo KLAAR: dist\DraveGoedNieuws\DraveGoedNieuws.exe
pause
