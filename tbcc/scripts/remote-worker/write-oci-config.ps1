# Write ~/.oci/config without the interactive oci setup config wizard.
# Edit the variables below, then run:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\scripts\remote-worker\write-oci-config.ps1
#
# NEVER commit this file with real OCIDs filled in.

$UserOcid     = "ocid1.user.oc1..aaaaaaaafigukslykdkxe6jdyks4qzsaglvoqbnzbf7iodzrujcvv5okhqjq"
$TenancyOcid  = "ocid1.tenancy.oc1..aaaaaaaa2fefhostpuptorsgflf6nakikmj2ow5dw5qdoc54hasb4intyopq"
$Fingerprint  = "30:2b:b5:5a:e5:c3:89:1e:6e:40:c1:ca:e4:88:b0:f4"
$Region       = "us-sanjose-1"
$KeyFile      = "C:\Users\ianmp\Downloads\aof.ianmx@gmail.com-2026-07-05T02_06_35.065Z.pem"
$OciDir = "$env:USERPROFILE\.oci"
$ConfigPath = "$OciDir\config"

if ($UserOcid -like "PASTE_*" -or $TenancyOcid -like "PASTE_*" -or $Fingerprint -like "PASTE_*") {
  Write-Error "Edit the variables at the top of write-oci-config.ps1 first."
  exit 1
}

if ($TenancyOcid -notmatch "^ocid1\.tenancy\.") {
  Write-Error "Tenancy OCID must start with ocid1.tenancy. (not API Gateway or Generative AI key)."
  exit 1
}

if (-not (Test-Path $KeyFile)) {
  Write-Error "Private key not found: $KeyFile. Download from My profile > Tokens and keys > Add API key."
  exit 1
}

New-Item -ItemType Directory -Force -Path $OciDir | Out-Null

$config = @"
[DEFAULT]
user=$UserOcid
fingerprint=$Fingerprint
tenancy=$TenancyOcid
region=$Region
key_file=$KeyFile
"@

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($ConfigPath, $config, $utf8NoBom)
Write-Host "Wrote $ConfigPath"
Write-Host "Test: oci iam region list"
