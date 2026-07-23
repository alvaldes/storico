#!/bin/sh
set -e

echo "=== Entrypoint: checking imports ==="
python3 -c "
import sys
try:
    from storico.api.app import app
    print('IMPORT OK', flush=True)
except Exception as e:
    print(f'IMPORT FAIL: {e}', flush=True)
    sys.exit(1)
try:
    import uvicorn
    print(f'UVICORN OK: {uvicorn.__version__}', flush=True)
except Exception as e:
    print(f'UVICORN FAIL: {e}', flush=True)
    sys.exit(1)
print('ALL CHECKS PASSED', flush=True)
"

echo "=== Entrypoint: starting uvicorn ==="
exec python3 -m uvicorn storico.api.app:app --host 0.0.0.0 --port 8000
