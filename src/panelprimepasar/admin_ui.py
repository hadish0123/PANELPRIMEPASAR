# ruff: noqa: E501
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(prefix="/admin", include_in_schema=False)

_ADMIN_HTML = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PANELPRIMEPASAR Admin</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#121a2d;--line:#25304a;--text:#f2f6ff;--muted:#9aa9c3;--accent:#66e3b4;--danger:#ff6b7a}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text)}
header{position:sticky;top:0;background:#0d1426;border-bottom:1px solid var(--line);padding:14px 20px;z-index:2}
.shell{display:grid;grid-template-columns:220px 1fr;min-height:100vh}.side{border-left:1px solid var(--line);padding:18px;background:#0d1426}
main{padding:24px;min-width:0}.nav button,.btn{width:100%;margin:5px 0;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--panel);color:var(--text);cursor:pointer;text-align:right}
.nav button:hover,.btn:hover{border-color:var(--accent)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}.metric{font-size:24px;font-weight:700;margin-top:8px}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th{color:var(--muted)}
.table-wrap{overflow:auto}.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
input,select{background:#0d1426;color:var(--text);border:1px solid var(--line);border-radius:9px;padding:9px}
.small{width:auto!important}.danger{border-color:#6a2d37!important;color:#ffc5cb!important}.ok{color:var(--accent)}.muted{color:var(--muted)}
#login{max-width:460px;margin:12vh auto}.hidden{display:none!important}h1,h2{margin-top:0}
@media(max-width:800px){.shell{grid-template-columns:1fr}.side{border-left:0;border-bottom:1px solid var(--line)}.nav{display:flex;gap:6px;overflow:auto}.nav button{min-width:130px}}
</style>
</head>
<body>
<section id="login" class="card">
<h1>ورود مدیریت</h1>
<p class="muted">کلید مدیریت را وارد کنید. کلید فقط در Session مرورگر نگه‌داری می‌شود.</p>
<input id="key" type="password" placeholder="ADMIN_PANEL_API_KEY" style="width:100%">
<button class="btn" onclick="login()">ورود</button>
<div id="loginError" style="color:var(--danger)"></div>
</section>
<section id="app" class="hidden">
<div class="shell">
<aside class="side">
<h2>PANELPRIMEPASAR</h2>
<div class="nav">
<button onclick="show('dashboard')">📊 داشبورد</button>
<button onclick="show('customers')">👥 مشتریان</button>
<button onclick="show('plans')">📦 پلن‌ها</button>
<button onclick="show('orders')">🧾 سفارش‌ها</button>
<button onclick="show('payments')">💳 پرداخت‌ها</button>
<button onclick="show('subscriptions')">🔄 سرویس‌ها</button>
<button onclick="show('support')">🎧 پشتیبانی</button>
<button onclick="show('staff')">👮 مدیران</button>
<button onclick="show('audit')">📜 لاگ‌ها</button>
<button class="danger" onclick="logout()">خروج</button>
</div>
</aside>
<main>
<header><span id="status" class="muted">آماده</span></header>
<div id="view"></div>
</main>
</div>
</section>
<script>
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function key(){return sessionStorage.getItem('adminKey')||''}
async function api(path,opts={}){
  const headers={...(opts.headers||{}),'X-Admin-Key':key()};
  if(opts.body && !headers['Content-Type']) headers['Content-Type']='application/json';
  const r=await fetch(path,{...opts,headers});
  if(r.status===401){logout();throw new Error('دسترسی نامعتبر')}
  if(!r.ok){let m='HTTP '+r.status;try{m=(await r.json()).detail||m}catch{}throw new Error(m)}
  return r.status===204?null:r.json()
}
async function login(){
  sessionStorage.setItem('adminKey',$('#key').value);
  try{await api('/admin/dashboard');$('#login').classList.add('hidden');$('#app').classList.remove('hidden');show('dashboard')}
  catch(e){sessionStorage.removeItem('adminKey');$('#loginError').textContent=e.message}
}
function logout(){sessionStorage.removeItem('adminKey');location.reload()}
function table(rows,cols){
  if(!rows.length)return '<p class="muted">داده‌ای وجود ندارد.</p>';
  return '<div class="table-wrap"><table><thead><tr>'+cols.map(c=>'<th>'+esc(c[0])+'</th>').join('')+'</tr></thead><tbody>'+
  rows.map(r=>'<tr>'+cols.map(c=>'<td>'+c[1](r)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>'
}
async function show(name){
  $('#status').textContent='در حال بارگذاری...';
  try{await views[name]();$('#status').textContent='به‌روز'}catch(e){$('#view').innerHTML='<div class="card" style="color:var(--danger)">'+esc(e.message)+'</div>';$('#status').textContent='خطا'}
}
const views={
 dashboard:async()=>{
  const d=await api('/admin/dashboard');
  const items=[['کاربران',d.customers],['سرویس فعال',d.active_services],['سفارش در جریان',d.pending_orders],['پرداخت موفق',d.verified_payments],['درآمد تاییدشده',Number(d.verified_revenue).toLocaleString()+' IRT'],['تیکت باز',d.open_tickets],['اکانت پاسارگارد',d.pasarguard_accounts],['پلن‌ها',d.plans]];
  $('#view').innerHTML='<h1>داشبورد</h1><div class="grid">'+items.map(x=>'<div class="card"><div class="muted">'+esc(x[0])+'</div><div class="metric">'+esc(x[1])+'</div></div>').join('')+'</div>'
 },
 customers:async()=>{
  const rows=await api('/admin/customers?limit=100');
  $('#view').innerHTML='<h1>مشتریان</h1>'+table(rows,[['Telegram',r=>'<code>'+esc(r.telegram_user_id)+'</code>'],['Username',r=>esc(r.username)],['نام',r=>esc((r.first_name||'')+' '+(r.last_name||''))],['وضعیت',r=>r.blocked?'🚫 مسدود':'✅ فعال'],['عملیات',r=>'<button class="btn small '+(r.blocked?'':'danger')+'" onclick="blockCustomer(\''+r.id+'\','+(!r.blocked)+')">'+(r.blocked?'رفع مسدودی':'مسدود')+'</button>']])
 },
 plans:async()=>{
  const rows=await api('/admin/plans');
  $('#view').innerHTML='<h1>پلن‌ها</h1><div class="card"><div class="toolbar"><input id="pname" placeholder="نام"><input id="pquota" type="number" placeholder="حجم بایت"><input id="pprice" type="number" placeholder="قیمت تومان"><input id="pdays" type="number" placeholder="روز"><button class="btn small" onclick="createPlan()">➕ ساخت</button></div></div>'+table(rows,[['نام',r=>esc(r.name)],['حجم',r=>Number(r.quota_bytes).toLocaleString()],['قیمت',r=>Number(r.price_amount).toLocaleString()+' '+esc(r.currency)],['اعتبار',r=>esc(r.validity_days??'∞')],['وضعیت',r=>r.active?'✅':'⛔'],['عملیات',r=>'<button class="btn small" onclick="togglePlan(\''+r.id+'\','+(!r.active)+')">'+(r.active?'غیرفعال':'فعال')+'</button>']])
 },
 orders:async()=>{const rows=await api('/admin/orders?limit=100');$('#view').innerHTML='<h1>سفارش‌ها</h1>'+table(rows,[['ID',r=>'<code>'+esc(r.id.slice(0,8))+'</code>'],['نوع',r=>esc(r.kind)],['وضعیت',r=>esc(r.status)],['مبلغ',r=>Number(r.amount).toLocaleString()+' '+esc(r.currency)],['حجم',r=>Number(r.quota_bytes).toLocaleString()]])},
 payments:async()=>{const rows=await api('/admin/payments?limit=100');$('#view').innerHTML='<h1>پرداخت‌ها</h1>'+table(rows,[['ID',r=>'<code>'+esc(r.id.slice(0,8))+'</code>'],['درگاه',r=>esc(r.provider)],['مبلغ',r=>Number(r.amount).toLocaleString()+' '+esc(r.currency)],['وضعیت',r=>esc(r.status)],['تراکنش',r=>esc(r.transaction_id)]])},
 subscriptions:async()=>{const rows=await api('/admin/subscriptions?limit=100');$('#view').innerHTML='<h1>سرویس‌ها</h1>'+table(rows,[['ID',r=>'<code>'+esc(r.id.slice(0,8))+'</code>'],['وضعیت',r=>esc(r.status)],['حجم',r=>Number(r.quota_bytes).toLocaleString()],['انقضا',r=>esc(r.expires_at||'∞')],['Auto Renew',r=>r.auto_renew?'✅':'—']])},
 support:async()=>{const rows=await api('/admin/support?limit=100');$('#view').innerHTML='<h1>پشتیبانی</h1>'+table(rows,[['ID',r=>'<code>'+esc(r.id.slice(0,8))+'</code>'],['موضوع',r=>esc(r.subject)],['وضعیت',r=>esc(r.status)],['به‌روزرسانی',r=>esc(r.updated_at)]])},
 staff:async()=>{const rows=await api('/admin/staff');$('#view').innerHTML='<h1>مدیران</h1>'+table(rows,[['Telegram',r=>esc(r.telegram_user_id)],['Username',r=>esc(r.username)],['نقش',r=>esc(r.role)],['وضعیت',r=>r.active?'✅':'⛔'],['عملیات',r=>'<button class="btn small" onclick="staffStatus(\''+r.id+'\','+(!r.active)+')">'+(r.active?'غیرفعال':'فعال')+'</button>']])},
 audit:async()=>{const rows=await api('/admin/audit?limit=100');$('#view').innerHTML='<h1>Audit Log</h1>'+table(rows,[['زمان',r=>esc(r.created_at)],['Actor',r=>esc(r.actor_type)+' '+esc(r.actor_id)],['عملیات',r=>esc(r.action)],['Entity',r=>esc(r.entity_type)+' '+esc(r.entity_id)]])}
};
async function blockCustomer(id,blocked){await api('/admin/customers/'+id+'/block',{method:'PATCH',body:JSON.stringify({blocked})});show('customers')}
async function togglePlan(id,active){await api('/admin/plans/'+id,{method:'PATCH',body:JSON.stringify({is_active:active})});show('plans')}
async function createPlan(){
 const body={name:$('#pname').value,quota_bytes:Number($('#pquota').value),price_amount:Number($('#pprice').value),currency:'IRT',validity_days:$('#pdays').value?Number($('#pdays').value):null};
 await api('/admin/plans',{method:'POST',body:JSON.stringify(body)});show('plans')
}
async function staffStatus(id,active){await api('/admin/staff/'+id+'/status',{method:'PATCH',body:JSON.stringify({active})});show('staff')}
if(key()){api('/admin/dashboard').then(()=>{$('#login').classList.add('hidden');$('#app').classList.remove('hidden');show('dashboard')}).catch(()=>sessionStorage.removeItem('adminKey'))}
</script>
</body>
</html>"""


@router.get("", response_class=RedirectResponse)
async def admin_root() -> RedirectResponse:
    return RedirectResponse(url="/admin/ui", status_code=307)


@router.get("/ui", response_class=HTMLResponse)
async def admin_ui() -> HTMLResponse:
    response = HTMLResponse(_ADMIN_HTML)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
