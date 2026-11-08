param([Parameter(Mandatory = $true)][string]$BackendProjectPath)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath $BackendProjectPath).Path
$pythonw = Join-Path $project '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'Backend Python environment not found.' }
$target = Join-Path $PSScriptRoot 'launch_web.py'
$desktopDirectory = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
# Use Unicode code points so Windows PowerShell 5 can read this script without a BOM.
$title = -join ([char[]]@(0xB2EC,0xC7A0,0x20,0xC6F9,0xC571))
$startLabel = -join ([char[]]@(0xC2E4,0xD589))
$stopLabel = -join ([char[]]@(0xC885,0xB8CC))
foreach ($pair in @(@($startLabel,''), @($stopLabel,' --stop'))) {
    $shortcut = $shell.CreateShortcut((Join-Path $desktopDirectory ($title + ' ' + $pair[0] + '.lnk')))
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = '"' + $target + '" --backend-project "' + $project + '"' + $pair[1]
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.WindowStyle = 7
    $shortcut.IconLocation = $pythonw + ',0'
    $shortcut.Save()
}
Write-Output 'WEB_APP_SHORTCUTS_INSTALLED'

$phone = -join ([char[]]@(0xD734,0xB300,0xD3F0,0x20,0xACF5,0xC720))
$phoneTarget = Join-Path $PSScriptRoot 'share_phone.py'
if (Test-Path -LiteralPath $phoneTarget) {
    foreach ($pair in @(@($startLabel,''),@($stopLabel,' --stop'))) {
        $shortcut = $shell.CreateShortcut((Join-Path $desktopDirectory ($title + ' ' + $phone + ' ' + $pair[0] + '.lnk')))
        $shortcut.TargetPath = $pythonw
        $shortcut.Arguments = '"' + $phoneTarget + '" --backend-project "' + $project + '"' + $pair[1]
        $shortcut.WorkingDirectory = $PSScriptRoot
        $shortcut.WindowStyle = 7
        $shortcut.Save()
    }
}
