<#
  .SYNOPSIS
    Convert .ppt (old binary format) to .pptx (Open XML) via PowerPoint COM.
    Used internally by PPT parser — called via subprocess from Python.
  .PARAMETER SourceFile
    Absolute path to the .ppt file.
  .PARAMETER TargetFile
    Absolute path for the output .pptx file.
#>
param(
    [string]$SourceFile,
    [string]$TargetFile
)

$ppt = New-Object -ComObject PowerPoint.Application
try {
    $presentation = $ppt.Presentations.Open($SourceFile)
    $presentation.SaveAs($TargetFile, 24)  # 24 = ppSaveAsOpenXMLPresentation
    $presentation.Close()
    Write-Host "SUCCESS: $TargetFile"
} finally {
    $ppt.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null
}
