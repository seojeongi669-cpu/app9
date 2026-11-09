"""끝까지 — 학습 플래너
실행: streamlit run app.py
기본 SQLite 저장은 Streamlit Cloud 재배포 시 사라질 수 있습니다.
영구 저장: Supabase SQL Editor에서 실행:
create table public.study_accounts (id text primary key, payload jsonb not null, version integer not null default 0);
alter table public.study_accounts enable row level security;
-- anon/authenticated 정책은 추가하지 마세요. 이 테이블은 서버 전용입니다.
Streamlit Settings > Secrets (GitHub에 업로드 금지):
SUPABASE_URL = "https://프로젝트.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "서버 전용 service_role 키"
기존 앱과 다른 저장 구조이며 기존 계정은 자동 이전되지 않습니다.
"""
import hashlib
import secrets
import sqlite3
import json
import time as clock
from datetime import datetime,date,timedelta
from zoneinfo import ZoneInfo
import requests
import streamlit as st
import streamlit.config as config
for k,v in {'theme.base':'light','theme.primaryColor':'#4263EB','theme.backgroundColor':'#F6F8FC','theme.secondaryBackgroundColor':'#FFFFFF','theme.textColor':'#202D45'}.items():
    config.set_option(k,v)
st.set_page_config(page_title='끝까지 · 학습 플래너',page_icon='🌱',layout='centered')
TODAY=datetime.now(ZoneInfo('Asia/Seoul')).date()
WEEK=['월','화','수','목','금','토','일']
def cloud():
    try:
        return bool(st.secrets.get('SUPABASE_URL') and st.secrets.get('SUPABASE_SERVICE_ROLE_KEY'))
    except Exception:
        return False

def store(key, data=None, version=None):
    if cloud():
        secret=st.secrets['SUPABASE_SERVICE_ROLE_KEY']
        headers={'apikey':secret,'Authorization':'Bearer '+secret,'Prefer':'return=representation'}
        url=st.secrets['SUPABASE_URL'].rstrip('/')+'/rest/v1/study_accounts'
        try:
            if data is None:
                r=requests.get(url,headers=headers,params={'id':'eq.'+key,'select':'payload,version'},timeout=15)
            elif version is None:
                r=requests.post(url,headers=headers,json={'id':key,'payload':data,'version':0},timeout=15)
            else:
                r=requests.patch(url,headers=headers,params={'id':'eq.'+key,'version':'eq.'+str(version)},json={'payload':data,'version':version+1},timeout=15)
            r.raise_for_status()
            rows=r.json()
            if data is None:
                return (rows[0]['payload'],rows[0]['version']) if rows else (None,None)
            if not rows:
                raise RuntimeError('다른 가족이 수정했어요. 새로고침 후 다시 해 주세요.')
        except requests.RequestException:
            raise RuntimeError('온라인 저장에 실패했어요. 연결과 저장소 설정을 확인해 주세요.')
    else:
        with sqlite3.connect('study_accounts.sqlite3',timeout=15) as db:
            db.execute('create table if not exists state (id text primary key,payload text,version integer)')
            if data is None:
                row=db.execute('select payload,version from state where id=?',(key,)).fetchone()
                return (json.loads(row[0]),row[1]) if row else (None,None)
            if version is None:
                db.execute('insert into state values (?,?,0)',(key,json.dumps(data)))
            else:
                c=db.execute('update state set payload=?,version=? where id=? and version=?',(json.dumps(data),version+1,key,version))
                if not c.rowcount:
                    raise RuntimeError('다른 가족이 수정했어요. 새로고침 후 다시 해 주세요.')

def password_hash(password,salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),260000).hex()
def recovery_id(code):
    return 'recovery_'+hashlib.sha256(code.strip().upper().encode()).hexdigest()

def commit(data,version):
    store(st.session_state.uid,data,version)
    st.rerun()

def schedule(g):
    done=int(g['done'])
    remaining=max(0,g['total']-done)
    days=[]
    start=max(TODAY,date.fromisoformat(g['start']))
    end=date.fromisoformat(g['end'])
    for i in range(max(0,(end-start).days+1)):
        d=start+timedelta(days=i)
        if d.weekday() in g['days']:
            days.append(d)
    if not days:
        return {},remaining
    q,r=divmod(remaining,len(days))
    return {d.isoformat():q+(i<r) for i,d in enumerate(days)},remaining

