@echo off
setlocal
cd /d "%~dp0"

rem build gublan studio into dist\GublanStudio.exe (needs: py -m pip install pyinstaller pygame-ce pyopengl)
py -m PyInstaller --noconfirm --distpath "dist" --workpath "build\GublanStudio" GublanStudio.spec
if errorlevel 1 goto build_failed

echo.
echo build succeeded: dist\GublanStudio.exe
goto done

:build_failed
echo.
echo build failed. check the output above for details.

:done
pause
endlocal
