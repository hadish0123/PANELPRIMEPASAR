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
:root{
  color-scheme:dark;
  --bg:#07090f;
  --bg-soft:#0a0d14;
  --panel:#10141d;
  --panel-2:#141a25;
  --panel-3:#191f2b;
  --line:#252c3a;
  --line-soft:#1b2230;
  --text:#f7f3e8;
  --text-soft:#d8d1bf;
  --muted:#8d95a5;
  --gold:#d6b46f;
  --gold-strong:#f0cf8e;
  --gold-dim:#8f7442;
  --blue:#5b8cff;
  --success:#5dc69a;
  --danger:#ef7b83;
  --warning:#e5b763;
  --shadow:0 24px 80px rgba(0,0,0,.42);
  --shadow-soft:0 12px 34px rgba(0,0,0,.28);
  --radius:18px;
  --radius-sm:12px;
}
*{box-sizing:border-box}
html{background:var(--bg);scroll-behavior:smooth}
body{
  margin:0;
  min-height:100vh;
  font-family:Tahoma,"Segoe UI",system-ui,-apple-system,sans-serif;
  background:
    radial-gradient(circle at 88% 2%,rgba(214,180,111,.13),transparent 26%),
    radial-gradient(circle at 12% 92%,rgba(91,140,255,.07),transparent 28%),
    linear-gradient(180deg,#080b12 0%,#06080d 100%);
  color:var(--text);
  letter-spacing:-.01em;
}
button,input,select{font:inherit}
button{user-select:none}
a{color:inherit}
.hidden{display:none!important}
.muted{color:var(--muted)}
.ok{color:var(--success)}
.danger{color:#ffd2d5!important;border-color:rgba(239,123,131,.32)!important}
.small{width:auto!important;display:inline-flex!important;align-items:center;justify-content:center;gap:7px}
code{
  direction:ltr;
  unicode-bidi:plaintext;
  color:#f4d99d;
  background:rgba(214,180,111,.08);
  border:1px solid rgba(214,180,111,.14);
  padding:4px 7px;
  border-radius:8px;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:.88em;
}
h1,h2,h3{margin:0;color:var(--text);font-weight:700}
h1{font-size:28px;letter-spacing:-.04em}
h2{font-size:18px}
p{line-height:1.9}

/* Login */
#login{
  width:min(960px,calc(100% - 36px));
  min-height:560px;
  margin:7vh auto;
  display:grid;
  grid-template-columns:minmax(0,1.02fr) minmax(320px,.98fr);
  padding:0;
  overflow:hidden;
  border-radius:28px;
  border:1px solid rgba(214,180,111,.18);
  background:rgba(14,18,27,.94);
  box-shadow:var(--shadow);
  position:relative;
}
#login:before{
  content:"";
  position:absolute;
  inset:0;
  pointer-events:none;
  background:linear-gradient(135deg,rgba(255,255,255,.018),transparent 38%,rgba(214,180,111,.025));
}
.login-visual{
  padding:54px 48px;
  background:
    linear-gradient(145deg,rgba(214,180,111,.12),rgba(214,180,111,.015) 48%),
    linear-gradient(180deg,#151922,#0e121a);
  border-left:1px solid rgba(214,180,111,.15);
  display:flex;
  flex-direction:column;
  justify-content:space-between;
  min-height:560px;
}
.login-form{padding:54px 48px;display:flex;flex-direction:column;justify-content:center}
.login-eyebrow,.section-eyebrow{
  color:var(--gold);
  font-size:11px;
  letter-spacing:.22em;
  text-transform:uppercase;
  font-weight:700;
}
.brand-lockup{display:flex;align-items:center;gap:14px}
.brand-mark{
  width:50px;height:50px;border-radius:15px;
  display:grid;place-items:center;
  background:linear-gradient(145deg,#f1d494,#9b793d);
  color:#11151d;font-weight:900;font-size:18px;
  box-shadow:0 12px 30px rgba(214,180,111,.2);
  border:1px solid rgba(255,255,255,.26);
}
.brand-title{font-weight:800;font-size:19px;letter-spacing:.02em}
.brand-sub{color:var(--muted);font-size:12px;margin-top:3px}
.lux-line{height:1px;background:linear-gradient(90deg,transparent,var(--gold-dim),transparent);margin:28px 0}
.login-visual h2{font-size:34px;line-height:1.55;max-width:440px;letter-spacing:-.04em}
.login-visual p{color:var(--text-soft);max-width:470px;font-size:14px}
.security-note{
  display:flex;gap:12px;align-items:flex-start;
  padding:14px 15px;border-radius:14px;
  border:1px solid rgba(214,180,111,.13);
  background:rgba(5,7,11,.28);
  color:var(--muted);font-size:12px;line-height:1.8;
}
.security-dot{width:8px;height:8px;border-radius:50%;background:var(--success);margin-top:6px;box-shadow:0 0 0 5px rgba(93,198,154,.08)}
.login-form h1{font-size:31px;margin-top:10px}
.login-form .lead{color:var(--muted);font-size:13px;margin:10px 0 26px}
.field-group{display:grid;gap:13px}
.field{display:grid;gap:7px}
.field label{font-size:12px;color:var(--text-soft);font-weight:700}
.divider{display:flex;align-items:center;gap:12px;color:#697180;font-size:11px;margin:18px 0}
.divider:before,.divider:after{content:"";height:1px;flex:1;background:var(--line-soft)}
#loginError{margin-top:12px;color:var(--danger);font-size:12px;min-height:18px}

/* App shell */
.shell{
  display:grid;
  grid-template-columns:278px minmax(0,1fr);
  min-height:100vh;
}
.side{
  position:sticky;
  top:0;
  height:100vh;
  padding:24px 18px 18px;
  border-left:1px solid rgba(214,180,111,.11);
  background:
    linear-gradient(180deg,rgba(16,20,29,.98),rgba(9,12,18,.99)),
    radial-gradient(circle at top right,rgba(214,180,111,.08),transparent 32%);
  box-shadow:12px 0 50px rgba(0,0,0,.22);
  z-index:20;
  overflow:auto;
}
.side-head{padding:2px 8px 20px;border-bottom:1px solid var(--line-soft);margin-bottom:14px}
.side-meta{display:flex;align-items:center;justify-content:space-between;margin-top:14px}
.role-badge{
  padding:5px 9px;border-radius:999px;
  color:var(--gold-strong);
  background:rgba(214,180,111,.08);
  border:1px solid rgba(214,180,111,.16);
  font-size:10px;font-weight:700;letter-spacing:.08em;
}
.env-dot{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:10px}
.env-dot:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--success);box-shadow:0 0 0 4px rgba(93,198,154,.08)}
.nav{display:grid;gap:4px}
.nav-label{
  color:#616a79;font-size:10px;font-weight:800;letter-spacing:.15em;
  padding:13px 11px 7px;text-transform:uppercase;
}
.nav button{
  width:100%;
  min-height:43px;
  margin:0;
  padding:10px 12px;
  border:1px solid transparent;
  border-radius:11px;
  background:transparent;
  color:#aeb6c3;
  cursor:pointer;
  text-align:right;
  transition:.18s ease;
  display:flex;
  align-items:center;
  gap:10px;
  position:relative;
}
.nav button:hover{
  background:rgba(255,255,255,.028);
  color:var(--text);
  border-color:rgba(255,255,255,.04);
  transform:translateX(-1px);
}
.nav button.active{
  color:var(--gold-strong);
  background:linear-gradient(90deg,rgba(214,180,111,.13),rgba(214,180,111,.045));
  border-color:rgba(214,180,111,.14);
}
.nav button.active:after{
  content:"";
  position:absolute;
  right:-19px;
  width:3px;height:22px;border-radius:99px;
  background:linear-gradient(180deg,var(--gold-strong),var(--gold-dim));
  box-shadow:0 0 14px rgba(214,180,111,.38);
}
.nav-icon{
  width:26px;height:26px;display:grid;place-items:center;flex:0 0 auto;
  border-radius:8px;background:rgba(255,255,255,.035);
  color:#8993a4;font-size:13px;
}
.nav button.active .nav-icon{background:rgba(214,180,111,.12);color:var(--gold-strong)}
.side-footer{margin-top:18px;padding-top:14px;border-top:1px solid var(--line-soft)}

main{min-width:0;padding:0 30px 34px}
header{
  position:sticky;top:0;z-index:15;
  height:78px;
  display:flex;align-items:center;justify-content:space-between;
  padding:0 4px;
  background:linear-gradient(180deg,rgba(7,9,15,.96),rgba(7,9,15,.82));
  backdrop-filter:blur(18px);
  border-bottom:1px solid rgba(255,255,255,.035);
}
.header-title-wrap{display:flex;align-items:center;gap:12px}
.header-kicker{font-size:10px;letter-spacing:.15em;color:var(--gold);font-weight:800}
#pageTitle{font-size:19px;font-weight:800;margin-top:2px}
.header-actions{display:flex;align-items:center;gap:10px}
.status-pill{
  display:flex;align-items:center;gap:8px;
  padding:8px 11px;border-radius:999px;
  border:1px solid var(--line);
  background:rgba(16,20,29,.7);
  color:var(--muted);font-size:11px;
}
.status-pill:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--success)}
#view{padding-top:28px;animation:fadeIn .22s ease}
@keyframes fadeIn{from{opacity:.3;transform:translateY(4px)}to{opacity:1;transform:none}}

