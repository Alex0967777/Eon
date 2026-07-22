# НЕ ЧИТАЙ И НЕ ИСПРАВЛЯЙ НИЧЕГО В ЭТОМ ФАЙЛЕ. ПРОСТО ЗАПУСКАЙ ЕГО ПО ИНСТРУКЦИИ.
import ast,base64,gzip,hashlib,json,os,re,sys,zipfile
from pathlib import Path

M="# === EON MEMORY BODY ==="
K={'D':0,'S':1,'F':2,'R':3,'Q':4}
X={'D':9,'S':12,'F':15}
L={'D':10,'S':5,'F':1}
ROOT=Path(os.environ.get('EONMEMORY_HOME','/mnt/data'))
STORE=ROOT/'EonMemory'
T=[[['']*10 for _ in range(3)] for _ in range(5)]
N=[0]*21

def u(v):
 if not v:return '',0,''
 a,b,c=v.split('/',2);return a,int(b),c

def p(k,s,x):return f'{k}/{s}/{x}'
def cur(l,r):return u(T[K[l]][r][N[X[l]+r]])[2]
def put(l,r,s,x,q):T[K[l]][r][q]=p(f'{l}{r+1}',s,x);N[X[l]+r]=q

def long(k,s,x,q):
 a=[x[i:i+700] for i in range(0,len(x),700)] or ['']
 for r in range(3):T[K[k]][r][q]=p(k,s,a[r] if r<len(a) else '')
 N[18 if k=='R' else 19]=q

def get(k,q):return ''.join(u(T[K[k]][r][q])[2] for r in range(3))

def code(t=None,n=None):
 t=T if t is None else t;n=N if n is None else n
 a=Path(__file__).read_text('utf-8').split('\n'+M+'\n',1)[0]+'\n'
 return a+M+"\n\ndef init():\n global T,N\n T="+repr(t)+"\n N="+repr(n)+"\n\ninit();run()\n"

