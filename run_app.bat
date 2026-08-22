@echo off
setlocal EnableExtensions
title Zalo Auction Auto Bidder - Quick Starter

cd /d "%~dp0"

rem Yeu cau quyen Administrator truoc khi cai Python/Tesseract.
net session >nul 2>&1
if errorlevel 1 (
    echo [INFO] Quyen Administrator la bat buoc de cai dat va gui tin nhan tu dong.
    echo Dang yeu cau quyen Administrator...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$q=[char]34; $script=$q+'%~f0'+$q; Start-Process -FilePath $env:ComSpec -ArgumentList @('/d','/c',$script) -WorkingDirectory '%~dp0' -Verb RunAs"
    if errorlevel 1 (
        echo [LOI] Khong the yeu cau quyen Administrator.
        pause
    )
    exit /b
)

echo [OK] Running with Administrator privileges.
echo.

call :find_python
if not defined PY_PATH (
    call :install_python
    if errorlevel 1 goto :failed
    call :find_python
)

if not defined PY_PATH (
    echo [LOI] Da cai Python nhung khong tim thay python.exe.
    goto :failed
)

echo [OK] Using Python: "%PY_PATH%"
"%PY_PATH%" --version
if errorlevel 1 (
    echo [LOI] Python khong khoi dong duoc.
    goto :failed
)

echo.
echo [1/2] Dang kiem tra va cai dat thu vien Python...
"%PY_PATH%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Dang khoi tao pip...
    "%PY_PATH%" -m ensurepip --upgrade
    if errorlevel 1 (
        echo [LOI] Khong the cai dat pip.
        goto :failed
    )
)

"%PY_PATH%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo [LOI] Khong the cai dat thu vien Python. Vui long kiem tra Internet.
    goto :failed
)
echo [OK] Thu vien Python da san sang.

echo.
echo [2/2] Dang kiem tra Tesseract OCR...
call :ensure_tesseract
if errorlevel 1 goto :failed

echo.
echo Dang khoi dong ung dung...
"%PY_PATH%" -m src.main
if errorlevel 1 (
    echo.
    echo [LOI] Chuong trinh gap loi khi chay hoac bi dong dot ngot.
    goto :failed
)
exit /b 0

:find_python
set "PY_PATH="

rem Uu tien ban Python 3.12 do script tu cai dat.
for %%p in (
    "%ProgramFiles%\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Python\pythoncore-3.12-64\python.exe"
    "%LocalAppData%\Python\pythoncore-3.14-64\python.exe"
) do (
    if not defined PY_PATH if exist "%%~p" set "PY_PATH=%%~p"
)

if defined PY_PATH exit /b 0

rem Tim cac ban Python khac da duoc cai theo kieu thong thuong.
for /d %%d in ("%LocalAppData%\Programs\Python\Python*") do (
    if not defined PY_PATH if exist "%%~fd\python.exe" set "PY_PATH=%%~fd\python.exe"
)
for /d %%d in ("%LocalAppData%\Python\pythoncore-*") do (
    if not defined PY_PATH if exist "%%~fd\python.exe" set "PY_PATH=%%~fd\python.exe"
)

if defined PY_PATH exit /b 0

rem Bo qua alias Microsoft Store trong WindowsApps.
for /f "delims=" %%p in ('where.exe python.exe 2^>nul') do (
    echo %%p | findstr.exe /i /c:"WindowsApps" >nul
    if errorlevel 1 if not defined PY_PATH set "PY_PATH=%%p"
)
exit /b 0

:install_python
set "PY_VERSION=3.12.10"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-amd64.exe"
set "PY_INSTALLER=%TEMP%\zalo-python-%PY_VERSION%-amd64.exe"

echo [INFO] May chua co Python.
echo [INFO] Dang tai Python %PY_VERSION% 64-bit tu python.org...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%'"
if errorlevel 1 (
    echo [LOI] Khong tai duoc Python. Vui long kiem tra ket noi Internet.
    exit /b 1
)
if not exist "%PY_INSTALLER%" (
    echo [LOI] File cai Python khong ton tai sau khi tai.
    exit /b 1
)

rem Chi chay file co chu ky so hop le cua Python Software Foundation.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$s=Get-AuthenticodeSignature -LiteralPath '%PY_INSTALLER%'; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Python Software Foundation'){ Write-Host '[LOI] Chu ky so cua bo cai Python khong hop le.'; exit 1 }"
if errorlevel 1 (
    del /q "%PY_INSTALLER%" >nul 2>&1
    exit /b 1
)

echo [INFO] Dang cai Python %PY_VERSION% va pip...
start "" /wait "%PY_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_launcher=1 Include_test=0
set "INSTALL_RESULT=%errorlevel%"
del /q "%PY_INSTALLER%" >nul 2>&1
if not "%INSTALL_RESULT%"=="0" (
    echo [LOI] Cai dat Python that bai. Ma loi: %INSTALL_RESULT%
    exit /b 1
)

echo [OK] Cai dat Python thanh cong.
exit /b 0

:ensure_tesseract
set "TESS_URL=https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe"
set "TESS_INSTALLER=%TEMP%\zalo-tesseract-setup.exe"

where.exe tesseract.exe >nul 2>&1
if not errorlevel 1 (
    echo [OK] Tesseract OCR da san sang.
    exit /b 0
)

if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" (
    echo [OK] Da tim thay Tesseract OCR tai "%ProgramFiles%\Tesseract-OCR".
    exit /b 0
)

if exist "tesseract_setup.exe" (
    echo [INFO] Dang cai Tesseract OCR tu file offline...
    start "" /wait "tesseract_setup.exe" /S
    if errorlevel 1 (
        echo [LOI] Cai dat Tesseract OCR that bai.
        exit /b 1
    )
) else (
    echo [INFO] Dang tai Tesseract OCR...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri '%TESS_URL%' -OutFile '%TESS_INSTALLER%'"
    if errorlevel 1 (
        echo [LOI] Khong tai duoc Tesseract OCR.
        exit /b 1
    )
    start "" /wait "%TESS_INSTALLER%" /S
    if errorlevel 1 (
        del /q "%TESS_INSTALLER%" >nul 2>&1
        echo [LOI] Cai dat Tesseract OCR that bai.
        exit /b 1
    )
    del /q "%TESS_INSTALLER%" >nul 2>&1
)

if not exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" (
    where.exe tesseract.exe >nul 2>&1
    if errorlevel 1 (
        echo [LOI] Da cai nhung khong tim thay Tesseract OCR.
        exit /b 1
    )
)
echo [OK] Cai dat Tesseract OCR thanh cong.
exit /b 0

:failed
echo.
echo [LOI] Khong the khoi dong ung dung. Xem thong bao ben tren de biet chi tiet.
pause
exit /b 1