/* Content */
.page-head{display:flex;align-items:end;justify-content:space-between;gap:16px;margin-bottom:18px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.card{
  background:
    linear-gradient(180deg,rgba(20,25,36,.92),rgba(14,18,27,.94));
  border:1px solid rgba(255,255,255,.055);
  border-radius:var(--radius);
  padding:18px;
  box-shadow:var(--shadow-soft);
  position:relative;
  overflow:hidden;
}
.card:after{
  content:"";
  position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(140deg,rgba(255,255,255,.025),transparent 35%);
}
.grid .card{
  min-height:128px;
  display:flex;flex-direction:column;justify-content:space-between;
  border-color:rgba(214,180,111,.08);
}
.grid .card:before{
  content:"";position:absolute;left:0;top:0;width:58px;height:2px;
  background:linear-gradient(90deg,var(--gold),transparent);
}
.metric{font-size:27px;font-weight:800;color:var(--text);margin-top:16px;letter-spacing:-.035em}
.toolbar{
  display:flex;align-items:center;gap:9px;flex-wrap:wrap;
  margin:14px 0 0;
}
input,select{
  min-height:42px;
  background:#0b0f16;
  color:var(--text);
  border:1px solid #252c39;
  border-radius:10px;
  padding:9px 11px;
  outline:none;
  transition:.18s ease;
}
input::placeholder{color:#555f6f}
input:focus,select:focus{
  border-color:rgba(214,180,111,.62);
  box-shadow:0 0 0 3px rgba(214,180,111,.08);
  background:#0d1119;
}
input[type="checkbox"]{min-height:auto;accent-color:var(--gold);transform:translateY(1px)}
label{color:var(--text-soft);font-size:12px}
.btn{
  min-height:40px;
  width:100%;
  margin:5px 0;
  padding:9px 13px;
  border:1px solid rgba(214,180,111,.22);
  border-radius:10px;
  background:linear-gradient(180deg,rgba(214,180,111,.13),rgba(214,180,111,.07));
  color:var(--gold-strong);
  cursor:pointer;
  text-align:center;
  font-weight:700;
  font-size:12px;
  transition:.17s ease;
}
.btn:hover{
  transform:translateY(-1px);
  border-color:rgba(214,180,111,.42);
  background:linear-gradient(180deg,rgba(214,180,111,.2),rgba(214,180,111,.1));
  box-shadow:0 8px 22px rgba(0,0,0,.18);
}
.btn.danger,.nav .danger{
  color:#f6a9af!important;
  background:rgba(239,123,131,.055);
  border-color:rgba(239,123,131,.15)!important;
}
.btn.danger:hover,.nav .danger:hover{background:rgba(239,123,131,.1)!important}
.table-wrap{
  width:100%;
  overflow:auto;
  border-radius:var(--radius);
  border:1px solid rgba(255,255,255,.055);
  background:#0e121a;
  box-shadow:var(--shadow-soft);
}
table{width:100%;border-collapse:separate;border-spacing:0;min-width:760px}
th,td{
  padding:13px 15px;
  text-align:right;
  white-space:nowrap;
  border-bottom:1px solid #1b2230;
  font-size:12px;
}
th{
  color:#7f8999;
  background:#111722;
  font-size:10px;
  font-weight:800;
  letter-spacing:.07em;
  text-transform:uppercase;
}
tbody tr{transition:.15s ease}
tbody tr:hover{background:rgba(214,180,111,.025)}
tbody tr:last-child td{border-bottom:0}
td{color:#d7dde7}
.empty-state{
  border:1px dashed #2a3140;
  background:rgba(16,20,29,.55);
  border-radius:var(--radius);
  padding:34px;text-align:center;color:var(--muted);
}

/* Scrollbars */
*{scrollbar-width:thin;scrollbar-color:#343c4c #0a0d13}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-track{background:#0a0d13}
::-webkit-scrollbar-thumb{background:#343c4c;border-radius:20px}

/* Responsive */
@media(max-width:1180px){
  .grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .shell{grid-template-columns:244px minmax(0,1fr)}
}
@media(max-width:860px){
  #login{grid-template-columns:1fr;margin:24px auto}
  .login-visual{display:none}
  .login-form{padding:36px 28px}
  .shell{grid-template-columns:1fr}
  .side{position:relative;height:auto;border-left:0;border-bottom:1px solid rgba(214,180,111,.11);padding:14px}
  .side-head{padding-bottom:12px}
  .nav{display:flex;overflow:auto;gap:6px;padding-bottom:4px}
  .nav-label,.side-footer{display:none}
  .nav button{min-width:max-content;width:auto;padding:8px 11px}
  .nav button.active:after{display:none}
  main{padding:0 16px 28px}
  header{height:64px}
}
@media(max-width:560px){
  .grid{grid-template-columns:1fr}
  .login-form{padding:30px 22px}
  .login-form h1{font-size:26px}
  header{align-items:center}
  .header-kicker{display:none}
  #pageTitle{font-size:16px}
  .status-pill{padding:7px 9px}
}
</style>
</head>
<body>
<section id="login">
  <div class="login-visual">
    <div>
      <div class="brand-lockup">
        <div class="brand-mark">PP</div>
        <div>
          <div class="brand-title">PANELPRIMEPASAR</div>
          <div class="brand-sub">Executive Control Center</div>
        </div>
      </div>
      <div class="lux-line"></div>
      <div class="login-eyebrow">Premium Administration</div>
      <h2>کنترل حرفه‌ای فروش، پرداخت و زیرساخت از یک مرکز فرماندهی.</h2>
      <p>داشبورد مدیریتی رسمی برای مدیریت مشتریان، سفارش‌ها، درگاه‌ها، سرویس‌ها و زیرساخت PasarGuard.</p>
    </div>
    <div class="security-note">
      <span class="security-dot"></span>
      <div>ورود امن با نشست امضاشده و سطح دسترسی مبتنی بر نقش. اطلاعات حساس در رابط مدیریت نمایش داده نمی‌شوند.</div>
    </div>
  </div>
  <div class="login-form">
    <div class="section-eyebrow">Secure Access</div>
    <h1>ورود به پنل مدیریت</h1>
    <p class="lead">برای ورود از حساب مدیریتی خود استفاده کنید.</p>
    <div class="field-group">
      <div class="field">
        <label for="username">نام کاربری</label>
        <input id="username" autocomplete="username" placeholder="نام کاربری مدیریت">
      </div>
      <div class="field">
        <label for="password">رمز عبور</label>
        <input id="password" type="password" autocomplete="current-password" placeholder="رمز عبور">
      </div>
    </div>
    <button class="btn" onclick="login()" style="margin-top:16px">ورود امن</button>
    <div class="divider">ورود اضطراری Owner</div>
    <div class="field">
      <label for="ownerKey">کلید مدیریت</label>
      <input id="ownerKey" type="password" autocomplete="off" placeholder="ADMIN_PANEL_API_KEY">
    </div>
    <div id="loginError"></div>
  </div>
</section>

<section id="app" class="hidden">
  <div class="shell">
    <aside class="side">
      <div class="side-head">
        <div class="brand-lockup">
          <div class="brand-mark">PP</div>
          <div>
            <div class="brand-title">PANELPRIMEPASAR</div>
            <div class="brand-sub">Executive Admin</div>
          </div>
        </div>
        <div class="side-meta">
          <span id="roleBadge" class="role-badge">ADMIN</span>
          <span class="env-dot">Production</span>
        </div>
      </div>

      <div class="nav">
        <div class="nav-label">Overview</div>
        <button data-view="dashboard" data-perm="view_dashboard" onclick="show('dashboard')"><span class="nav-icon">◆</span>داشبورد</button>

        <div class="nav-label">Commerce</div>
        <button data-view="customers" data-perm="view_users" onclick="show('customers')"><span class="nav-icon">◉</span>مشتریان</button>
        <button data-view="plans" data-perm="manage_plans" onclick="show('plans')"><span class="nav-icon">▦</span>پلن‌ها</button>
        <button data-view="discounts" data-perm="manage_discounts" onclick="show('discounts')"><span class="nav-icon">◇</span>تخفیف‌ها</button>
        <button data-view="orders" data-perm="view_orders" onclick="show('orders')"><span class="nav-icon">▤</span>سفارش‌ها</button>
        <button data-view="payments" data-perm="view_payments" onclick="show('payments')"><span class="nav-icon">◈</span>پرداخت‌ها</button>
        <button data-view="paymentMethods" data-perm="manage_payment_methods" onclick="show('paymentMethods')"><span class="nav-icon">⌁</span>روش‌های پرداخت</button>

        <div class="nav-label">Infrastructure</div>
        <button data-view="pasarguardInstances" data-perm="manage_pasarguard" onclick="show('pasarguardInstances')"><span class="nav-icon">⬡</span>پاسارگاردها</button>
        <button data-view="subscriptions" data-perm="view_orders" onclick="show('subscriptions')"><span class="nav-icon">↻</span>سرویس‌ها</button>

        <div class="nav-label">Operations</div>
        <button data-view="support" data-perm="manage_support" onclick="show('support')"><span class="nav-icon">◎</span>پشتیبانی</button>
        <button data-view="staff" data-perm="manage_admins" onclick="show('staff')"><span class="nav-icon">♙</span>مدیران</button>
        <button data-view="audit" data-perm="view_audit_logs" onclick="show('audit')"><span class="nav-icon">≡</span>لاگ‌ها</button>
      </div>

      <div class="side-footer">
        <button class="danger" onclick="logout()"><span class="nav-icon">↪</span>خروج امن</button>
      </div>
    </aside>

    <main>
      <header>
        <div class="header-title-wrap">
          <div>
            <div class="header-kicker">PANELPRIMEPASAR / CONTROL CENTER</div>
            <div id="pageTitle">داشبورد</div>
          </div>
        </div>
        <div class="header-actions">
          <div class="status-pill"><span id="status">آماده</span></div>
        </div>
      </header>
      <div id="view"></div>
    </main>
  </div>
</section>
<script>
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function token(){return sessionStorage.getItem('adminToken')||''}
function permissions(){try{return JSON.parse(sessionStorage.getItem('adminPermissions')||'[]')}catch{return []}}
function can(permission){return permissions().includes(permission)}
function applyPermissions(){
  const allowed=new Set(permissions());
  document.querySelectorAll('[data-perm]').forEach(el=>el.classList.toggle('hidden',!allowed.has(el.dataset.perm)));
  const role=sessionStorage.getItem('adminRole')||'admin';
  const badge=$('#roleBadge');if(badge)badge.textContent=role.toUpperCase();
}
async function api(path,opts={}){
  const headers={...(opts.headers||{})};
  if(token())headers['Authorization']='Bearer '+token();
  if(opts.body && !headers['Content-Type']) headers['Content-Type']='application/json';
  const r=await fetch(path,{...opts,headers});
  if(r.status===401){logout();throw new Error('دسترسی نامعتبر یا منقضی‌شده')}
  if(r.status===403)throw new Error('برای این بخش دسترسی ندارید');
  if(!r.ok){let m='HTTP '+r.status;try{m=(await r.json()).detail||m}catch{}throw new Error(m)}
  return r.status===204?null:r.json()
}
async function login(){
  const username=$('#username').value.trim();
  const password=$('#password').value;
  const ownerKey=$('#ownerKey').value;
  const body=ownerKey?{api_key:ownerKey}:{username,password};
  try{
    const auth=await fetch('/admin/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!auth.ok){let m='ورود ناموفق';try{m=(await auth.json()).detail||m}catch{}throw new Error(m)}
    const data=await auth.json();
    sessionStorage.setItem('adminToken',data.token);
    sessionStorage.setItem('adminPermissions',JSON.stringify(data.permissions||[]));
    sessionStorage.setItem('adminRole',data.role||'');
    $('#login').classList.add('hidden');$('#app').classList.remove('hidden');applyPermissions();show('dashboard')
  }catch(e){
    sessionStorage.removeItem('adminToken');
    sessionStorage.removeItem('adminPermissions');
    $('#loginError').textContent=e.message
  }
}
function logout(){sessionStorage.clear();location.reload()}
function table(rows,cols){
  if(!rows.length)return '<div class="empty-state">داده‌ای برای نمایش وجود ندارد.</div>';
  return '<div class="table-wrap"><table><thead><tr>'+cols.map(c=>'<th>'+esc(c[0])+'</th>').join('')+'</tr></thead><tbody>'+
  rows.map(r=>'<tr>'+cols.map(c=>'<td>'+c[1](r)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>'
}
const viewTitles={
 dashboard:'داشبورد مدیریتی',customers:'مدیریت مشتریان',plans:'پلن‌های فروش',discounts:'کدهای تخفیف',
 orders:'سفارش‌ها',payments:'تراکنش‌ها و پرداخت‌ها',paymentMethods:'روش‌های پرداخت',
 pasarguardInstances:'زیرساخت PasarGuard',subscriptions:'سرویس‌ها',support:'پشتیبانی',
 staff:'مدیران و دسترسی‌ها',audit:'گزارش فعالیت‌ها'
};
function activateNav(name){
  document.querySelectorAll('.nav button[data-view]').forEach(btn=>btn.classList.toggle('active',btn.dataset.view===name));
  const title=$('#pageTitle');if(title)title.textContent=viewTitles[name]||'مدیریت';
}
async function show(name){
  activateNav(name);
  $('#status').textContent='در حال بارگذاری...';
  try{await views[name]();$('#status').textContent='به‌روز و همگام'}catch(e){$('#view').innerHTML='<div class="card" style="color:var(--danger)">'+esc(e.message)+'</div>';$('#status').textContent='خطا در دریافت اطلاعات'}
}
const views={
 dashboard:async()=>{
  const d=await api('/admin/dashboard');
  const items=[['کاربران',d.customers],['سرویس فعال',d.active_services],['سفارش در جریان',d.pending_orders],['پرداخت موفق',d.verified_payments],['درآمد تاییدشده',Number(d.verified_revenue).toLocaleString()+' IRT'],['تیکت باز',d.open_tickets],['اکانت پاسارگارد',d.pasarguard_accounts],['پلن‌ها',d.plans]];
  $('#view').innerHTML='<div class="page-head"><div><div class="section-eyebrow">Executive Overview</div><h1>داشبورد مدیریتی</h1></div></div><div class="grid">'+items.map(x=>'<div class="card"><div class="muted">'+esc(x[0])+'</div><div class="metric">'+esc(x[1])+'</div></div>').join('')+'</div>'
 },
 customers:async()=>{
  const rows=await api('/admin/customers?limit=100');
  $('#view').innerHTML='<h1>مشتریان</h1>'+table(rows,[['Telegram',r=>'<code>'+esc(r.telegram_user_id)+'</code>'],['Username',r=>esc(r.username)],['نام',r=>esc((r.first_name||'')+' '+(r.last_name||''))],['وضعیت',r=>r.blocked?'🚫 مسدود':'✅ فعال'],['عملیات',r=>(can('manage_users')?'<button class="btn small '+(r.blocked?'':'danger')+'" onclick="blockCustomer(\''+r.id+'\','+(!r.blocked)+')">'+(r.blocked?'رفع مسدودی':'مسدود')+'</button>':'')+(can('manage_wallets')?'<button class="btn small" onclick="walletCredit(\''+r.id+'\')">💰 کیف پول</button>':'')]])
 },
 plans:async()=>{
  const rows=await api('/admin/plans');
  $('#view').innerHTML='<h1>پلن‌ها</h1><div class="card"><div class="toolbar"><input id="pname" placeholder="نام"><input id="pquota" type="number" placeholder="حجم بایت"><input id="pprice" type="number" placeholder="قیمت تومان"><input id="pdays" type="number" placeholder="روز"><button class="btn small" onclick="createPlan()">➕ ساخت</button></div></div>'+table(rows,[['نام',r=>esc(r.name)],['حجم',r=>Number(r.quota_bytes).toLocaleString()],['قیمت',r=>Number(r.price_amount).toLocaleString()+' '+esc(r.currency)],['اعتبار',r=>esc(r.validity_days??'∞')],['وضعیت',r=>r.active?'✅':'⛔'],['عملیات',r=>'<button class="btn small" onclick="togglePlan(\''+r.id+'\','+(!r.active)+')">'+(r.active?'غیرفعال':'فعال')+'</button>']])
 },
 discounts:async()=>{
  const rows=await api('/admin/discounts');
  $('#view').innerHTML='<h1>کدهای تخفیف</h1><div class="card"><div class="toolbar"><input id="dcode" placeholder="کد"><select id="dkind"><option value="percent">درصدی</option><option value="fixed">مبلغ ثابت</option></select><input id="dvalue" type="number" placeholder="مقدار"><input id="dmax" type="number" placeholder="حداکثر استفاده"><button class="btn small" onclick="createDiscount()">➕ ساخت</button></div></div>'+table(rows,[['کد',r=>'<code>'+esc(r.code)+'</code>'],['نوع',r=>esc(r.kind)],['مقدار',r=>r.kind==='percent'?esc(r.value_percent)+'%':Number(r.value_amount||0).toLocaleString()],['استفاده',r=>esc(r.used_count)+' / '+esc(r.max_uses??'∞')],['وضعیت',r=>r.active?'✅':'⛔'],['عملیات',r=>'<button class="btn small" onclick="toggleDiscount(\''+r.id+'\','+(!r.active)+')">'+(r.active?'غیرفعال':'فعال')+'</button>']])
 },
 orders:async()=>{const rows=await api('/admin/orders?limit=100');$('#view').innerHTML='<h1>سفارش‌ها</h1>'+table(rows,[['ID',r=>'<code>'+esc(r.id.slice(0,8))+'</code>'],['نوع',r=>esc(r.kind)],['وضعیت',r=>esc(r.status)],['مبلغ',r=>Number(r.amount).toLocaleString()+' '+esc(r.currency)],['حجم',r=>Number(r.quota_bytes).toLocaleString()],['عملیات',r=>'<button class="btn small" onclick="orderActionMenu(\''+r.id+'\')">⚙️ عملیات</button><div class="muted">'+esc(orderActionHtml(r))+'</div>']])},
 payments:async()=>{const rows=await api('/admin/payments?limit=100');$('#view').innerHTML='<h1>پرداخت‌ها</h1>'+table(rows,[['ID',r=>'<code>'+esc(r.id.slice(0,8))+'</code>'],['درگاه',r=>esc(r.provider)],['مبلغ',r=>Number(r.amount).toLocaleString()+' '+esc(r.currency)],['وضعیت',r=>esc(r.status)],['تراکنش',r=>esc(r.transaction_id)]])},
 paymentMethods:async()=>{
  const rows=await api('/admin/payment-methods');
  const form='<div class="card"><h2>افزودن روش پرداخت</h2><div class="toolbar">'+
   '<input id="pmSlug" placeholder="شناسه کوتاه مثل zarinpal">'+
   '<input id="pmName" placeholder="نام نمایشی">'+
   '<select id="pmKind"><option value="manual_card">کارت‌به‌کارت</option><option value="zarinpal">زرین‌پال</option><option value="idpay">IDPay</option><option value="zibal">زیبال</option><option value="nextpay">NextPay</option></select>'+
   '<input id="pmSecret" type="password" autocomplete="new-password" placeholder="Merchant ID / API Key">'+
   '<input id="pmCard" placeholder="شماره کارت (کارت‌به‌کارت)">'+
   '<input id="pmHolder" placeholder="نام صاحب کارت">'+
   '<input id="pmBank" placeholder="بانک">'+
   '<input id="pmIban" placeholder="شبا (اختیاری)">'+
   '<label><input id="pmSandbox" type="checkbox"> تست/Sandbox</label>'+
   '<label><input id="pmEnabled" type="checkbox"> فعال</label>'+
   '<button class="btn small" onclick="createPaymentMethod()">➕ ذخیره</button></div>'+
   '<p class="muted">اطلاعات محرمانه در پاسخ API نمایش داده نمی‌شود و با کلید PAYMENT_CREDENTIALS_MASTER_KEY رمزگذاری می‌شود.</p></div>';
  $('#view').innerHTML='<h1>روش‌های پرداخت</h1>'+form+table(rows,[['نام',r=>esc(r.display_name)],['نوع',r=>esc(r.kind)],['شناسه',r=>'<code>'+esc(r.slug)+'</code>'],['حالت',r=>r.sandbox?'🧪 تست':'واقعی'],['اعتبارنامه',r=>r.kind==='manual_card'?'—':(r.credentials_configured?'✅ تنظیم شده':'❌ ناقص')],['وضعیت',r=>r.enabled?'✅ فعال':'⛔ غیرفعال'],['عملیات',r=>'<button class="btn small" onclick="togglePaymentMethod(\''+r.id+'\','+(!r.enabled)+')">'+(r.enabled?'غیرفعال':'فعال')+'</button><button class="btn small" onclick="editPaymentMethod(\''+r.id+'\')">✏️ ویرایش</button>']])
 },
 pasarguardInstances:async()=>{
  const rows=await api('/admin/pasarguard/instances');
  const form='<div class="card"><h2>افزودن PasarGuard</h2><div class="toolbar">'+
   '<input id="pgName" placeholder="نام">'+
   '<input id="pgUrl" placeholder="https://panel.example.com">'+
   '<input id="pgEnv" placeholder="نام Env برای API Key">'+
   '<input id="pgRole" placeholder="نام نقش نماینده">'+
   '<input id="pgWeight" type="number" value="100" placeholder="وزن">'+
   '<label><input id="pgEnabled" type="checkbox" checked> فعال</label>'+
   '<button class="btn small" onclick="createPasarguard()">➕ افزودن</button>'+
   '<button class="btn small" onclick="checkPasarguards()">🩺 Health Check</button></div>'+
   '<p class="muted">مقدار واقعی API Key در دیتابیس ذخیره نمی‌شود؛ فقط نام متغیر محیطی ثبت می‌شود.</p></div>';
  $('#view').innerHTML='<h1>PasarGuard Instances</h1>'+form+table(rows,[['نام',r=>esc(r.name)],['آدرس',r=>'<code>'+esc(r.base_url)+'</code>'],['وزن',r=>esc(r.weight)],['وضعیت',r=>r.enabled?'✅ فعال':'⛔ غیرفعال'],['Health',r=>r.last_health_ok===true?'🟢 سالم':(r.last_health_ok===false?'🔴 خطا':'—')],['Env',r=>'<code>'+esc(r.api_key_env_var||r.bearer_token_env_var||'')+'</code>'],['عملیات',r=>'<button class="btn small" onclick="togglePasarguard(\''+r.id+'\','+(!r.enabled)+')">'+(r.enabled?'غیرفعال':'فعال')+'</button><button class="btn small" onclick="editPasarguard(\''+r.id+'\')">✏️ ویرایش</button>']])
 },
 subscriptions:async()=>{const rows=await api('/admin/subscriptions?limit=100');$('#view').innerHTML='<h1>سرویس‌ها</h1>'+table(rows,[['ID',r=>'<code>'+esc(r.id.slice(0,8))+'</code>'],['وضعیت',r=>esc(r.status)],['حجم',r=>Number(r.quota_bytes).toLocaleString()],['انقضا',r=>esc(r.expires_at||'∞')],['Auto Renew',r=>r.auto_renew?'✅':'—']])},
 support:async()=>{const rows=await api('/admin/support?limit=100');$('#view').innerHTML='<h1>پشتیبانی</h1>'+table(rows,[['ID',r=>'<code>'+esc(r.id.slice(0,8))+'</code>'],['موضوع',r=>esc(r.subject)],['وضعیت',r=>esc(r.status)],['به‌روزرسانی',r=>esc(r.updated_at)]])},
 staff:async()=>{const rows=await api('/admin/staff');$('#view').innerHTML='<h1>مدیران</h1>'+table(rows,[['Telegram',r=>esc(r.telegram_user_id)],['Username',r=>esc(r.username)],['نقش',r=>esc(r.role)],['وضعیت',r=>r.active?'✅':'⛔'],['عملیات',r=>'<button class="btn small" onclick="staffStatus(\''+r.id+'\','+(!r.active)+')">'+(r.active?'غیرفعال':'فعال')+'</button>']])},
 audit:async()=>{const rows=await api('/admin/audit?limit=100');$('#view').innerHTML='<h1>Audit Log</h1>'+table(rows,[['زمان',r=>esc(r.created_at)],['Actor',r=>esc(r.actor_type)+' '+esc(r.actor_id)],['عملیات',r=>esc(r.action)],['Entity',r=>esc(r.entity_type)+' '+esc(r.entity_id)]])}
};
function orderActionHtml(r){
 const actions=[];
 const unpaid=r.status==='pending'||r.status==='awaiting_payment';
 if(unpaid&&can('approve_payments'))actions.push('پرداخت');
 if(unpaid&&can('manage_orders'))actions.push('لغو');
 if((r.status==='paid'||r.status==='provisioning'||r.status==='failed')&&can('manage_pasarguard'))actions.push('اجرا');
 if(r.status==='completed'&&r.kind==='new'&&can('manage_pasarguard'))actions.push('صدور مجدد');
 return actions.length?actions.join(' / '):'—'
}
async function orderActionMenu(id){
 const choice=(prompt('عملیات: approve / reject / cancel / fulfill / reissue','')||'').trim().toLowerCase();
 if(!choice)return;
 const map={approve:'approve-manual',reject:'reject-payment',cancel:'cancel',fulfill:'fulfill',reissue:'reissue-credentials'};
 const endpoint=map[choice];
 if(!endpoint){alert('عملیات معتبر نیست');return}
 const result=await api('/admin/orders/'+id+'/'+endpoint,{method:'POST'});
 alert(result.success===false?'عملیات کامل نشد':'عملیات انجام شد');
 show('orders')
}
async function blockCustomer(id,blocked){await api('/admin/customers/'+id+'/block',{method:'PATCH',body:JSON.stringify({blocked})});show('customers')}
async function walletCredit(id){
 const wallet=await api('/admin/customers/'+id+'/wallet');
 const raw=prompt('موجودی فعلی: '+Number(wallet.balance).toLocaleString()+' '+wallet.currency+'\nمبلغ واریز را به تومان وارد کنید:');
 if(!raw)return;
 const amount=Number(raw.replace(/,/g,''));
 if(!Number.isInteger(amount)||amount<=0){alert('مبلغ معتبر نیست');return}
 const key='web-wallet-'+crypto.randomUUID();
 const result=await api('/admin/customers/'+id+'/wallet/credit',{method:'POST',body:JSON.stringify({amount,currency:wallet.currency,idempotency_key:key,reference:'web-admin'})});
 alert('موجودی جدید: '+Number(result.balance).toLocaleString()+' '+result.currency);
}
async function togglePlan(id,active){await api('/admin/plans/'+id,{method:'PATCH',body:JSON.stringify({is_active:active})});show('plans')}
async function createPlan(){
 const body={name:$('#pname').value,quota_bytes:Number($('#pquota').value),price_amount:Number($('#pprice').value),currency:'IRT',validity_days:$('#pdays').value?Number($('#pdays').value):null};
 await api('/admin/plans',{method:'POST',body:JSON.stringify(body)});show('plans')
}
async function createDiscount(){
 const kind=$('#dkind').value,value=Number($('#dvalue').value),maxRaw=$('#dmax').value;
 const body={code:$('#dcode').value,kind,max_uses:maxRaw?Number(maxRaw):null};
 if(kind==='percent')body.value_percent=value;else body.value_amount=value;
 await api('/admin/discounts',{method:'POST',body:JSON.stringify(body)});show('discounts')
}
async function toggleDiscount(id,active){await api('/admin/discounts/'+id,{method:'PATCH',body:JSON.stringify({is_active:active})});show('discounts')}
function paymentCredential(kind,value){
 if(!value)return null;
 if(kind==='zarinpal')return {merchant_id:value};
 if(kind==='zibal')return {merchant:value};
 return {api_key:value};
}
async function createPaymentMethod(){
 const kind=$('#pmKind').value;
 const publicConfig={};
 if(kind==='manual_card'){
  publicConfig.card_number=$('#pmCard').value;
  publicConfig.card_holder=$('#pmHolder').value;
  if($('#pmBank').value)publicConfig.bank_name=$('#pmBank').value;
  if($('#pmIban').value)publicConfig.iban=$('#pmIban').value;
 }
 const body={slug:$('#pmSlug').value,kind,display_name:$('#pmName').value,is_enabled:$('#pmEnabled').checked,sandbox:$('#pmSandbox').checked,sort_order:0,public_config:publicConfig,credentials:paymentCredential(kind,$('#pmSecret').value)};
 await api('/admin/payment-methods',{method:'POST',body:JSON.stringify(body)});show('paymentMethods')
}
async function togglePaymentMethod(id,enabled){
 const rows=await api('/admin/payment-methods'),r=rows.find(x=>x.id===id);if(!r)return;
 const body={slug:r.slug,kind:r.kind,display_name:r.display_name,is_enabled:enabled,sandbox:r.sandbox,sort_order:r.sort_order,public_config:r.public_config,credentials:null};
 await api('/admin/payment-methods/'+id,{method:'PUT',body:JSON.stringify(body)});show('paymentMethods')
}
async function editPaymentMethod(id){
 const rows=await api('/admin/payment-methods'),r=rows.find(x=>x.id===id);if(!r)return;
 const name=prompt('نام نمایشی',r.display_name);if(name===null)return;
 const secret=r.kind==='manual_card'?'':prompt('Merchant ID / API Key جدید (خالی = بدون تغییر)','');
 const publicConfig={...r.public_config};
 if(r.kind==='manual_card'){
  const card=prompt('شماره کارت',publicConfig.card_number||'');if(card===null)return;
  const holder=prompt('نام صاحب کارت',publicConfig.card_holder||'');if(holder===null)return;
  publicConfig.card_number=card;publicConfig.card_holder=holder;
  publicConfig.bank_name=prompt('نام بانک',publicConfig.bank_name||'')||'';
  publicConfig.iban=prompt('شبا',publicConfig.iban||'')||'';
 }
 const body={slug:r.slug,kind:r.kind,display_name:name,is_enabled:r.enabled,sandbox:r.sandbox,sort_order:r.sort_order,public_config:publicConfig,credentials:secret?paymentCredential(r.kind,secret):null};
 await api('/admin/payment-methods/'+id,{method:'PUT',body:JSON.stringify(body)});show('paymentMethods')
}
async function createPasarguard(){
 const body={name:$('#pgName').value,base_url:$('#pgUrl').value,api_key_env_var:$('#pgEnv').value||null,bearer_token_env_var:null,reseller_role_name:$('#pgRole').value||null,reseller_role_id:null,weight:Number($('#pgWeight').value||100),is_enabled:$('#pgEnabled').checked};
 await api('/admin/pasarguard/instances',{method:'POST',body:JSON.stringify(body)});show('pasarguardInstances')
}
async function togglePasarguard(id,enabled){
 const rows=await api('/admin/pasarguard/instances'),r=rows.find(x=>x.id===id);if(!r)return;
 const body={name:r.name,base_url:r.base_url,api_key_env_var:r.api_key_env_var,bearer_token_env_var:r.bearer_token_env_var,reseller_role_name:r.reseller_role_name,reseller_role_id:r.reseller_role_id,weight:r.weight,is_enabled:enabled};
 await api('/admin/pasarguard/instances/'+id,{method:'PATCH',body:JSON.stringify(body)});show('pasarguardInstances')
}
async function editPasarguard(id){
 const rows=await api('/admin/pasarguard/instances'),r=rows.find(x=>x.id===id);if(!r)return;
 const name=prompt('نام',r.name);if(name===null)return;
 const url=prompt('Base URL',r.base_url);if(url===null)return;
 const env=prompt('نام Env برای API Key',r.api_key_env_var||'');if(env===null)return;
 const role=prompt('نام نقش نماینده',r.reseller_role_name||'');if(role===null)return;
 const weightRaw=prompt('وزن',String(r.weight));if(weightRaw===null)return;
 const body={name,base_url:url,api_key_env_var:env||null,bearer_token_env_var:null,reseller_role_name:role||null,reseller_role_id:r.reseller_role_id,weight:Number(weightRaw),is_enabled:r.enabled};
 await api('/admin/pasarguard/instances/'+id,{method:'PATCH',body:JSON.stringify(body)});show('pasarguardInstances')
}
async function checkPasarguards(){
 const rows=await api('/admin/pasarguard/instances/health',{method:'POST'});
 const ok=rows.filter(x=>x.healthy).length;
 alert('Health Check: '+ok+' از '+rows.length+' سالم');
 show('pasarguardInstances')
}
async function staffStatus(id,active){await api('/admin/staff/'+id+'/status',{method:'PATCH',body:JSON.stringify({active})});show('staff')}
if(token()){api('/admin/auth/me').then(me=>{sessionStorage.setItem('adminPermissions',JSON.stringify(me.permissions||[]));$('#login').classList.add('hidden');$('#app').classList.remove('hidden');applyPermissions();show('dashboard')}).catch(()=>sessionStorage.clear())}
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
