"""Start the local app and open the browser only after it is ready."""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8765'


def ready():
    try:
        with urllib.request.urlopen(URL + '/api/health', timeout=1) as response:
            data = json.load(response)
            return data.get('app') == 'trilha' and data.get('version') == '1.3.0'
    except (OSError, ValueError):
        return False


def main():
    if ready():
        print('Trilha já está funcionando em ' + URL)
        webbrowser.open(URL)
        return 0
    command = [sys.executable, str(ROOT / 'app.py')]
    if '--reload' in sys.argv:
        command.append('--reload')
    process = subprocess.Popen(command, cwd=ROOT)
    try:
        for _ in range(60):
            if process.poll() is not None:
                print('O servidor não iniciou. Confira a mensagem acima e se a porta 8765 está livre.')
                return 1
            if ready():
                print('\nTRILHA pronto em ' + URL + '\nMantenha esta janela aberta. Ctrl+C para encerrar.', flush=True)
                webbrowser.open(URL)
                return process.wait()
            time.sleep(.5)
        print('O servidor não respondeu no prazo esperado.')
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    raise SystemExit(main())
