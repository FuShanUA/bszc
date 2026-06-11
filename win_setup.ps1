# Set UTF-8 encoding to prevent mojibake on Chinese Windows
$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
if ([Console]::InputEncoding.CodePage -ne 65001) {
    try {
        [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    } catch {}
}

function Clear-Console {
    Clear-Host
    Write-Host "==============================================" -ForegroundColor Green
    Write-Host "      投标自查卫士 BidShield Windows 助手      " -ForegroundColor Green
    Write-Host "==============================================" -ForegroundColor Green
}

function Pause-Console {
    try {
        [void][Console]::ReadKey($true)
    } catch {
        Start-Sleep -Milliseconds 500
    }
}

function Stop-BidShieldServer {
    try {
        $gps = Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue
        if (-not $gps) {
            $gps = Get-WmiObject Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue
        }
        $killed = $false
        foreach ($p in $gps) {
            if ($p.CommandLine -match "server.py") {
                Write-Host "🛑 正在停止已运行的 投标自查卫士 服务端 (PID: $($p.ProcessId))... " -ForegroundColor Yellow
                Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
                $killed = $true
            }
        }
        if ($killed) {
            Start-Sleep -Seconds 1
        }
    } catch {}
}

Clear-Console
Write-Host "🔍 正在检查运行环境，请稍候... " -ForegroundColor Cyan

# 1. Check Python Environment
$PythonCmd = "python"
$PipCmd = "pip"
$hasPython = $false
$isPortable = $false

try {
    $ver = & python --version 2>&1
    if ($ver -match "Python 3") { $hasPython = $true }
} catch {}

if (-not $hasPython) {
    try {
        $ver = & python3 --version 2>&1
        if ($ver -match "Python 3") {
            $hasPython = $true
            $PythonCmd = "python3"
            $PipCmd = "pip3"
        }
    } catch {}
}

$venvPath = Join-Path $PSScriptRoot ".venv"
$embedPath = Join-Path $PSScriptRoot "python_embed"

# A. If Python is installed, setup venv
if ($hasPython) {
    Write-Host "✔ 检测到系统已安装 Python... " -ForegroundColor Green
    if (-not (Test-Path $venvPath) -and -not (Test-Path $embedPath)) {
        Write-Host "🛠 正在尝试创建 Python 虚拟环境 (.venv)... " -ForegroundColor Cyan
        & $PythonCmd -m venv $venvPath 2>&1 | Out-Null
    }
    if (Test-Path $venvPath) {
        $PythonCmd = Join-Path $venvPath "Scripts\python.exe"
        $PipCmd = Join-Path $venvPath "Scripts\pip.exe"
    }
}

# B. If Python is not installed, but portable Python already exists
if (-not $hasPython -and (Test-Path $embedPath)) {
    Write-Host "✔ 检测到本地已存在便携式 Python... " -ForegroundColor Green
    $PythonCmd = Join-Path $embedPath "python.exe"
    $PipCmd = Join-Path $embedPath "Scripts\pip.exe"
    $isPortable = $true
}

# C. If Python is not installed and no portable Python exists, download it
if (-not $hasPython -and -not (Test-Path $embedPath)) {
    Write-Host "❌ 未检测到系统 Python 3 环境... " -ForegroundColor Yellow
    Write-Host "💡 将自动下载便携式 Python 3.10 (约 10MB，无需管理员权限，纯绿色)... " -ForegroundColor Cyan
    
    $zipUrl = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip"
    $destZip = Join-Path $PSScriptRoot "python-3.10.11-embed-amd64.zip"
    
    try {
        Write-Host "📥 正在从 python.org 下载便携式 Python (这可能需要一些时间)... " -ForegroundColor Cyan
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $zipUrl -OutFile $destZip -UserAgent "Mozilla/5.0"
        
        Write-Host "📦 正在解压 Python 运行环境... " -ForegroundColor Cyan
        Expand-Archive -Path $destZip -DestinationPath $embedPath -Force
        Remove-Item $destZip
        
        $pthFile = Join-Path $embedPath "python310._pth"
        if (Test-Path $pthFile) {
            $content = Get-Content $pthFile -Raw
            $newContent = $content -replace '#import site', 'import site'
            Set-Content $pthFile $newContent
        }
        
        $pipUrl = "https://bootstrap.pypa.io/get-pip.py"
        $pipScript = Join-Path $embedPath "get-pip.py"
        Write-Host "📥 正在下载 pip 包管理器... " -ForegroundColor Cyan
        Invoke-WebRequest -Uri $pipUrl -OutFile $pipScript -UserAgent "Mozilla/5.0"
        
        Write-Host "🛠 正在为便携版 Python 安装 pip... " -ForegroundColor Cyan
        & "$embedPath\python.exe" $pipScript --no-warn-script-location
        Remove-Item $pipScript
        
        $PythonCmd = Join-Path $embedPath "python.exe"
        $PipCmd = Join-Path $embedPath "Scripts\pip.exe"
        $isPortable = $true
        Write-Host "✔ 便携式 Python 环境配置成功！ " -ForegroundColor Green
    } catch {
        Write-Host "❌ 自动配置 Python 环境失败！请检查网络连接。 " -ForegroundColor Red
        Write-Host "错误详情: $_ " -ForegroundColor Red
        Write-Host "按下任意键退出... " -ForegroundColor Yellow
        Pause-Console
        exit 1
    }
}

# 2. Check and Install Requirements
$reqFile = Join-Path $PSScriptRoot "requirements.txt"
$checkPackages = @("pypdf", "pdfplumber", "PIL")
$needInstall = $false

foreach ($pkg in $checkPackages) {
    $pkgCheck = & $PythonCmd -c "import $pkg" 2>&1
    if ($pkgCheck -match "ModuleNotFoundError" -or $pkgCheck -match "No module named") {
        $needInstall = $true
        break
    }
}

if ($needInstall) {
    Write-Host "🛠 正在自动安装项目所需的依赖包 (使用国内清华源，以加快速度)... " -ForegroundColor Cyan
    & $PipCmd install -r $reqFile pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple --no-warn-script-location
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠️ 使用清华源失败，正在尝试使用默认源安装... " -ForegroundColor Yellow
        & $PipCmd install -r $reqFile pyinstaller --no-warn-script-location
    }
}

