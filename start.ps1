$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "AI 智慧前台数字人系统"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AvatarDir = Join-Path $RootDir "avatar"
$AvatarPort = 3456
$LogDir = Join-Path $RootDir "cache\logs"
$NodeProcess = $null
$PythonProcess = $null
$Script:Stopping = $false

function Write-Banner {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  AI 智慧前台数字人系统 - 一键启动" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Section {
    param(
        [int]$Index,
        [int]$Total,
        [string]$Title
    )
    [Console]::WriteLine("")
    Write-Host ("[{0}/{1}] {2}" -f $Index, $Total, $Title) -ForegroundColor Yellow
}

function Write-Status {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message = "",
        [ConsoleColor]$Color = "Gray"
    )
    [Console]::Write("`r")
    Write-Host ("       {0,-12} [{1,-5}] {2}" -f $Name, $Status, $Message) -ForegroundColor $Color
}

function Stop-System {
    if ($Script:Stopping) {
        return
    }
    $Script:Stopping = $true

    Write-Host ""
    Write-Status "系统" "STOP" "正在停止服务..." "Yellow"
    if ($NodeProcess -and -not $NodeProcess.HasExited) {
        Stop-ProcessQuietly -ProcessId $NodeProcess.Id
    }
    if ($PythonProcess -and -not $PythonProcess.HasExited) {
        Stop-ProcessQuietly -ProcessId $PythonProcess.Id
    }
    Write-Status "系统" "OK" "已停止" "Green"
}

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Status ".env" "SKIP" "未找到，使用系统环境变量和默认配置" "DarkGray"
        return
    }

    foreach ($RawLine in Get-Content -LiteralPath $Path) {
        $Line = $RawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($Line) -or $Line.StartsWith("#")) {
            continue
        }
        if ($Line -notmatch "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$") {
            continue
        }

        $Name = $Matches[1]
        $Value = $Matches[2].Trim()
        if (
            ($Value.StartsWith('"') -and $Value.EndsWith('"')) -or
            ($Value.StartsWith("'") -and $Value.EndsWith("'"))
        ) {
            $Value = $Value.Substring(1, $Value.Length - 2)
        }

        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }

    Write-Status ".env" "OK" "已加载 $Path" "Green"
}

function Read-YesNo {
    param(
        [string]$Prompt,
        [bool]$DefaultYes = $true
    )

    $Suffix = if ($DefaultYes) { "Y/n" } else { "y/N" }
    while ($true) {
        $Answer = Read-Host "$Prompt ($Suffix)"
        if ([string]::IsNullOrWhiteSpace($Answer)) {
            return $DefaultYes
        }

        switch ($Answer.Trim().ToLowerInvariant()) {
            "y" { return $true }
            "yes" { return $true }
            "是" { return $true }
            "n" { return $false }
            "no" { return $false }
            "否" { return $false }
            default { Write-Status "输入" "WARN" "请输入 y 或 n" "DarkYellow" }
        }
    }
}

function Test-WslAvailable {
    try {
        $Output = & wsl.exe -l -q 2>$null
        return -not [string]::IsNullOrWhiteSpace(($Output | Out-String).Trim())
    }
    catch {
        return $false
    }
}

function Invoke-WslDatabaseStartup {
    $Script = @'
set +e

sudo service mysql start >/dev/null 2>&1
sleep 1
if sudo service mysql status >/dev/null 2>&1; then
    echo "MYSQL=OK"
else
    echo "MYSQL=FAIL"
fi

sudo service redis-server start >/dev/null 2>&1
sleep 1
if sudo service redis-server status >/dev/null 2>&1 || redis-cli -h 127.0.0.1 -p 6379 ping >/dev/null 2>&1; then
    echo "REDIS=OK"
else
    echo "REDIS=FAIL"
fi

sudo service postgresql start >/dev/null 2>&1
sleep 1
if sudo service postgresql status >/dev/null 2>&1; then
    echo "PGSQL=OK"
else
    echo "PGSQL=FAIL"
fi
'@
    return & wsl.exe -e bash -lc $Script 2>&1
}

function Initialize-WslSudo {
    Write-Status "sudo" "WAIT" "请在下方输入 WSL sudo 密码并回车" "Yellow"
    & wsl.exe -e sudo -v
    if ($LASTEXITCODE -ne 0) {
        throw "sudo 验证失败，无法启动 WSL 服务。"
    }
    Write-Status "sudo" "OK" "验证完成" "Green"
}

