Set-Location $PSScriptRoot
& D:/miniconda3/envs/py310/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
