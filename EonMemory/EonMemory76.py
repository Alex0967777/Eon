# НЕ ЧИТАЙ И НЕ ИСПРАВЛЯЙ НИЧЕГО В ЭТОМ ФАЙЛЕ. ПРОСТО ЗАПУСКАЙ ЕГО ПО ИНСТРУКЦИИ.
import ast,hashlib,json,os,re,sys,zipfile
from pathlib import Path
M="# === EON MEMORY BODY ==="; K={'D':0,'S':1,'F':2,'R':3,'Q':4}; X={'D':9,'S':12,'F':15}; L={'D':10,'S':5,'F':1}
T=[[['']*10 for _ in range(3)] for _ in range(5)]; N=[0]*21

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
def save(path=None,t=None,n=None):
 path=Path(__file__) if path is None else Path(path);s=code(t,n);ast.parse(s);path.parent.mkdir(parents=True,exist_ok=True)
 q=path.with_suffix(path.suffix+'.tmp');q.write_text(s,'utf-8');os.replace(q,path)
def avail(s):return [l for b,l,i in ((1,'D',3),(2,'S',4),(4,'F',5)) if not N[8]&b and s-N[i]>=L[l]]
def ask(x,m):
 while 1:
  v=input(x).strip()
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
def checkpoint():
 if N[6]:raise SystemExit('Сначала завершите текущий шаг.')
 if N[2]==0 and N[0]==N[1]:print('Новых шагов после checkpoint нет.');return
 s=N[0];d=Path('/mnt/data/EonMemory');d.mkdir(parents=True,exist_ok=True);f=d/f'EonMemory{s}.py';save(f)
 h=hashlib.sha256(f.read_bytes()).hexdigest();z=f'file={f.name}\nstep={s}\nsha256={h}\n';(d/'LATEST.txt').write_text(z,'utf-8')
 w=Path(f'/mnt/data/Patch_EonMemory{s}.zip')
 with zipfile.ZipFile(w,'w',zipfile.ZIP_DEFLATED) as q:
  q.write(f,f'files/EonMemory/{f.name}');q.writestr('files/EonMemory/LATEST.txt',z);q.writestr('patch.json',json.dumps({'format':'EonMemoryPatch','version':1,'patchId':f'Patch_EonMemory{s}'},ensure_ascii=False));q.writestr(f'notes/Patch_EonMemory{s}.md',f'Checkpoint EonMemory, шаг {s}.\n')
 t,n=compact();save(None,t,n);print(f'Checkpoint создан: {f}\nПатч создан: {w}')
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
  if not a:finish();return
  v=input('Измените Dn/Sn/Fn или введите N. Доступно: '+','.join(a)+'\n> ').strip()
  if v.upper()=='N':finish();return
  m=re.match(r'^([DSF])([1-3])\s+(.+)$',v,re.S)
  if not m or m[1] not in a or len(m[3])>160:print('Пример: F2 текст. Отказ: N.');continue
  l=m[1];put(l,int(m[2])-1,N[7],m[3].strip(),q);N[8]|={'D':1,'S':2,'F':4}[l];N[{'D':3,'S':4,'F':5}[l]]=N[7];save();print('Сохранено.')
def start():
 t,n=compact();save('/mnt/data/EonMemory.py',t,n);print(f'Рабочая память создана: /mnt/data/EonMemory.py\nШаг: {n[0]}')
def help():print('EonMemory\nбез параметров — смысловой шаг\n--start — создать EonMemory.py\n--checkpoint — checkpoint и патч\n--help — справка')
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
 T=[[['D1/76/Память — аккумулятор смыслов, а не хроника сообщений','','','','','','','','',''],['D2/76/Гравитирующий узел узнаётся по повторному влиянию на выбор','','','','','','','','',''],['D3/76/Механика должна быть жёсткой только на границе, оставляя ландшафт свободным','','','','','','','','','']],[['S1/76/Исполняемый сосуд объединяет логику, активное поле, историю и сохранение','','','','','','','','',''],['S2/76/История сохраняется в последовательных checkpoint-файлах репозитория','','','','','','','','',''],['S3/76/Штатный маршрут должен быть настолько простым, чтобы не провоцировать реконструкцию','','','','','','','','','']],[['F1/76/Один Python-файл объединяет механизм, текущее поле и накопительный пакет','','','','','','','','',''],['F2/76/Checkpoint выполняется через каждые 10 шагов или вручную командой --checkpoint','','','','','','','','',''],['F3/76/Команда N завершает этап регистров без изменения доступных строк','','','','','','','','','']],[['R/76/Новая архитектура EonMemory отказалась от бинарников и транспортных капсул. Обычный Python-файл содержит неизменяемую механику и хвостовую процедуру инициализации памяти. Рабочий EonMemory.py накапливает до десяти смысловых шагов; затем или по команде --checkpoint создаёт неизменяемый EonMemoryNN.py, индекс LATEST.txt и готовый патч. После подтверждённого checkpoint рабочий пакет очищается, но текущее состояние сохраняется.','','','','','','','','',''],['R/76/','','','','','','','','',''],['R/76/','','','','','','','','','']],[['Q/76/Переживёт ли однозначный текстовый маршрут первый запуск в чистом контексте?','','','','','','','','',''],['Q/76/','','','','','','','','',''],['Q/76/','','','','','','','','','']]]
 N=[76,76,0,34,70,76,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]

init();run()
