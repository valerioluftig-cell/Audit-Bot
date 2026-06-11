@echo off
echo Installing / upgrading PyInstaller...
pip install --upgrade pyinstaller

echo.
echo Building AuditPipeline.exe...
pyinstaller audit_pipeline.spec --clean --noconfirm

echo.
if exist "dist\AuditPipeline\AuditPipeline.exe" (
    echo BUILD SUCCESSFUL
    echo.
    echo Your app is at:  dist\AuditPipeline\AuditPipeline.exe
    echo Copy the entire dist\AuditPipeline\ folder to any Windows PC and double-click the .exe
) else (
    echo BUILD FAILED - check the output above for errors
)
pause
