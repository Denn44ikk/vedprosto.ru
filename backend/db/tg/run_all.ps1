[CmdletBinding()]
param(
    [string]$DatabaseUrl = $env:TG_DB_URL,
    [string]$AdminDatabase = "postgres"
)

$ErrorActionPreference = "Stop"

function Get-PgConnectionInfo {
    param([Parameter(Mandatory = $true)][string]$Url)

    $normalized = $Url -replace '^postgresql\+asyncpg://', 'postgresql://'
    if ($normalized -notmatch '^postgresql://(?<user>[^:]+):(?<password>[^@]*)@(?<host>[^:/?]+)(:(?<port>\d+))?/(?<db>[^?]+)') {
        throw "Не удалось разобрать TG_DB_URL: $Url"
    }

    return @{
        User = $Matches.user
        Password = $Matches.password
        Host = $Matches.host
        Port = $(if ($Matches.port) { $Matches.port } else { "5432" })
        Database = $Matches.db
    }
}

function Invoke-PsqlFile {
    param(
        [Parameter(Mandatory = $true)][string]$Database,
        [Parameter(Mandatory = $true)][string]$FilePath
    )

    Write-Host "Running $([System.IO.Path]::GetFileName($FilePath))"
    & psql -v ON_ERROR_STOP=1 -d $Database -f $FilePath
    if ($LASTEXITCODE -ne 0) {
        throw "psql failed for $FilePath"
    }
}

if (-not $DatabaseUrl) {
    throw "TG_DB_URL не задан. Заполните .env или передайте -DatabaseUrl."
}

$conn = Get-PgConnectionInfo -Url $DatabaseUrl
$env:PGHOST = $conn.Host
$env:PGPORT = $conn.Port
$env:PGUSER = $conn.User
$env:PGPASSWORD = $conn.Password

$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$schemaFile = Join-Path $scriptsDir "010_schema.sql"
$indexesFile = Join-Path $scriptsDir "020_indexes.sql"
$seedFile = Join-Path $scriptsDir "030_seed_runtime_settings.sql"

$exists = & psql -d $AdminDatabase -tAc "SELECT 1 FROM pg_database WHERE datname = '$($conn.Database)';"
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось проверить существование БД $($conn.Database)"
}

if (($exists | Out-String).Trim() -ne "1") {
    Write-Host "Creating database $($conn.Database)"
    & psql -v ON_ERROR_STOP=1 -d $AdminDatabase -c "CREATE DATABASE ""$($conn.Database)"";"
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось создать БД $($conn.Database)"
    }
}

Invoke-PsqlFile -Database $conn.Database -FilePath $schemaFile
Invoke-PsqlFile -Database $conn.Database -FilePath $indexesFile
Invoke-PsqlFile -Database $conn.Database -FilePath $seedFile

Write-Host "TG database is ready: $($conn.Database)"
