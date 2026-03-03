# do_copy.ps1 — Деплой aipilot-llm Phase 2 изменений
# Запуск: .\do_copy.ps1
# Копирует изменённые/новые файлы в реальный проект C:\PROJETS AI PILOT\AI_PILOT_LLM\
# Примечание: Antigravity пишет напрямую в AI_PILOT_LLM\ — этот скрипт для верификации

$SRC = "C:\PROJETS AI PILOT\AI_PILOT_LLM\src\aipilot_llm"
$TESTS = "C:\PROJETS AI PILOT\AI_PILOT_LLM\tests"
$ROOT = "C:\PROJETS AI PILOT\AI_PILOT_LLM"

Write-Host "== aipilot-llm Phase 2 Deploy ==" -ForegroundColor Cyan
Write-Host "All files written directly to $ROOT" -ForegroundColor Green
Write-Host ""

# Список изменённых/созданных файлов
$files = @(
    # Providers
    "$SRC\openai_provider.py",
    "$SRC\local_provider.py",
    # New files
    "$SRC\health.py",
    # Routes
    "$SRC\routes\integration_1c.py",
    "$SRC\routes\code.py",
    # Updated
    "$SRC\__init__.py",
    # Tests
    "$TESTS\conftest.py",
    "$TESTS\helpers.py",
    "$TESTS\test_router.py",
    "$TESTS\test_anthropic.py",
    "$TESTS\test_mistral.py",
    "$TESTS\test_openai.py",
    "$TESTS\test_geoip.py",
    "$TESTS\test_base.py",
    "$TESTS\__init__.py",
    # Config
    "$ROOT\pyproject.toml"
)

foreach ($file in $files) {
    if (Test-Path $file) {
        $rel = $file.Replace($ROOT, "").TrimStart("\")
        $size = (Get-Item $file).Length
        Write-Host "  OK  $rel ($size bytes)" -ForegroundColor Green
    }
    else {
        $rel = $file.Replace($ROOT, "").TrimStart("\")
        Write-Host "  !!  MISSING: $rel" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "== Running verification ==" -ForegroundColor Cyan

# 1. Import check
Write-Host "1. Import check..." -ForegroundColor Yellow
$result = python -c "from aipilot_llm import get_provider, health_router; print('OK')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "   PASS: from aipilot_llm import get_provider, health_router" -ForegroundColor Green
}
else {
    Write-Host "   FAIL: $result" -ForegroundColor Red
}

# 2. Health router check
Write-Host "2. Health router check..." -ForegroundColor Yellow
$result = python -c "from aipilot_llm.health import router; print(f'OK: {len(router.routes)} routes')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "   PASS: $result" -ForegroundColor Green
}
else {
    Write-Host "   FAIL: $result" -ForegroundColor Red
}

# 3. Run tests
Write-Host "3. Running pytest..." -ForegroundColor Yellow
$testResult = python -m pytest "$TESTS" -v --tb=short --rootdir="$ROOT" --import-mode=importlib -q 2>&1
if ($LASTEXITCODE -eq 0) {
    $passed = ($testResult | Select-String "passed").ToString()
    Write-Host "   PASS: $passed" -ForegroundColor Green
}
else {
    Write-Host "   FAIL: Tests failed!" -ForegroundColor Red
    $testResult | Select-Object -Last 20 | ForEach-Object { Write-Host "   $_" -ForegroundColor Red }
}

Write-Host ""
Write-Host "== Phase 2 Deploy complete ==" -ForegroundColor Cyan
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  git add -A" -ForegroundColor White
Write-Host "  git commit -m 'feat: aipilot-llm Phase 2 — OpenAI/Local providers, tests, health, routes'" -ForegroundColor White
Write-Host "  git push" -ForegroundColor White
Write-Host "  railway up --service ai-pilot-api --detach" -ForegroundColor White
