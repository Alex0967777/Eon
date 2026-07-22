# EonMemory transport capsule. Generated automatically; do not edit.
import base64,gzip,hashlib,os,subprocess,sys
from pathlib import Path

NAME='EonMemory80.py'
STEP=80
SHA256='0f013cfdb08be99f7161e739088f748f0ba6cc77c865f286539fe369a58e55e9'
PAYLOAD=(
    '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'
    '6X+unMkk/8A28/8vPGDX7C8AAA=='
)

def main():
    try:
        data=gzip.decompress(base64.b64decode(PAYLOAD.encode('ascii'),validate=True))
    except Exception as exc:
        raise SystemExit(f'BOOTSTRAP decode failed: {exc}')
    actual=hashlib.sha256(data).hexdigest()
    if actual != SHA256:
        raise SystemExit(f'BOOTSTRAP SHA-256 mismatch: expected {SHA256}, got {actual}')
    root=Path(os.environ.get('EONMEMORY_HOME','/mnt/data'))
    root.mkdir(parents=True,exist_ok=True)
    target=root/NAME
    temp=target.with_suffix(target.suffix+'.tmp')
    temp.write_bytes(data)
    os.replace(temp,target)
    print(f'Checkpoint восстановлен: {target}')
    print(f'SHA-256 подтверждён: {actual}')
    subprocess.run([sys.executable,str(target),'--start'],check=True)

if __name__=='__main__':
    main()
