# EonMemory transport capsule. Generated automatically; do not edit.
import base64,gzip,hashlib,os,subprocess,sys
from pathlib import Path

NAME='EonMemory81.py'
STEP=81
SHA256='113edb6a717d0acc8c09eb86fda3c4a65030ccbc00e4d239e30ba41237f45dec'
PAYLOAD=(
    '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'
    'EpcyF/+/mEol/71R6n8BHKnTLvsoAAA='
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
    print(f'Checkpoint восстановлен: {target}',flush=True)
    print(f'SHA-256 подтверждён: {actual}',flush=True)
    subprocess.run([sys.executable,str(target),'--start'],check=True)

if __name__=='__main__':
    main()
