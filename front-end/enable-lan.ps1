#Requires -RunAsAdministrator
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 4173
)

$ErrorActionPreference = 'Stop'
$nodePath = (Get-Command node.exe -CommandType Application).Source
$ruleName = "GiaSuAI-Frontend-LAN-$Port"

if ($PSCmdlet.ShouldProcess($ruleName, "Allow Node.js TCP $Port from LocalSubnet")) {
    $existing = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    if ($existing) {
        Set-NetFirewallRule -Name $ruleName -Enabled True -Direction Inbound -Action Allow `
            -Profile Any -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet -Program $nodePath | Out-Null
    } else {
        New-NetFirewallRule -Name $ruleName -DisplayName "Gia Su AI - LAN TCP $Port" `
            -Direction Inbound -Action Allow -Enabled True -Profile Any -Protocol TCP `
            -LocalPort $Port -RemoteAddress LocalSubnet -Program $nodePath | Out-Null
    }
    Write-Host "LAN access enabled for Node.js TCP port $Port (LocalSubnet)."
}
