# Pester tests for the trim keep/kill decision that guards against the 0/10 incident
# (an aggressive trim that killed live service wrappers). Run:
#   Invoke-Pester -Path scripts\tests\trim-safety.Tests.ps1
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "..\tbcc-service-control.ps1")

function New-Wrapper {
  param([int]$WrapperPid, [int]$AgeMinutes, [bool]$OwnsLive)
  [pscustomobject]@{ Pid = $WrapperPid; Created = (Get-Date).AddMinutes(-$AgeMinutes); OwnsLive = $OwnsLive }
}

Describe "Select-TbccTabWrapperKeepPid" {

  It "keeps the OLDER wrapper that owns the live worker over a newer empty shell (0/10 regression)" {
    $wrappers = @(
      (New-Wrapper -WrapperPid 100 -AgeMinutes 30 -OwnsLive $true),   # live worker lives here
      (New-Wrapper -WrapperPid 200 -AgeMinutes 1  -OwnsLive $false)   # newer, but empty
    )
    Select-TbccTabWrapperKeepPid -Wrappers $wrappers | Should Be 100
  }

  It "keeps the NEWEST live-owning wrapper when several own workers (singleton to 1, never 0)" {
    $wrappers = @(
      (New-Wrapper -WrapperPid 100 -AgeMinutes 30 -OwnsLive $true),
      (New-Wrapper -WrapperPid 300 -AgeMinutes 5  -OwnsLive $true)
    )
    Select-TbccTabWrapperKeepPid -Wrappers $wrappers | Should Be 300
  }

  It "keeps the newest wrapper when NONE own a live worker (never drops to zero)" {
    $wrappers = @(
      (New-Wrapper -WrapperPid 100 -AgeMinutes 30 -OwnsLive $false),
      (New-Wrapper -WrapperPid 200 -AgeMinutes 1  -OwnsLive $false)
    )
    Select-TbccTabWrapperKeepPid -Wrappers $wrappers | Should Be 200
  }

  It "returns the single wrapper's pid" {
    Select-TbccTabWrapperKeepPid -Wrappers @((New-Wrapper -WrapperPid 100 -AgeMinutes 3 -OwnsLive $false)) | Should Be 100
  }

  It "returns null for an empty set" {
    Select-TbccTabWrapperKeepPid -Wrappers @() | Should Be $null
  }
}
