[CmdletBinding()]
param(
    [switch]$Silent
)

$launcher = Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1' -File |
    Where-Object { $_.Name -ne [System.IO.Path]::GetFileName($PSCommandPath) } |
    Select-Object -First 1

if (-not $launcher) {
    throw 'Physics Vault launcher was not found.'
}

& $launcher.FullName -Silent:$Silent
exit $LASTEXITCODE