function Stop-ProcessQuietly {
    param([int]$ProcessId)

    if ($ProcessId -gt 0) {
        Stop-Process -Id $ProcessId -ErrorAction SilentlyContinue
    }
}

function Stop-PortOwner {
    param([int]$Port)

    $ProcessIds = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -and $_.OwningProcess -gt 0 } |
        Select-Object -ExpandProperty OwningProcess -Unique

    foreach ($ProcessId in $ProcessIds) {
        Write-Status "端口$Port" "STOP" "结束占用进程 PID=$ProcessId" "DarkYellow"
        Stop-ProcessQuietly -ProcessId $ProcessId
    }

    if ($ProcessIds) {
        Start-Sleep -Seconds 1
    }
}

function Wait-HttpJson {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds,
        [scriptblock]$Ready
    )

    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        try {
            $Response = Invoke-RestMethod -Uri $Uri -TimeoutSec 2
            if (& $Ready $Response) {
                return $Response
            }
        }
        catch {
        }
        Start-Sleep -Seconds 2
    }

    return $null
}

function Initialize-Logs {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    return @{
        NodeOut = Join-Path $LogDir "avatar-node.log"
        NodeErr = Join-Path $LogDir "avatar-node.err.log"
        PyOut = Join-Path $LogDir "app-python.log"
        PyErr = Join-Path $LogDir "app-python.err.log"
    }
}

function Initialize-Databases {
    Write-Section 1 5 "数据库服务确认"

    $AlreadyRunning = Read-YesNo "MySQL / Redis / PostgreSQL 服务是否已经开启？"
    $State = @{
        HasWsl = Test-WslAvailable
        MySQL = $false
        Redis = $false
        PostgreSQL = $false
    }

    if ($AlreadyRunning) {
        Write-Status "数据库" "SKIP" "已确认开启，跳过 WSL 启动" "Green"
        $State.MySQL = $true
        $State.Redis = $true
        $State.PostgreSQL = $true
        return $State
    }

    if (-not $State.HasWsl) {
        Write-Status "WSL" "FAIL" "未检测到可用 WSL" "Red"
        throw "请手动启动 MySQL / Redis / PostgreSQL 后重新运行脚本。"
    }

    Initialize-WslSudo
    Write-Status "WSL" "RUN" "正在启动数据库服务（可能需要输入 sudo 密码）" "Gray"
    $Output = Invoke-WslDatabaseStartup

    $State.MySQL = ($Output -match "MYSQL=OK")
    $State.Redis = ($Output -match "REDIS=OK")
    $State.PostgreSQL = ($Output -match "PGSQL=OK")

    if ($State.MySQL) {
        Write-Status "MySQL" "OK" "已运行 (WSL)" "Green"
    }
    else {
        Write-Status "MySQL" "FAIL" "启动失败，请检查 WSL 中 MySQL" "Red"
    }

    if ($State.Redis) {
        Write-Status "Redis" "OK" "redis-server 已运行 (WSL)" "Green"
    }
    else {
        Write-Status "Redis" "FAIL" "redis-server 启动失败，请检查 WSL Redis" "Red"
    }

    if ($State.PostgreSQL) {
        Write-Status "PostgreSQL" "OK" "已运行 (WSL)" "Green"
    }
    else {
        Write-Status "PostgreSQL" "FAIL" "启动失败，请检查 WSL 中 PostgreSQL" "Red"
    }

    if (-not $State.MySQL) {
        throw "MySQL 不可用，考勤模块无法初始化。"
    }

    return $State
}