def goal_form(data,version,kind,old=None):
    unit='쪽' if kind=='책' else '강'
    with st.form('goal_'+kind):
        name=st.text_input('책 제목' if kind=='책' else '강의 이름',value=old['name'] if old else '',max_chars=70)
        total=st.number_input('마지막 페이지' if kind=='책' else '전체 강의 수',1,100000,value=old['total'] if old else (200 if kind=='책' else 30))
        done=st.number_input('현재 읽은 페이지' if kind=='책' else '현재 완료한 강의 번호',0,100000,value=old['done'] if old else 0)
        end=st.date_input('완료 목표일',value=date.fromisoformat(old['end']) if old else TODAY+timedelta(days=14))
        days=st.multiselect('공부 요일',WEEK,default=[WEEK[i] for i in old['days']] if old else WEEK[:5])
        if st.form_submit_button('계획 저장',use_container_width=True):
            if not name.strip() or done>total or end<TODAY or not days:
                st.error('제목·분량·날짜·공부 요일을 확인해 주세요.')
            else:
                g={'id':old['id'] if old else secrets.token_hex(8),'kind':kind,'name':name.strip(),'total':total,'done':done,'start':old['start'] if old else str(TODAY),'end':str(end),'days':[WEEK.index(x) for x in days],'history':old.get('history',[]) if old else []}
                plan,remaining=schedule(g)
                if remaining and not plan:
                    st.error('기간 안에 공부일이 없어요.')
                else:
                    if old:
                        data['goals']=[g if x['id']==g['id'] else x for x in data['goals']]
                    else:
                        data['goals'].append(g)
                    commit(data,version)