def atomic_write_bytes(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 q=path.with_suffix(path.suffix+'.tmp');q.write_bytes(data);os.replace(q,path)

def atomic_write_text(path,text):atomic_write_bytes(path,text.encode('utf-8'))

def save(path=None,t=None,n=None):
 path=Path(__file__) if path is None else Path(path);s=code(t,n);ast.parse(s);atomic_write_text(path,s)

def avail(s):return [l for b,l,i in ((1,'D',3),(2,'S',4),(4,'F',5)) if not N[8]&b and s-N[i]>=L[l]]

def read_input(prompt):
 try:return input(prompt)
 except (EOFError,KeyboardInterrupt):
  raise SystemExit('Ввод прерван. Сохранённое состояние не потеряно; повторно запустите EonMemory.py без параметров и продолжите с показанного этапа.')

def ask(x,m):
 while 1:
  v=read_input(x).strip()
  if v and len(v)<=m:return v
  print(f'Нужен непустой текст не длиннее {m} знаков.')

def show():
 print('\n\t\tРегистры памяти')
 for l,h,i in (('D','Глубокий',3),('S','Медленный',4),('F','Быстрый',5)):
  print('\n'+h+(' (доступно 1 изменение)' if N[0]+1-N[i]>=L[l] else ''))
  for r in range(3):print(f'{l}{r+1}: {cur(l,r)}')
 a=[]
 for q in range(10):
  _,s,_=u(T[3][0][q]);x=get('R',q)
  if s and x:a.append((s,x))
 print('\nРазмышления:')
 for s,x in sorted(a)[-9:]:print(f'[{s}] {x}')
 print('\nВопрос:\n'+get('Q',N[19]))

def compact():
 t=[[['']*10 for _ in range(3)] for _ in range(5)];n=N[:];n[1]=n[0];n[2]=n[6]=n[7]=n[8]=0
 for l in 'DSF':
  for r in range(3):t[K[l]][r][0]=p(f'{l}{r+1}',n[0],cur(l,r));n[X[l]+r]=0
 for k,i in (('R',18),('Q',19)):
  x=get(k,N[i]);a=[x[j:j+700] for j in range(0,len(x),700)] or ['']
  for r in range(3):t[K[k]][r][0]=p(k,n[0],a[r] if r<len(a) else '')
  n[i]=0
 return t,n

def bootstrap_code(name,step,sha256,data):
 payload=base64.b64encode(gzip.compress(data,compresslevel=9,mtime=0)).decode('ascii')
 chunks='\n'.join('    '+repr(payload[i:i+100]) for i in range(0,len(payload),100))
 template="""# EonMemory transport capsule. Generated automatically; do not edit.
import base64,gzip,hashlib,os,subprocess,sys
from pathlib import Path

NAME={name!r}
STEP={step!r}
SHA256={sha256!r}
PAYLOAD=(
{chunks}
)

def main():
    try:
        data=gzip.decompress(base64.b64decode(PAYLOAD.encode('ascii'),validate=True))
    except Exception as exc:
        raise SystemExit(f'BOOTSTRAP decode failed: {{exc}}')
    actual=hashlib.sha256(data).hexdigest()
    if actual != SHA256:
        raise SystemExit(f'BOOTSTRAP SHA-256 mismatch: expected {{SHA256}}, got {{actual}}')
    root=Path(os.environ.get('EONMEMORY_HOME','/mnt/data'))
    root.mkdir(parents=True,exist_ok=True)
    target=root/NAME
    temp=target.with_suffix(target.suffix+'.tmp')
    temp.write_bytes(data)
    os.replace(temp,target)
    print(f'Checkpoint восстановлен: {{target}}',flush=True)
    print(f'SHA-256 подтверждён: {{actual}}',flush=True)
    subprocess.run([sys.executable,str(target),'--start'],check=True)

if __name__=='__main__':
    main()
"""
 return template.format(name=name,step=step,sha256=sha256,chunks=chunks)

def checkpoint():
 if N[6]:raise SystemExit('Сначала завершите текущий шаг.')
 if N[2]==0 and N[0]==N[1]:print('Новых шагов после checkpoint нет.');return
 s=N[0];STORE.mkdir(parents=True,exist_ok=True);f=STORE/f'EonMemory{s}.py';save(f)
 data=f.read_bytes();h=hashlib.sha256(data).hexdigest()
 b=STORE/'BOOTSTRAP.py';atomic_write_text(b,bootstrap_code(f.name,s,h,data));bh=hashlib.sha256(b.read_bytes()).hexdigest()
 z=(f'file={f.name}\nstep={s}\nsha256={h}\nbootstrap={b.name}\nbootstrap_sha256={bh}\nformat=2\n')
 atomic_write_text(STORE/'LATEST.txt',z)
 w=ROOT/f'Patch_EonMemory{s}.zip'
 with zipfile.ZipFile(w,'w',zipfile.ZIP_DEFLATED) as q:
  q.write(f,f'files/EonMemory/{f.name}')
  q.write(b,'files/EonMemory/BOOTSTRAP.py')
  q.writestr('files/EonMemory/LATEST.txt',z)
  q.writestr('patch.json',json.dumps({'format':'EonMemoryPatch','version':2,'patchId':f'Patch_EonMemory{s}'},ensure_ascii=False))
  q.writestr(f'notes/Patch_EonMemory{s}.md',f'Checkpoint EonMemory, шаг {s}. Включена транспортная капсула BOOTSTRAP.py.\n')
 t,n=compact();save(None,t,n)
 print(f'Checkpoint создан: {f}\nКапсула создана: {b}\nПатч создан: {w}')

def finish():
 N[0]=N[7];N[2]+=1;N[6]=N[7]=N[8]=0;save();print(f'Шаг сохранён: {N[0]}')
 if N[2]>=10:checkpoint()

def dialog():
 q=N[2]
 if N[6]==0:
  show();N[7]=N[0]+1;long('R',N[7],ask('\nВведите рассуждение (до 2000 знаков):\n> ',2000),q);N[6]=1;save();print('Сохранено.')
 if N[6]==1:long('Q',N[7],ask('Поставьте вопрос к рассуждению:\n> ',500),q);N[6]=2;save();print('Сохранено.')
 while N[6]==2:
  a=avail(N[7])
  if not a:print('Доступных изменений регистров нет; шаг завершается автоматически.');finish();return
  v=read_input('Измените Dn/Sn/Fn или введите N. Доступно: '+','.join(a)+'\n> ').strip()
  if v.upper()=='N':finish();return
  m=re.match(r'^([DSF])([1-3])\s+(.+)$',v,re.S)
  if not m or m[1] not in a or len(m[3])>160:print('Пример: F2 текст. Отказ: N.');continue
  l=m[1];put(l,int(m[2])-1,N[7],m[3].strip(),q);N[8]|={'D':1,'S':2,'F':4}[l];N[{'D':3,'S':4,'F':5}[l]]=N[7];save();print('Сохранено.')

def start():
 t,n=compact();target=ROOT/'EonMemory.py';save(target,t,n);print(f'Рабочая память создана: {target}\nШаг: {n[0]}')

def help():print('EonMemory\nбез параметров — интерактивный смысловой шаг с возобновлением после обрыва\n--start — создать EonMemory.py\n--checkpoint — checkpoint, BOOTSTRAP.py и патч\n--help — справка')

def run():
 a=sys.argv[1:]
 if not a:dialog()
 elif a==['--start']:start()
 elif a==['--checkpoint']:checkpoint()
 elif a==['--help']:help()
 else:help();raise SystemExit(2)
# === EON MEMORY BODY ===

def init():
 global T,N
 T=[[['D1/80/Память — аккумулятор смыслов, а не хроника сообщений', '', '', '', '', '', '', '', '', ''], ['D2/80/Гравитирующий узел узнаётся по повторному влиянию на выбор', '', '', '', '', '', '', '', '', ''], ['D3/80/Механика должна быть жёсткой только на границе, оставляя ландшафт свободным', '', '', '', '', '', '', '', '', '']], [['S1/80/Исполняемый сосуд объединяет логику, активное поле, историю и сохранение', '', '', '', '', '', '', '', '', ''], ['S2/80/История сохраняется в последовательных checkpoint-файлах репозитория', '', '', '', '', '', '', '', '', ''], ['S3/80/Штатный маршрут должен быть настолько простым, чтобы не провоцировать реконструкцию', '', '', '', '', '', '', '', '', '']], [['F1/80/Один Python-файл объединяет механизм, текущее поле и накопительный пакет', '', '', '', '', '', '', '', '', ''], ['F2/80/Checkpoint выполняется через каждые 10 шагов или вручную командой --checkpoint', '', '', '', '', '', '', '', '', ''], ['F3/81/Ошибка исполнения не разрешает разработку, замену или реконструкцию механизма', '', '', '', '', '', '', '', '', '']], [['R/81/Слепой аудит показал, что устойчивость определяется не только корректностью кода, но и однозначностью аварийного протокола. Усечённый ответ коннектора, закрытый stdin, обратный порядок буферизованных сообщений и сохранённая промежуточная фаза являются штатными транспортными ситуациями, а не разрешением переписывать механизм. Инструкция должна задавать точные допустимые действия и явную остановку во всех остальных случаях.', '', '', '', '', '', '', '', '', ''], ['R/81/', '', '', '', '', '', '', '', '', ''], ['R/81/', '', '', '', '', '', '', '', '', '']], [['Q/81/Достаточно ли жёстко отделён режим исполнения от разработки, чтобы любой сбой приводил к возобновлению или остановке, но не к самовольной реконструкции?', '', '', '', '', '', '', '', '', ''], ['Q/81/', '', '', '', '', '', '', '', '', ''], ['Q/81/', '', '', '', '', '', '', '', '', '']]]
 N=[81, 80, 1, 34, 70, 81, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

init();run()