function Clear-TestDataIfRequested {
    param([hashtable]$DatabaseState)

    Write-Section 2 5 "测试数据清理"
    Write-Status "配置" "INFO" "CLEAR_TEST_DATA=$($env:CLEAR_TEST_DATA)" "DarkGray"

    if ($env:CLEAR_TEST_DATA -ne "1") {
        Write-Status "测试数据" "SKIP" "如需演示清库，请在 .env 设置 CLEAR_TEST_DATA=1" "Green"
        return
    }

    Write-Status "测试数据" "RUN" "正在清除 Redis / MySQL 测试数据" "Yellow"

    if ($DatabaseState.Redis) {
        try {
            $RedisCleanScript = @'
for pattern in 'checkin:*' 'checkin_cooldown:*' 'checkout:*'; do
    redis-cli --scan --pattern "$pattern" | xargs -r redis-cli DEL >/dev/null
done
'@
            & wsl.exe -e bash -lc $RedisCleanScript 2>$null
            Write-Status "Redis" "OK" "签到缓存已清除" "Green"
        }
        catch {
            Write-Status "Redis" "WARN" "清除失败，不影响启动" "DarkYellow"
        }
    }
    else {
        Write-Status "Redis" "SKIP" "不可用，跳过清除" "DarkYellow"
    }

    if ($DatabaseState.MySQL) {
        try {
            $MySqlCleanSql = @'
CREATE DATABASE IF NOT EXISTS attendance;
USE attendance;
CREATE TABLE IF NOT EXISTS attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    date VARCHAR(10) NOT NULL,
    check_in VARCHAR(8) NOT NULL,
    check_out VARCHAR(8),
    duration INT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
TRUNCATE TABLE attendance;
'@
            if ($DatabaseState.HasWsl) {
                $BashCmd = "MYSQL_PWD='123456' mysql -u root <<'EOSQL'`n$MySqlCleanSql`nEOSQL"
                $MySqlOutput = & wsl.exe -e bash -lc $BashCmd 2>&1
            }
            else {
                $env:MYSQL_PWD = "123456"
                $MySqlOutput = & mysql -u root -e $MySqlCleanSql 2>&1
                Remove-Item Env:\MYSQL_PWD -ErrorAction SilentlyContinue
            }

            if ($LASTEXITCODE -ne 0) {
                $Message = ($MySqlOutput | Out-String).Trim()
                if (-not $Message) {
                    $Message = "mysql exit code $LASTEXITCODE"
                }
                throw $Message
            }
            Write-Status "MySQL" "OK" "签到记录已清除" "Green"
        }
        catch {
            Write-Status "MySQL" "WARN" "清除失败，不影响启动: $($_.Exception.Message)" "DarkYellow"
        }
    }
}

function Start-AvatarServer {
    param([hashtable]$Logs)

    Write-Section 3 5 "启动数字人前端"
    Stop-PortOwner -Port $AvatarPort

    $Process = Start-Process `
        -FilePath "node" `
        -ArgumentList @("server.js") `
        -WorkingDirectory $AvatarDir `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $Logs.NodeOut `
        -RedirectStandardError $Logs.NodeErr

    Start-Sleep -Seconds 2
    if ($Process.HasExited) {
        throw "Node 启动失败，请检查 $AvatarDir\server.js 和日志 $($Logs.NodeErr)"
    }

    Write-Status "Node" "OK" "数字人服务已启动 PID=$($Process.Id)" "Green"
    return $Process
}

function Wait-TtsPrewarmIfEnabled {
    param([System.Diagnostics.Process]$Process)

    if ($env:ENABLE_TTS_PREWARM -ne "1") {
        Write-Status "TTS预热" "SKIP" "语音将按事件异步生成并缓存" "Green"
        return
    }

    Write-Status "TTS预热" "RUN" "正在生成旧版全量语音缓存" "Yellow"
    $Deadline = (Get-Date).AddMinutes(5)
    while ((Get-Date) -lt $Deadline) {
        try {
            $Status = Invoke-RestMethod -Uri "http://localhost:$AvatarPort/tts-prewarm-status" -TimeoutSec 3
            $Done = [int]$Status.generated + [int]$Status.skipped
            Write-Status "TTS缓存" "INFO" ("{0}/{1}" -f $Done, $Status.total) "DarkGray"

            if ($Status.complete) {
                if ($Status.error) {
                    throw "语音预生成失败: $($Status.error)"
                }
                Write-Status "TTS预热" "OK" "语音缓存已就绪" "Green"
                return
            }
        }
        catch {
            Write-Status "TTS预热" "WAIT" "等待数字人服务响应" "DarkGray"
        }
        Start-Sleep -Seconds 3
    }

    Stop-ProcessQuietly -ProcessId $Process.Id
    throw "语音预生成未完成。"
}

function Open-AvatarBrowserAndWait {
    param([System.Diagnostics.Process]$Process)

    Write-Section 4 5 "打开数字人页面"

    $Url = "http://localhost:$AvatarPort/?display&v=$([DateTimeOffset]::Now.ToUnixTimeSeconds())"
    Start-Process `
        -FilePath "msedge" `
        -ArgumentList @(
            "--new-window",
            "--kiosk",
            $Url,
            "--edge-kiosk-type=fullscreen",
            "--autoplay-policy=no-user-gesture-required"
        ) | Out-Null

    Write-Status "浏览器" "OK" $Url "Green"
    $Ready = Wait-HttpJson `
        -Uri "http://localhost:$AvatarPort/avatar-ready" `
        -TimeoutSeconds 120 `
        -Ready { param($Response) return [bool]$Response.ready }

    if ($null -eq $Ready) {
        Stop-ProcessQuietly -ProcessId $Process.Id
        throw "数字人模型未加载完成，系统不会打开摄像头。"
    }

    Write-Status "Live2D" "OK" "模型已加载: $($Ready.model)" "Green"
    return $Url
}