# Menu loop
while ($true) {
    Clear-Console
    Write-Host "  [1] 启动 投标自查卫士 (本地运行) " -ForegroundColor White
    Write-Host "  [2] 打包 投标自查卫士 (生成独立的 .exe 文件) " -ForegroundColor White
    Write-Host "  [3] 重新安装/更新所有依赖包 " -ForegroundColor White
    Write-Host "  [4] 清理临时打包文件 (build/dist/spec) " -ForegroundColor White
    Write-Host "  [5] 退出 " -ForegroundColor White
    Write-Host "==============================================" -ForegroundColor Green
    
    $choice = Read-Host "请选择操作序号 [1-5] "
    
    switch ($choice) {
        "1" {
            Clear-Console
            Stop-BidShieldServer
            Write-Host "🚀 正在后台启动 投标自查卫士 服务端，并自动打开浏览器... " -ForegroundColor Green
            
            # Start process hidden (which automatically opens the browser via webbrowser.open)
            Start-Process -FilePath $PythonCmd -ArgumentList "server.py" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
            Start-Sleep -Seconds 2
            
            Write-Host "`n✔ 启动成功！ " -ForegroundColor Green
            Write-Host "💡 提示：服务端已在后台静默运行。若要关闭，只需在此菜单选择 [5] 退出，本助手将自动清理后台进程。 " -ForegroundColor Yellow
            Write-Host "`n按任意键返回主菜单... " -ForegroundColor Yellow
            Pause-Console
        }
        "2" {
            Clear-Console
            Write-Host "🛠 开始进行 Windows 本地打包为 exe 独立可执行程序... " -ForegroundColor Cyan
            Write-Host "📦 这会将 Python 环境和程序所有依赖打包进单个 EXE 文件，以便在没有 Python 的电脑上双击即用... " -ForegroundColor Cyan
            Write-Host "⏳ 正在分析依赖并打包，请耐心等待... " -ForegroundColor Cyan
            
            # Execute PyInstaller via python module runner for maximum stability
            $argsList = @(
                "-m", "PyInstaller",
                "--name=投标自查卫士",
                "--add-data=index.html;.",
                "--add-data=logo.png;.",
                "--add-data=hualu_result.txt;.",
                "--add-data=zhizhenyun_result.txt;.",
                "--add-data=zhuowei_result.txt;.",
                "--onefile",
                "server.py"
            )
            
            & $PythonCmd $argsList
            
            if ($LASTEXITCODE -eq 0 -and (Test-Path (Join-Path $PSScriptRoot "dist\投标自查卫士.exe"))) {
                Write-Host "`n✔ 打包成功！独立可执行文件已生成在： " -ForegroundColor Green
                Write-Host "👉 $(Join-Path $PSScriptRoot 'dist\投标自查卫士.exe') " -ForegroundColor Green
                Write-Host "`n✨ 您可以将该文件发送给其他 Windows 用户，双击即可无依赖运行！ " -ForegroundColor Green
            } else {
                Write-Host "`n❌ 打包失败，请检查上方 PyInstaller 报错信息。 " -ForegroundColor Red
            }
            Write-Host "`n按任意键返回主菜单... " -ForegroundColor Yellow
            Pause-Console
        }
        "3" {
            Clear-Console
            Write-Host "🔄 正在重新安装/更新所有依赖包... " -ForegroundColor Cyan
            & $PipCmd install --upgrade -r $reqFile pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple --no-warn-script-location
            Write-Host "`n✔ 依赖更新完成！ " -ForegroundColor Green
            Write-Host "`n按任意键返回主菜单... " -ForegroundColor Yellow
            Pause-Console
        }
        "4" {
            Clear-Console
            Write-Host "🧹 正在清理 PyInstaller 生成的临时打包目录... " -ForegroundColor Cyan
            
            $buildDir = Join-Path $PSScriptRoot "build"
            $distDir = Join-Path $PSScriptRoot "dist"
            $specFile = Join-Path $PSScriptRoot "投标自查卫士.spec"
            
            if (Test-Path $buildDir) {
                Remove-Item -Recurse -Force $buildDir
                Write-Host "✔ 已清理 build/ 目录 " -ForegroundColor Green
            }
            if (Test-Path $distDir) {
                Remove-Item -Recurse -Force $distDir
                Write-Host "✔ 已清理 dist/ 目录 " -ForegroundColor Green
            }
            if (Test-Path $specFile) {
                Remove-Item -Force $specFile
                Write-Host "✔ 已清理 投标自查卫士.spec 文件 " -ForegroundColor Green
            }
            
            Write-Host "`n✔ 临时文件清理完毕！ " -ForegroundColor Green
            Write-Host "`n按任意键返回主菜单... " -ForegroundColor Yellow
            Pause-Console
        }
        "5" {
            Write-Host "👋 正在退出... " -ForegroundColor Cyan
            Stop-BidShieldServer
            exit 0
        }
    }
}