st.markdown('''<style>
.block-container{max-width:540px;padding:1rem 1rem 2rem!important;}
h1{font-size:1.65rem!important;}h3{font-size:1.15rem!important;}
[data-testid="stVerticalBlock"]{gap:.65rem;}
input,textarea,[data-baseweb="input"],[data-baseweb="base-input"],[data-baseweb="select"]>div{background:#fff!important;color:#202D45!important;-webkit-text-fill-color:#202D45!important;color-scheme:light!important;}
[role="dialog"],[data-baseweb="calendar"],[role="listbox"]{background:white!important;color:#202D45!important;}
button{border-radius:12px!important;}[data-testid="stForm"]{background:white;border-radius:16px;}
</style>''',unsafe_allow_html=True)
st.title('끝까지 🌱')
try:
    if 'uid' not in st.session_state:
        st.write('책과 인강, 계획부터 완주까지')
        page=st.radio('계정 메뉴',['로그인','회원가입','계정 찾기'],horizontal=True,label_visibility='collapsed')
        if 'new_recovery' in st.session_state:
            st.success('가입했어요. 아래 복구 코드를 개인적으로 보관한 뒤 로그인하세요.')
            st.code(st.session_state.new_recovery,language=None)
            st.caption('코드를 아는 사람은 계정 비밀번호를 바꿀 수 있어요. 공유하지 마세요.')
        if page in ['로그인','회원가입']:
            with st.form('auth'):
                username=st.text_input('아이디',max_chars=30,placeholder='영문·숫자·밑줄 3자 이상').strip().lower()
                password=st.text_input('비밀번호',type='password')
                confirm=st.text_input('비밀번호 확인',type='password') if page=='회원가입' else password
                submitted=st.form_submit_button(page,use_container_width=True)
            if submitted:
                legal=len(username)>=3 and all(c.isascii() and (c.isalnum() or c=='_') for c in username)
                if not legal or len(password)<8 or password!=confirm:
                    st.error('아이디 형식과 비밀번호(8자 이상)를 확인해 주세요.')
                else:
                    uid='user_'+hashlib.sha256(username.encode()).hexdigest()
                    data,ver=store(uid)
                    if page=='회원가입':
                        if data:
                            st.error('이미 사용 중인 아이디예요.')
                        else:
                            salt=secrets.token_hex(16)
                            recovery=secrets.token_hex(16).upper()
                            data={'username':username,'salt':salt,'hash':password_hash(password,salt),'goals':[],'tasks':[],'sessions':[]}
                            store(recovery_id(recovery),{'uid':uid})
                            store(uid,data)
                            st.session_state.new_recovery=recovery
                            st.rerun()
                    elif data and secrets.compare_digest(data['hash'],password_hash(password,data['salt'])):
                        st.session_state.uid=uid
                        st.session_state.pop('new_recovery',None)
                        st.rerun()
                    else:
                        st.error('아이디 또는 비밀번호를 확인해 주세요.')
        else:
            with st.form('recovery'):
                code=st.text_input('가입할 때 받은 복구 코드',type='password')
                newpw=st.text_input('새 비밀번호 (변경할 때만 입력)',type='password')
                find=st.form_submit_button('아이디 확인 / 비밀번호 재설정',use_container_width=True)
            if find:
                entry,_=store(recovery_id(code))
                if not entry:
                    st.error('복구 코드를 확인해 주세요.')
                else:
                    account,ver=store(entry['uid'])
                    if not account:
                        st.error('계정을 찾을 수 없어요.')
                    else:
                        st.success('아이디: '+account['username'])
                        if newpw:
                            if len(newpw)<8:
                                st.error('비밀번호는 8자 이상이어야 해요.')
                            else:
                                account['salt']=secrets.token_hex(16)
                                account['hash']=password_hash(newpw,account['salt'])
                                store(entry['uid'],account,ver)
                                st.success('변경했어요. 로그인 메뉴에서 접속하세요.')
            st.caption('이메일 없이 복구 코드를 사용해요. 코드까지 잃으면 복구할 수 없어요.')
        if not cloud():
            st.caption('체험 저장 · 서버 초기화 시 기록이 사라질 수 있어요.')
        st.stop()

    data,version=store(st.session_state.uid)
    if not data:
        st.session_state.clear()
        st.rerun()
    menu=st.radio('메뉴',['오늘','내 학습','집중','기록'],horizontal=True,label_visibility='collapsed')
    if menu=='오늘':
        st.subheader(TODAY.strftime('%m월 %d일')+' · 오늘의 공부')
        active=[g for g in data['goals'] if g['done']<g['total']]
        if not active:
            st.info('내 학습에서 책이나 인강을 등록해 보세요.')
        for g in active:
            plan,remaining=schedule(g)
            amount=plan.get(str(TODAY),0)
            unit='쪽' if g['kind']=='책' else '강'
            with st.container(border=True):
                st.write(('📖 ' if g['kind']=='책' else '🎧 ')+g['name'])
                # 하루의 기준 분량은 그날 첫 기록 전 진도를 복원하여 계산.
                baseline=dict(g)
                today_delta=sum(x['delta'] for x in g.get('history',[]) if x['day']==str(TODAY))
                baseline['done']=max(0,g['done']-today_delta)
                original,_=schedule(baseline)
                left=max(0,original.get(str(TODAY),0)-today_delta)
                if not plan:
                    st.caption('완료일 또는 공부 요일을 수정해 주세요.')
                elif str(TODAY) not in plan:
                    st.caption('오늘은 쉬는 날이에요.')
                elif left:
                    end=min(g['total'],g['done']+left)
                    st.subheader(f"{g['done']+1}~{end}{unit}")
                else:
                    st.caption('오늘 목표 달성 ✓')
                st.progress(g['done']/g['total'],text=f"{g['done']} / {g['total']}{unit}")
                with st.form('progress_'+g['id']):
                    actual=st.number_input('지금까지 읽은 페이지' if g['kind']=='책' else '지금까지 완료한 강의 번호',0,g['total'],value=g['done'])
                    if st.form_submit_button('진도 저장',use_container_width=True):
                        g['history'].append({'day':str(TODAY),'delta':actual-g['done']})
                        g['done']=actual
                        commit(data,version)
        with st.expander('오늘 할 일 추가'):
            with st.form('task'):
                task=st.text_input('할 일',placeholder='예: 영어 단어 복습',max_chars=100)
                if st.form_submit_button('추가') and task.strip():
                    data['tasks'].append({'id':secrets.token_hex(6),'day':str(TODAY),'name':task.strip(),'done':False})
                    commit(data,version)
        for t in data['tasks']:
            if t['day']==str(TODAY):
                checked=st.checkbox(t['name'],value=t['done'],key=t['id'])
                if checked!=t['done']:
                    t['done']=checked
                    commit(data,version)
    elif menu=='내 학습':
        kind=st.radio('학습 종류',['책','인강'],horizontal=True)
        goals=[g for g in data['goals'] if g['kind']==kind]
        @st.dialog('학습 계획')
        def editor(old=None):
            goal_form(data,version,kind,old)
        if st.button('＋ '+('책 등록' if kind=='책' else '인강 등록'),type='primary',use_container_width=True):
            editor()
        for g in goals:
            with st.container(border=True):
                st.write(g['name'])
                unit='쪽' if kind=='책' else '강'
                st.progress(g['done']/g['total'],text=f"{g['done']} / {g['total']}{unit} · {g['end']}까지")
                if st.button('학습 계획 수정',key='edit_'+g['id']):
                    editor(g)
    elif menu=='집중':
        st.subheader('한 번에 한 가지에 집중해요')
        timer=st.session_state.get('timer')
        if not timer:
            c1,c2=st.columns(2)
            minutes=c1.number_input('집중 (분)',1,180,25)
            rest=c2.number_input('휴식 (분)',1,60,5)
            if st.button('집중 시작',type='primary',use_container_width=True):
                st.session_state.timer={'end':clock.time()+minutes*60,'minutes':minutes,'rest':rest,'phase':'집중','id':secrets.token_hex(8)}
                st.rerun()
        else:
            @st.fragment(run_every=1)
            def countdown():
                left=max(0,int(timer['end']-clock.time()))
                st.metric(timer['phase'],f'{left//60:02d}:{left%60:02d}')
                if left==0:
                    st.success('시간이 끝났어요!')
                    if not timer.get('notified'):
                        timer['notified']=True
                        st.rerun(scope='app')
            countdown()
            if st.button('중단',use_container_width=True):
                st.session_state.pop('timer',None)
                st.rerun()
            if clock.time()>=timer['end']:
                if st.button('집중 기록 저장 · 휴식 시작' if timer['phase']=='집중' else '휴식 마치기',type='primary'):
                    if timer['phase']=='집중':
                        if not any(x['id']==timer['id'] for x in data['sessions']):
                            data['sessions'].append({'id':timer['id'],'day':str(TODAY),'minutes':timer['minutes']})
                            store(st.session_state.uid,data,version)
                        st.session_state.timer={'end':clock.time()+timer['rest']*60,'phase':'휴식','rest':timer['rest'],'minutes':0,'id':secrets.token_hex(8)}
                    else:
                        st.session_state.pop('timer',None)
                    st.rerun()
            else:
                st.caption('완료 버튼이 안 보이면 아래 버튼을 눌러 주세요.')
                if st.button('완료 상태 확인'):
                    st.rerun()
        st.caption('새로고침·로그아웃하면 진행 중 타이머가 초기화될 수 있어요.')
    else:
        st.subheader('이번 주 공부 기록')
        monday=TODAY-timedelta(days=TODAY.weekday())
        sessions=[x for x in data['sessions'] if str(monday)<=x['day']<=str(TODAY)]
        minutes=sum(x['minutes'] for x in sessions)
        tasks=[x for x in data['tasks'] if str(monday)<=x['day']<=str(TODAY)]
        a,b=st.columns(2)
        a.metric('집중 시간',f'{minutes}분')
        b.metric('할 일 완료',f"{sum(t['done'] for t in tasks)} / {len(tasks)}")
        st.caption('집중 시간은 타이머를 완료하고 저장한 기록만 포함해요.')
        for i in range((TODAY-monday).days+1):
            d=str(monday+timedelta(days=i))
            mins=sum(x['minutes'] for x in sessions if x['day']==d)
            st.write(f'{d[5:]} · 집중 {mins}분')
        with st.expander('설정'):
            if not cloud():
                st.warning('체험 저장 중 · 영구 보관하려면 파일 상단의 온라인 저장 설정을 적용하세요.')
            st.caption('복구 코드는 안전하게 보관하세요. 비밀번호나 코드를 공유하지 마세요.')
            if st.button('로그아웃'):
                st.session_state.clear()
                st.rerun()
except (RuntimeError,sqlite3.Error) as exc:
    st.error(str(exc) if isinstance(exc,RuntimeError) else '저장에 실패했어요. 다시 시도해 주세요.')