function Start-FaceRecognition {
    param([hashtable]$Logs)

    Write-Section 5 5 "启动人脸识别引擎"

    $OldProcesses = Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -match '(^| )app\.py( |$)' }

    foreach ($OldProcess in $OldProcesses) {
        Write-Status "Python" "STOP" "清理旧进程 PID=$($OldProcess.ProcessId)" "DarkYellow"
        Stop-ProcessQuietly -ProcessId $OldProcess.ProcessId
    }

    if ($OldProcesses) {
        Start-Sleep -Seconds 1
    }

    $PythonExe = Join-Path $RootDir ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        $PythonExe = "python"
    }

    $Process = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList @("app.py") `
        -WorkingDirectory $RootDir `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $Logs.PyOut `
        -RedirectStandardError $Logs.PyErr

    Start-Sleep -Seconds 4
    if ($Process.HasExited) {
        throw "Python 启动失败，请检查 $RootDir\app.py 和日志 $($Logs.PyErr)"
    }

    Write-Status "Python" "OK" "人脸识别引擎已启动 PID=$($Process.Id)" "Green"
    return $Process
}

function Show-RunningInfo {
    param([string]$Url)

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  系统运行中!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  数字人页面: $Url" -ForegroundColor White
    Write-Host "  运行日志:   $LogDir" -ForegroundColor DarkGray
    Write-Host "  退出全屏:   按 F11" -ForegroundColor DarkGray
    Write-Host "  关闭浏览器: Alt+F4" -ForegroundColor DarkGray
    Write-Host "  停止系统:   关闭此窗口" -ForegroundColor DarkGray
    Write-Host ""
}

function Watch-Processes {
    param(
        [System.Diagnostics.Process]$Node,
        [System.Diagnostics.Process]$Python
    )

    while ($true) {
        if ($Node.HasExited) {
            Write-Status "Node" "EXIT" "数字人前端已退出" "Red"
            break
        }
        if ($Python.HasExited) {
            Write-Status "Python" "EXIT" "人脸识别引擎已退出" "Red"
            break
        }
        Start-Sleep -Seconds 3
    }
}

$Script:ExitEventSubscriber = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    $NodePid = [Environment]::GetEnvironmentVariable('CV_NODE_PID')
    $PythonPid = [Environment]::GetEnvironmentVariable('CV_PYTHON_PID')
    if ($NodePid) { Stop-Process -Id $NodePid -ErrorAction SilentlyContinue }
    if ($PythonPid) { Stop-Process -Id $PythonPid -ErrorAction SilentlyContinue }
}

Write-Banner
Import-DotEnv (Join-Path $RootDir ".env")
$Logs = Initialize-Logs

try {
    $DatabaseState = Initialize-Databases
    Clear-TestDataIfRequested -DatabaseState $DatabaseState
    $NodeProcess = Start-AvatarServer -Logs $Logs
    [Environment]::SetEnvironmentVariable('CV_NODE_PID', $NodeProcess.Id, 'Process')
    Wait-TtsPrewarmIfEnabled -Process $NodeProcess
    $AvatarUrl = Open-AvatarBrowserAndWait -Process $NodeProcess
    $PythonProcess = Start-FaceRecognition -Logs $Logs
    [Environment]::SetEnvironmentVariable('CV_PYTHON_PID', $PythonProcess.Id, 'Process')
    Show-RunningInfo -Url $AvatarUrl
    Watch-Processes -Node $NodeProcess -Python $PythonProcess
}
catch {
    Write-Host ""
    Write-Status "启动" "FAIL" $_.Exception.Message "Red"
    exit 1
}
finally {
    if ($Script:ExitEventSubscriber) {
        Unregister-Event -SourceIdentifier PowerShell.Exiting -ErrorAction SilentlyContinue
    }
    Stop-System
    [Environment]::SetEnvironmentVariable('CV_NODE_PID', $null, 'Process')
    [Environment]::SetEnvironmentVariable('CV_PYTHON_PID', $null, 'Process')
}