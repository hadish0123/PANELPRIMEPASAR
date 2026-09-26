# ruff: noqa: E501
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from panelprimepasar.config import get_settings
from panelprimepasar.security import WebAdminSecurityError, verify_session_token

router = APIRouter(prefix="/admin", include_in_schema=False)

_ADMIN_HTML = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PANELPRIMEPASAR Admin</title>
<style>
:root{
  color-scheme:light;
  --bg:#f6f2e9;
  --bg-soft:#fbf8f1;
  --panel:#fffdf8;
  --panel-2:#f8f2e7;
  --panel-3:#efe6d8;
  --line:#e4dac9;
  --line-soft:#eee7dc;
  --text:#172033;
  --text-soft:#4d586c;
  --muted:#7b8493;
  --gold:#b58a3e;
  --gold-strong:#8c6527;
  --gold-soft:#f3e5c8;
  --navy:#17284a;
  --navy-soft:#e9eef8;
  --blue:#356dc4;
  --success:#27815d;
  --danger:#b84650;
  --warning:#a66d18;
  --shadow:0 22px 65px rgba(63,49,27,.10);
  --shadow-soft:0 10px 30px rgba(63,49,27,.08);
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
    radial-gradient(circle at 91% 0%,rgba(213,181,118,.24),transparent 28%),
    radial-gradient(circle at 5% 92%,rgba(58,103,177,.09),transparent 27%),
    linear-gradient(180deg,#fbf8f1 0%,#f3eee5 100%);
  color:var(--text);
  letter-spacing:-.01em;
}
button,input,select{font:inherit}
button{user-select:none}
button:disabled{cursor:wait;opacity:.62;transform:none!important}
a{color:inherit}
.hidden{display:none!important}
.muted{color:var(--muted)}
.ok{color:var(--success)}
.danger{color:var(--danger)!important;border-color:rgba(184,70,80,.30)!important}
.small{width:auto!important;display:inline-flex!important;align-items:center;justify-content:center;gap:7px}
code{
  direction:ltr;
  unicode-bidi:plaintext;
  color:#73551f;
  background:#fff7e7;
  border:1px solid #ead7b1;
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
  width:min(980px,calc(100% - 36px));
  min-height:570px;
  margin:7vh auto;
  display:grid;
  grid-template-columns:minmax(0,1.04fr) minmax(320px,.96fr);
  padding:0;
  overflow:hidden;
  border-radius:30px;
  border:1px solid #ddcfb7;
  background:rgba(255,253,248,.96);
  box-shadow:0 30px 90px rgba(83,64,34,.16);
  position:relative;
}
#login:before{
  content:"";
  position:absolute;
  inset:0;
  pointer-events:none;
  background:linear-gradient(135deg,rgba(255,255,255,.60),transparent 42%,rgba(210,173,99,.05));
}
.login-visual{
  padding:56px 50px;
  background:
    radial-gradient(circle at 18% 12%,rgba(255,255,255,.72),transparent 28%),
    linear-gradient(145deg,#f5e5c6 0%,#ead5ad 52%,#d8b875 100%);
  border-left:1px solid rgba(154,114,48,.18);
  display:flex;
  flex-direction:column;
  justify-content:space-between;
  min-height:570px;
  color:#1b2941;
}
.login-form{
  padding:56px 50px;
  display:flex;
  flex-direction:column;
  justify-content:center;
  background:rgba(255,253,248,.92);
}
.login-eyebrow,.section-eyebrow{
  color:var(--gold-strong);
  font-size:11px;
  letter-spacing:.22em;
  text-transform:uppercase;
  font-weight:800;
}
.brand-lockup{display:flex;align-items:center;gap:14px}
.brand-mark{
  width:52px;height:52px;border-radius:16px;
  display:grid;place-items:center;
  background:linear-gradient(145deg,#233b67,#17284a);
  color:#f6dfac;font-weight:900;font-size:18px;
  box-shadow:0 13px 28px rgba(28,47,81,.20);
  border:1px solid rgba(255,255,255,.58);
}
.brand-title{font-weight:900;font-size:19px;letter-spacing:.02em;color:var(--navy)}
.brand-sub{color:#6e654f;font-size:12px;margin-top:3px}
.lux-line{height:1px;background:linear-gradient(90deg,transparent,#b98c3f,transparent);margin:29px 0}
.login-visual h2{font-size:34px;line-height:1.55;max-width:440px;letter-spacing:-.04em;color:#17284a}
.login-visual p{color:#5d5749;max-width:470px;font-size:14px}
.security-note{
  display:flex;gap:12px;align-items:flex-start;
  padding:14px 15px;border-radius:14px;
  border:1px solid rgba(127,92,35,.16);
  background:rgba(255,255,255,.44);
  color:#635d51;font-size:12px;line-height:1.8;
}
.security-dot{width:8px;height:8px;border-radius:50%;background:var(--success);margin-top:6px;box-shadow:0 0 0 5px rgba(39,129,93,.09)}
.login-form h1{font-size:31px;margin-top:10px;color:var(--navy)}
.login-form .lead{color:var(--muted);font-size:13px;margin:10px 0 26px}
.field-group{display:grid;gap:13px}
.field{display:grid;gap:7px}
.field label{font-size:12px;color:var(--text-soft);font-weight:700}
.divider{display:flex;align-items:center;gap:12px;color:#9299a4;font-size:11px;margin:18px 0}
.divider:before,.divider:after{content:"";height:1px;flex:1;background:var(--line)}
#loginError{margin-top:12px;color:var(--danger);font-size:12px;min-height:18px}

/* App shell */
.shell{
  display:grid;
  grid-template-columns:280px minmax(0,1fr);
  min-height:100vh;
}
.side{
  position:sticky;
  top:0;
  height:100vh;
  padding:24px 18px 18px;
  border-left:1px solid #dfd4c3;
  background:
    linear-gradient(180deg,rgba(255,253,248,.98),rgba(247,241,231,.99)),
    radial-gradient(circle at top right,rgba(213,181,118,.18),transparent 34%);
  box-shadow:12px 0 44px rgba(79,61,31,.07);
  z-index:20;
  overflow:auto;
}
.side-head{padding:2px 8px 20px;border-bottom:1px solid var(--line-soft);margin-bottom:14px}
.side-meta{display:flex;align-items:center;justify-content:space-between;margin-top:14px}
.role-badge{
  padding:5px 9px;border-radius:999px;
  color:#78571f;
  background:#f6e8ca;
  border:1px solid #e7d2a6;
  font-size:10px;font-weight:800;letter-spacing:.08em;
}
.env-dot{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:10px}
.env-dot:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--success);box-shadow:0 0 0 4px rgba(39,129,93,.08)}
.nav{display:grid;gap:4px}
.nav-label{
  color:#9d9384;font-size:10px;font-weight:900;letter-spacing:.14em;
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
  color:#596477;
  cursor:pointer;
  text-align:right;
  transition:.18s ease;
  display:flex;
  align-items:center;
  gap:10px;
  position:relative;
  font-weight:700;
}
.nav button:hover{
  background:#f5efe4;
  color:var(--navy);
  border-color:#ede1cf;
  transform:translateX(-1px);
}
.nav button.active{
  color:var(--navy);
  background:linear-gradient(90deg,#f2dfba,#fbf5e9);
  border-color:#e7cf9d;
  box-shadow:0 7px 20px rgba(139,101,39,.08);
}
.nav button.active:after{
  content:"";
  position:absolute;
  right:-19px;
  width:3px;height:24px;border-radius:99px;
  background:linear-gradient(180deg,#c49a4d,#8d6827);
  box-shadow:0 0 12px rgba(181,138,62,.25);
}
.nav-icon{
  width:27px;height:27px;display:grid;place-items:center;flex:0 0 auto;
  border-radius:8px;background:#f1ece3;
  color:#707a89;font-size:13px;
  border:1px solid #e9e0d3;
}
.nav button.active .nav-icon{background:var(--navy);color:#f4dba8;border-color:var(--navy)}
.side-footer{margin-top:18px;padding-top:14px;border-top:1px solid var(--line-soft)}

main{min-width:0;padding:0 30px 34px}
header{
  position:sticky;top:0;z-index:15;
  height:78px;
  display:flex;align-items:center;justify-content:space-between;
  padding:0 4px;
  background:linear-gradient(180deg,rgba(250,247,240,.96),rgba(250,247,240,.86));
  backdrop-filter:blur(18px);
  border-bottom:1px solid rgba(137,111,66,.10);
}
.header-title-wrap{display:flex;align-items:center;gap:12px}
.header-title-wrap,.header-actions{min-width:0}
.header-kicker{font-size:10px;letter-spacing:.15em;color:var(--gold-strong);font-weight:900}
#pageTitle{font-size:19px;font-weight:900;margin-top:2px;color:var(--navy);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.header-actions{display:flex;align-items:center;gap:10px}
.status-pill{
  display:flex;align-items:center;gap:8px;
  padding:8px 11px;border-radius:999px;
  border:1px solid #ded4c3;
  background:rgba(255,253,248,.86);
  color:#687284;font-size:11px;
  box-shadow:0 5px 15px rgba(69,53,26,.05);
}
.status-pill:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--success)}
#status{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#view{padding-top:28px;animation:fadeIn .22s ease}
@keyframes fadeIn{from{opacity:.3;transform:translateY(4px)}to{opacity:1;transform:none}}

.notice{
  position:fixed;inset-inline-start:24px;bottom:24px;z-index:80;
  width:min(520px,calc(100vw - 48px));
  padding:13px 15px;border-radius:12px;
  border:1px solid #e9c3c6;background:#fff1f1;color:#8f3039;
  box-shadow:0 16px 46px rgba(63,49,27,.18);
  line-height:1.7;font-size:12px;
}
.notice.success{border-color:#b9dacb;background:#eef9f3;color:#1f6f50}

/* Content */
.page-head{display:flex;align-items:end;justify-content:space-between;gap:16px;margin-bottom:18px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.card{
  background:
    linear-gradient(180deg,rgba(255,254,251,.98),rgba(252,248,241,.98));
  border:1px solid #e7ddce;
  border-radius:var(--radius);
  padding:18px;
  box-shadow:var(--shadow-soft);
  position:relative;
  overflow:hidden;
}
.card:after{
  content:"";
  position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(140deg,rgba(255,255,255,.70),transparent 36%);
}
.grid .card{
  min-height:128px;
  display:flex;flex-direction:column;justify-content:space-between;
  border-color:#eadcc2;
}
.grid .card:before{
  content:"";position:absolute;left:0;top:0;width:68px;height:3px;
  background:linear-gradient(90deg,#c79b4d,transparent);
}
.metric{font-size:27px;font-weight:900;color:var(--navy);margin-top:16px;letter-spacing:-.035em}
.toolbar{
  display:flex;align-items:center;gap:9px;flex-wrap:wrap;
  margin:14px 0 0;
}
input,select{
  min-height:42px;
  background:#fffdfa;
  color:var(--text);
  border:1px solid #ded4c4;
  border-radius:10px;
  padding:9px 11px;
  outline:none;
  transition:.18s ease;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.70);
}
input::placeholder{color:#a1a7b0}
input:focus,select:focus{
  border-color:#c49a4d;
  box-shadow:0 0 0 3px rgba(196,154,77,.12);
  background:#fff;
}
input[type="checkbox"]{min-height:auto;accent-color:#a4772d;transform:translateY(1px)}
label{color:var(--text-soft);font-size:12px}
.btn{
  min-height:40px;
  width:100%;
  margin:5px 0;
  padding:9px 13px;
  border:1px solid #d8bd86;
  border-radius:10px;
  background:linear-gradient(180deg,#f3dfb5,#e4c98d);
  color:#644718;
  cursor:pointer;
  text-align:center;
  font-weight:800;
  font-size:12px;
  transition:.17s ease;
  box-shadow:0 5px 14px rgba(119,84,28,.08);
}
.btn:hover{
  transform:translateY(-1px);
  border-color:#c49a4d;
  background:linear-gradient(180deg,#f7e8c8,#e9cf97);
  box-shadow:0 9px 22px rgba(119,84,28,.13);
}
.btn.danger,.nav .danger{
  color:#a33640!important;
  background:#fff1f1;
  border-color:#e9c3c6!important;
}
.btn.danger:hover,.nav .danger:hover{background:#ffe5e6!important}
.payment-category-picker,.payment-provider-picker{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;
  margin-top:14px;
}
.payment-choice{
  min-height:52px;margin:0;padding:11px 14px;border:1px solid #ded4c4;
  border-radius:12px;background:#fffdfa;color:var(--text);cursor:pointer;
  font-weight:800;transition:.17s ease;box-shadow:var(--shadow-soft);
}
.payment-choice:hover{transform:translateY(-1px);border-color:#c49a4d;background:#fff9ed}
.payment-choice.is-active{
  color:#684817;border-color:#c49a4d;background:linear-gradient(180deg,#f8e8c6,#efdab0);
  box-shadow:0 0 0 3px rgba(196,154,77,.12);
}
.payment-provider-picker{padding-top:2px}
.payment-form-panel{
  margin-top:14px;padding:15px;border:1px solid #e7ddce;border-radius:12px;
  background:rgba(255,253,248,.78);
}
.payment-form-panel h3{margin-bottom:4px}
.payment-field{
  min-width:175px;display:flex;flex-direction:column;align-items:stretch;gap:6px;
  color:var(--text-soft);font-size:11px;font-weight:700;
}
.payment-field input{width:100%}
.payment-edit-hint{
  width:100%;margin:4px 0 0;padding:9px 11px;border-radius:10px;
  background:#fff8e9;color:#786443;border:1px solid #ead9b7;
}
.table-wrap{
  width:100%;
  overflow:auto;
  border-radius:var(--radius);
  border:1px solid #e3dacd;
  background:#fffdf9;
  box-shadow:var(--shadow-soft);
}
table{width:100%;border-collapse:separate;border-spacing:0;min-width:760px}
th,td{
  padding:13px 15px;
  text-align:right;
  white-space:nowrap;
  border-bottom:1px solid #eee6da;
  font-size:12px;
}
th{
  color:#665d50;
  background:linear-gradient(180deg,#f5ede0,#f1e7d7);
  font-size:10px;
  font-weight:900;
  letter-spacing:.07em;
  text-transform:uppercase;
}
tbody tr{transition:.15s ease}
tbody tr:hover{background:#fff9ed}
tbody tr:last-child td{border-bottom:0}
td{color:#394457}
.empty-state{
  border:1px dashed #d7cbb9;
  background:rgba(255,253,248,.72);
  border-radius:var(--radius);
  padding:34px;text-align:center;color:var(--muted);
}

/* Scrollbars */
*{scrollbar-width:thin;scrollbar-color:#c9bda9 #f4eee4}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-track{background:#f4eee4}
::-webkit-scrollbar-thumb{background:#c9bda9;border-radius:20px}

/* Responsive */
@media(max-width:1180px){
  .grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .shell{grid-template-columns:244px minmax(0,1fr)}
}
@media(max-width:860px){
  #login{grid-template-columns:1fr;margin:24px auto;min-height:0}
  .login-visual{display:none}
  .login-form{padding:36px 28px}
  .shell{grid-template-columns:1fr}
  .side{position:relative;height:auto;border-left:0;border-bottom:1px solid #dfd4c3;padding:14px}
  .side-head{padding-bottom:12px}
  .nav{display:flex;overflow:auto;gap:6px;padding-bottom:4px}
  .nav-label{display:none}
  .nav button{min-width:max-content;width:auto;padding:8px 11px}
  .nav button.active:after{display:none}
  .side-footer{display:block;margin-top:10px;padding-top:10px}
  .side-footer .btn{margin:0}
  main{padding:0 16px 28px}
  header{height:64px}
}
@media(max-width:560px){
  .grid{grid-template-columns:1fr}
  .payment-category-picker,.payment-provider-picker{grid-template-columns:1fr}
  .card{padding:14px}
  .login-form{padding:30px 22px}
  .login-form h1{font-size:26px}
  header{align-items:center}
  .header-kicker{display:none}
  #pageTitle{font-size:16px}
  .status-pill{padding:7px 9px;max-width:128px}
  #view{padding-top:20px}
  .toolbar{align-items:stretch}
  .toolbar > input,.toolbar > select,.toolbar > .btn.small{width:100%!important;max-width:none}
  .toolbar > label{
    width:100%;min-height:42px;display:flex;align-items:center;gap:8px;
    padding:8px 10px;border:1px solid var(--line);border-radius:10px;background:#fffdfa;
  }
  .toolbar > .payment-field{flex-direction:column;align-items:stretch;height:auto}
  .notice{inset-inline:12px;bottom:12px;width:calc(100vw - 24px)}
}
</style>
</head>
<body>
<noscript><div style="margin:24px;padding:16px;border:1px solid #e0b8bb;border-radius:12px;background:#fff1f1;color:#9b3039;text-align:center">برای استفاده از پنل مدیریت، JavaScript مرورگر باید فعال باشد.</div></noscript>
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
  <form id="loginForm" class="login-form" method="post" action="/admin/auth/login-form">
    <div class="section-eyebrow">Secure Access</div>
    <h1>ورود به پنل مدیریت</h1>
    <p class="lead">برای ورود از حساب مدیریتی خود استفاده کنید.</p>
    <div class="field-group">
      <div class="field">
        <label for="username">نام کاربری</label>
        <input id="username" name="username" autocomplete="username" placeholder="نام کاربری مدیریت">
      </div>
      <div class="field">
        <label for="password">رمز عبور</label>
        <input id="password" name="password" type="password" autocomplete="current-password" placeholder="رمز عبور">
      </div>
    </div>
    <button class="btn" type="submit" style="margin-top:16px">ورود امن</button>
    <div class="divider">ورود اضطراری Owner</div>
    <div class="field">
      <label for="ownerKey">کلید مدیریت</label>
      <input id="ownerKey" name="api_key" type="password" autocomplete="off" placeholder="ADMIN_PANEL_API_KEY">
    </div>
    <div id="loginError"></div>
  </form>
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
        <button class="btn danger side-logout" type="button" onclick="logout()"><span class="nav-icon">↪</span>خروج امن</button>
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
      <div id="notice" class="notice hidden" role="status" aria-live="polite"></div>
      <div id="view"></div>
    </main>
  </div>
</section>
<script src="/admin/ui.js" defer></script>
</body>
</html>"""

_ADMIN_JS = r"""
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let noticeTimer=0;
let paymentMethodsCache=[];
let editingPaymentMethod=null;
function humanError(value){
  if(value instanceof Error)return humanError(value.message);
  if(typeof value==='string'&&value.trim())return value.trim();
  if(Array.isArray(value))return value.map(item=>humanError(item?.msg??item?.message??item)).filter(Boolean).join(' • ');
  if(value&&typeof value==='object'){
    if('detail' in value)return humanError(value.detail);
    if('message' in value)return humanError(value.message);
    try{return JSON.stringify(value)}catch{}
  }
  return 'خطای ناشناخته';
}
function notify(message,kind='error'){
  const box=$('#notice');if(!box)return;
  box.textContent=humanError(message);
  box.className='notice '+kind;
  clearTimeout(noticeTimer);
  noticeTimer=setTimeout(()=>box.classList.add('hidden'),6000);
}
async function runAction(button,task,successMessage=''){
  if(button?.disabled)return null;
  if(button){button.disabled=true;button.setAttribute('aria-busy','true')}
  try{
    const result=await task();
    if(successMessage)notify(successMessage,'success');
    return result
  }catch(error){notify(error);return null}
  finally{if(button){button.disabled=false;button.removeAttribute('aria-busy')}}
}
window.addEventListener('unhandledrejection',event=>{
  event.preventDefault();
  notify(event.reason);
  const status=$('#status');if(status)status.textContent='خطا در انجام عملیات';
});
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
  if(!r.ok){
    let detail='HTTP '+r.status;
    try{const data=await r.json();detail=data.detail??data.message??detail}catch{}
    throw new Error(humanError(detail))
  }
  return r.status===204?null:r.json()
}
async function login(event){
  if(event)event.preventDefault();
  $('#loginError').textContent='';
  const username=$('#username').value.trim();
  const password=$('#password').value;
  const ownerKey=$('#ownerKey').value;
  if(!ownerKey&&(!username||!password)){
    $('#loginError').textContent='نام کاربری و رمز عبور یا کلید مدیریت را وارد کنید.';
    return
  }
  const body=ownerKey?{api_key:ownerKey}:{username,password};
  try{
    const auth=await fetch('/admin/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!auth.ok){let m='ورود ناموفق';try{m=(await auth.json()).detail||m}catch{}throw new Error(m)}
    const data=await auth.json();
    sessionStorage.setItem('adminToken',data.token);
    sessionStorage.setItem('adminPermissions',JSON.stringify(data.permissions||[]));
    sessionStorage.setItem('adminRole',data.role||'');
    $('#login').classList.add('hidden');$('#app').classList.remove('hidden');applyPermissions();await show('dashboard')
  }catch(e){
    sessionStorage.removeItem('adminToken');
    sessionStorage.removeItem('adminPermissions');
    sessionStorage.removeItem('adminRole');
    $('#loginError').textContent=humanError(e)
  }finally{$('#password').value='';$('#ownerKey').value=''}
}
async function logout(){
  try{await fetch('/admin/auth/logout',{method:'POST'})}catch{}
  sessionStorage.clear();
  location.href='/admin/ui'
}
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
  try{await views[name]();$('#status').textContent='به‌روز و همگام'}catch(e){$('#view').innerHTML='<div class="card" style="color:var(--danger)">'+esc(humanError(e))+'</div>';$('#status').textContent='خطا در دریافت اطلاعات'}
}
const views={
 dashboard:async()=>{
  const d=await api('/admin/dashboard');
  const items=[['کاربران',d.customers],['سرویس فعال',d.active_services],['سفارش در جریان',d.pending_orders],['پرداخت موفق',d.verified_payments],['درآمد تاییدشده',Number(d.verified_revenue).toLocaleString()+' IRT'],['تیکت باز',d.open_tickets],['اکانت پاسارگارد',d.pasarguard_accounts],['پلن‌ها',d.plans]];
  $('#view').innerHTML='<div class="page-head"><div><div class="section-eyebrow">Executive Overview</div><h1>داشبورد مدیریتی</h1></div></div><div class="grid">'+items.map(x=>'<div class="card"><div class="muted">'+esc(x[0])+'</div><div class="metric">'+esc(x[1])+'</div></div>').join('')+'</div>'
 },
 customers:async()=>{
  const rows=await api('/admin/customers?limit=100');
  $('#view').innerHTML='<h1>مشتریان</h1>'+table(rows,[['Telegram',r=>'<code>'+esc(r.telegram_user_id)+'</code>'],['Username',r=>esc(r.username)],['نام',r=>esc((r.first_name||'')+' '+(r.last_name||''))],['وضعیت',r=>r.blocked?'🚫 مسدود':'✅ فعال'],['عملیات',r=>(can('manage_users')?'<button type="button" class="btn small '+(r.blocked?'':'danger')+'" onclick="blockCustomer(\''+r.id+'\','+(!r.blocked)+',this)">'+(r.blocked?'رفع مسدودی':'مسدود')+'</button>':'')+(can('manage_wallets')?'<button type="button" class="btn small" onclick="walletCredit(\''+r.id+'\',this)">💰 کیف پول</button>':'')]])
 },
 plans:async()=>{
  const rows=await api('/admin/plans');
  $('#view').innerHTML='<h1>پلن‌ها</h1><div class="card"><div class="toolbar"><input id="pname" maxlength="128" placeholder="نام"><input id="pquota" type="number" min="0" step="0.01" inputmode="decimal" placeholder="حجم (گیگابایت، ۰ = نامحدود)"><input id="pprice" type="number" min="0" inputmode="numeric" placeholder="قیمت تومان"><button type="button" class="btn small" onclick="createPlan(this)">➕ ساخت</button></div><p class="muted">حجم را به گیگابایت وارد کنید. عدد صفر یعنی حجم نامحدود.</p></div>'+table(rows,[['نام',r=>esc(r.name)],['حجم (GB)',r=>formatQuotaGb(r.quota_bytes)],['قیمت',r=>Number(r.price_amount).toLocaleString()+' '+esc(r.currency)],['وضعیت',r=>r.active?'✅':'⛔'],['عملیات',r=>'<button type="button" class="btn small" onclick="togglePlan(\''+r.id+'\','+(!r.active)+',this)">'+(r.active?'غیرفعال':'فعال')+'</button><button type="button" class="btn small danger" onclick="deletePlan(\''+r.id+'\',this)">🗑 حذف</button>']])
 },
 discounts:async()=>{
  const rows=await api('/admin/discounts');
  $('#view').innerHTML='<h1>کدهای تخفیف</h1><div class="card"><div class="toolbar"><input id="dcode" maxlength="64" placeholder="کد"><select id="dkind"><option value="percent">درصدی</option><option value="fixed">مبلغ ثابت</option></select><input id="dvalue" type="number" min="1" inputmode="numeric" placeholder="مقدار"><input id="dmax" type="number" min="1" inputmode="numeric" placeholder="حداکثر استفاده"><button type="button" class="btn small" onclick="createDiscount(this)">➕ ساخت</button></div></div>'+table(rows,[['کد',r=>'<code>'+esc(r.code)+'</code>'],['نوع',r=>esc(r.kind)],['مقدار',r=>r.kind==='percent'?esc(r.value_percent)+'%':Number(r.value_amount||0).toLocaleString()],['استفاده',r=>esc(r.used_count)+' / '+esc(r.max_uses??'∞')],['وضعیت',r=>r.active?'✅':'⛔'],['عملیات',r=>'<button type="button" class="btn small" onclick="toggleDiscount(\''+r.id+'\','+(!r.active)+',this)">'+(r.active?'غیرفعال':'فعال')+'</button>']])
 },
 orders:async()=>{const rows=await api('/admin/orders?limit=100');$('#view').innerHTML='<h1>سفارش‌ها</h1>'+table(rows,[['ID',r=>'<code>'+esc(r.id.slice(0,8))+'</code>'],['نوع',r=>esc(r.kind)],['وضعیت',r=>esc(r.status)],['مبلغ',r=>Number(r.amount).toLocaleString()+' '+esc(r.currency)],['حجم',r=>formatQuotaGb(r.quota_bytes)],['عملیات',r=>'<button type="button" class="btn small" onclick="orderActionMenu(\''+r.id+'\',this)">⚙️ عملیات</button><div class="muted">'+esc(orderActionHtml(r))+'</div>']])},
 payments:async()=>{const rows=await api('/admin/payments?limit=100');$('#view').innerHTML='<h1>پرداخت‌ها</h1>'+table(rows,[['ID',r=>'<code>'+esc(r.id.slice(0,8))+'</code>'],['درگاه',r=>esc(r.provider)],['مبلغ',r=>Number(r.amount).toLocaleString()+' '+esc(r.currency)],['وضعیت',r=>esc(r.status)],['تراکنش',r=>esc(r.transaction_id)]])},
 paymentMethods:async()=>{
  const rows=await api('/admin/payment-methods');
  paymentMethodsCache=rows;editingPaymentMethod=null;
  const form='<div class="card"><h2>افزودن روش پرداخت</h2><p class="muted">ابتدا نوع روش پرداخت را انتخاب کنید.</p>'+
   '<div class="payment-category-picker" role="group" aria-label="نوع روش پرداخت">'+
   '<button type="button" class="payment-choice" data-payment-category="card" aria-pressed="false" onclick="selectPaymentCategory(\'card\',this)">💳 شماره کارت</button>'+
   '<button type="button" class="payment-choice" data-payment-category="gateway" aria-pressed="false" onclick="selectPaymentCategory(\'gateway\',this)">🌐 درگاه پرداخت</button></div>'+
   '<div id="paymentProviderPicker"></div><div id="paymentMethodForm" aria-live="polite"><div class="empty-state">یک گزینه را انتخاب کنید تا تنظیمات همان روش نمایش داده شود.</div></div>'+
   '<p class="muted">اطلاعات محرمانه در پاسخ API نمایش داده نمی‌شود و با کلید PAYMENT_CREDENTIALS_MASTER_KEY رمزگذاری می‌شود.</p></div>';
  $('#view').innerHTML='<h1>روش‌های پرداخت</h1>'+form+table(rows,[['نام',r=>esc(r.display_name)],['نوع',r=>esc(r.kind)],['شناسه',r=>'<code>'+esc(r.slug)+'</code>'],['حالت',r=>r.sandbox?'🧪 تست':'واقعی'],['اعتبارنامه',r=>r.kind==='manual_card'?'—':(r.credentials_configured?'✅ تنظیم شده':'❌ ناقص')],['وضعیت',r=>r.enabled?'✅ فعال':'⛔ غیرفعال'],['عملیات',r=>'<button type="button" class="btn small" onclick="togglePaymentMethod(\''+r.id+'\','+(!r.enabled)+',this)">'+(r.enabled?'غیرفعال':'فعال')+'</button><button type="button" class="btn small" onclick="editPaymentMethod(\''+r.id+'\',this)">✏️ ویرایش کامل</button><button type="button" class="btn small danger" onclick="deletePaymentMethod(\''+r.id+'\',this)">🗑 حذف</button>']])
 },
 pasarguardInstances:async()=>{
  const rows=await api('/admin/pasarguard/instances');
  const form='<div class="card"><h2>افزودن PasarGuard</h2><div class="toolbar">'+
   '<input id="pgName" maxlength="128" placeholder="نام">'+
   '<input id="pgUrl" inputmode="url" placeholder="https://panel.example.com">'+
   '<input id="pgEnv" maxlength="128" autocapitalize="none" placeholder="نام Env برای API Key">'+
   '<input id="pgRole" maxlength="128" placeholder="نام نقش نماینده">'+
   '<input id="pgWeight" type="number" min="1" max="10000" inputmode="numeric" value="100" placeholder="وزن">'+
   '<label><input id="pgEnabled" type="checkbox" checked> فعال</label>'+
   '<button type="button" class="btn small" onclick="createPasarguard(this)">➕ افزودن</button>'+
   '<button type="button" class="btn small" onclick="checkPasarguards(this)">🩺 Health Check</button></div>'+
   '<p class="muted">مقدار واقعی API Key در دیتابیس ذخیره نمی‌شود؛ فقط نام متغیر محیطی ثبت می‌شود.</p></div>';
  $('#view').innerHTML='<h1>PasarGuard Instances</h1>'+form+table(rows,[['نام',r=>esc(r.name)],['آدرس',r=>'<code>'+esc(r.base_url)+'</code>'],['وزن',r=>esc(r.weight)],['وضعیت',r=>r.enabled?'✅ فعال':'⛔ غیرفعال'],['Health',r=>r.last_health_ok===true?'🟢 سالم':(r.last_health_ok===false?'🔴 خطا':'—')],['Env',r=>'<code>'+esc(r.api_key_env_var||r.bearer_token_env_var||'')+'</code>'],['عملیات',r=>'<button type="button" class="btn small" onclick="togglePasarguard(\''+r.id+'\','+(!r.enabled)+',this)">'+(r.enabled?'غیرفعال':'فعال')+'</button><button type="button" class="btn small" onclick="editPasarguard(\''+r.id+'\',this)">✏️ ویرایش</button>']])
 },
 subscriptions:async()=>{const rows=await api('/admin/subscriptions?limit=100');$('#view').innerHTML='<h1>سرویس‌ها</h1>'+table(rows,[['ID',r=>'<code>'+esc(r.id.slice(0,8))+'</code>'],['وضعیت',r=>esc(r.status)],['حجم',r=>formatQuotaGb(r.quota_bytes)],['Auto Renew',r=>r.auto_renew?'✅':'—']])},
 support:async()=>{const rows=await api('/admin/support?limit=100');$('#view').innerHTML='<h1>پشتیبانی</h1>'+table(rows,[['ID',r=>'<code>'+esc(r.id.slice(0,8))+'</code>'],['موضوع',r=>esc(r.subject)],['وضعیت',r=>esc(r.status)],['به‌روزرسانی',r=>esc(r.updated_at)]])},
 staff:async()=>{const rows=await api('/admin/staff');$('#view').innerHTML='<h1>مدیران</h1>'+table(rows,[['Telegram',r=>esc(r.telegram_user_id)],['Username',r=>esc(r.username)],['نقش',r=>esc(r.role)],['وضعیت',r=>r.active?'✅':'⛔'],['عملیات',r=>'<button type="button" class="btn small" onclick="staffStatus(\''+r.id+'\','+(!r.active)+',this)">'+(r.active?'غیرفعال':'فعال')+'</button>']])},
 audit:async()=>{const rows=await api('/admin/audit?limit=100');$('#view').innerHTML='<h1>Audit Log</h1>'+table(rows,[['زمان',r=>esc(r.created_at)],['Actor',r=>esc(r.actor_type)+' '+esc(r.actor_id)],['عملیات',r=>esc(r.action)],['Entity',r=>esc(r.entity_type)+' '+esc(r.entity_id)]])}
};
function orderActionHtml(r){
 const actions=[];
 const unpaid=r.status==='pending'||r.status==='awaiting_payment';
 if(unpaid&&can('approve_payments'))actions.push('پرداخت');
 if(unpaid&&can('manage_orders'))actions.push('لغو');
 if((r.status==='paid'||r.status==='provisioning'||r.status==='failed')&&can('manage_pasarguard'))actions.push('اجرا');
 if(r.status==='completed'&&r.kind==='new'&&can('manage_pasarguard'))actions.push('همگام‌سازی حجم / صدور مجدد');
 return actions.length?actions.join(' / '):'—'
}
function requiredText(selector,label,min=1,max=Infinity){
 const value=$(selector).value.trim();
 if(value.length<min)throw new Error(label+' باید حداقل '+min+' نویسه باشد.');
 if(value.length>max)throw new Error(label+' نمی‌تواند بیشتر از '+max+' نویسه باشد.');
 return value
}
function integerInput(selector,label,min,max=Infinity,optional=false){
 const raw=$(selector).value.trim();
 if(!raw&&optional)return null;
 const value=Number(raw);
 if(!raw||!Number.isInteger(value)||value<min||value>max)throw new Error(label+' معتبر نیست.');
 return value
}
const GB_BYTES=1_000_000_000;
function quotaInputBytes(selector){
 const raw=$(selector).value.trim();
 const gigabytes=Number(raw);
 const bytes=Math.round(gigabytes*GB_BYTES);
 if(!raw||!Number.isFinite(gigabytes)||gigabytes<0||!Number.isSafeInteger(bytes))throw new Error('حجم گیگابایتی معتبر نیست.');
 return bytes
}
function formatQuotaGb(quotaBytes){
 const bytes=Number(quotaBytes);
 if(bytes===0)return 'نامحدود';
 const gigabytes=bytes/GB_BYTES;
 return gigabytes.toLocaleString('fa-IR',{maximumFractionDigits:2})+' GB'
}
function httpUrl(value){
 let parsed;
 try{parsed=new URL(value)}catch{throw new Error('آدرس PasarGuard معتبر نیست.')}
 if(!['http:','https:'].includes(parsed.protocol))throw new Error('آدرس PasarGuard باید با http یا https شروع شود.');
 return parsed.href.replace(/\/$/,'')
}
async function orderActionMenu(id,button){
 const choice=(prompt('عملیات: approve / reject / cancel / fulfill / sync / reissue','')||'').trim().toLowerCase();
 if(!choice)return;
 const map={approve:'approve-manual',reject:'reject-payment',cancel:'cancel',fulfill:'fulfill',sync:'fulfill',reissue:'reissue-credentials'};
 const endpoint=map[choice];
 if(!endpoint){notify('عملیات معتبر نیست.');return}
 if(['reject','cancel'].includes(choice)&&!confirm('این عملیات قابل بازگشت نیست. ادامه می‌دهید؟'))return;
 await runAction(button,async()=>{
   const result=await api('/admin/orders/'+id+'/'+endpoint,{method:'POST'});
   if(result.success===false)throw new Error(result.error_message||'عملیات کامل نشد.');
   await show('orders')
 },'عملیات سفارش انجام شد.')
}
async function blockCustomer(id,blocked,button){
 if(!confirm(blocked?'این مشتری مسدود شود؟':'مسدودی این مشتری برداشته شود؟'))return;
 await runAction(button,async()=>{
   await api('/admin/customers/'+id+'/block',{method:'PATCH',body:JSON.stringify({blocked})});
   await show('customers')
 },blocked?'مشتری مسدود شد.':'مسدودی مشتری برداشته شد.')
}
async function walletCredit(id,button){
 await runAction(button,async()=>{
   const wallet=await api('/admin/customers/'+id+'/wallet');
   const raw=prompt('موجودی فعلی: '+Number(wallet.balance).toLocaleString()+' '+wallet.currency+'\nمبلغ واریز را به تومان وارد کنید:');
   if(raw===null||!raw.trim())return;
   const amount=Number(raw.replace(/,/g,''));
   if(!Number.isInteger(amount)||amount<=0)throw new Error('مبلغ معتبر نیست.');
   if(!confirm('مبلغ '+amount.toLocaleString()+' '+wallet.currency+' به کیف پول واریز شود؟'))return;
   const key='web-wallet-'+crypto.randomUUID();
   const result=await api('/admin/customers/'+id+'/wallet/credit',{method:'POST',body:JSON.stringify({amount,currency:wallet.currency,idempotency_key:key,reference:'web-admin'})});
   notify('موجودی جدید: '+Number(result.balance).toLocaleString()+' '+result.currency,'success')
 })
}
async function togglePlan(id,active,button){
 if(!confirm(active?'این پلن فعال شود؟':'این پلن غیرفعال شود؟'))return;
 await runAction(button,async()=>{
   await api('/admin/plans/'+id,{method:'PATCH',body:JSON.stringify({is_active:active})});
   await show('plans')
 },active?'پلن فعال شد.':'پلن غیرفعال شد.')
}
async function deletePlan(id,button){
 if(!confirm('این پلن برای همیشه حذف شود؟ پلن دارای سفارش یا سرویس قابل حذف نیست.'))return;
 await runAction(button,async()=>{
   await api('/admin/plans/'+id,{method:'DELETE'});
   await show('plans')
 },'پلن حذف شد.')
}
async function createPlan(button){
 await runAction(button,async()=>{
   const body={
     name:requiredText('#pname','نام پلن',2,128),
     quota_bytes:quotaInputBytes('#pquota'),
     price_amount:integerInput('#pprice','قیمت',0),
     currency:'IRT'
   };
   await api('/admin/plans',{method:'POST',body:JSON.stringify(body)});
   await show('plans')
 },'پلن ساخته شد.')
}
async function createDiscount(button){
 await runAction(button,async()=>{
   const kind=$('#dkind').value;
   const value=integerInput('#dvalue','مقدار تخفیف',1,kind==='percent'?100:Infinity);
   const body={code:requiredText('#dcode','کد تخفیف',2,64),kind,max_uses:integerInput('#dmax','حداکثر استفاده',1,Infinity,true)};
   if(kind==='percent')body.value_percent=value;else body.value_amount=value;
   await api('/admin/discounts',{method:'POST',body:JSON.stringify(body)});
   await show('discounts')
 },'کد تخفیف ساخته شد.')
}
async function toggleDiscount(id,active,button){
 if(!confirm(active?'این کد تخفیف فعال شود؟':'این کد تخفیف غیرفعال شود؟'))return;
 await runAction(button,async()=>{
   await api('/admin/discounts/'+id,{method:'PATCH',body:JSON.stringify({is_active:active})});
   await show('discounts')
 },active?'کد تخفیف فعال شد.':'کد تخفیف غیرفعال شد.')
}
function paymentCredential(kind,value){
 if(!value)return null;
 if(kind==='zarinpal')return {merchant_id:value};
 if(kind==='zibal')return {merchant:value};
 return {api_key:value};
}
const paymentKindMeta={
 manual_card:{name:'کارت‌به‌کارت',slug:'card',secret:''},
 zarinpal:{name:'زرین‌پال',slug:'zarinpal',secret:'Merchant ID زرین‌پال'},
 idpay:{name:'آیدی‌پی',slug:'idpay',secret:'API Key آیدی‌پی'},
 zibal:{name:'زیبال',slug:'zibal',secret:'Merchant زیبال'},
 nextpay:{name:'نکست‌پی',slug:'nextpay',secret:'API Key نکست‌پی'}
};
function paymentMethodFields(kind,method=editingPaymentMethod){
 const meta=paymentKindMeta[kind];
 if(!meta)return '<div class="empty-state">روش پرداخت معتبر نیست.</div>';
 const editing=Boolean(method?.id),sameKind=editing&&method.kind===kind;
 const publicConfig=sameKind?(method.public_config||{}):{};
 const slug=editing?method.slug:meta.slug;
 const displayName=editing?method.display_name:meta.name;
 const sortOrder=editing?Number(method.sort_order||0):0;
 const enabledValue=editing&&method.enabled?' checked':'';
 const sandboxValue=sameKind&&method.sandbox?' checked':'';
 const credentialsConfigured=sameKind&&method.credentials_configured;
 const common='<input id="pmKind" type="hidden" value="'+esc(kind)+'">'+
  '<input id="pmMethodId" type="hidden" value="'+esc(editing?method.id:'')+'">'+
  '<input id="pmOriginalKind" type="hidden" value="'+esc(editing?method.kind:'')+'">'+
  '<input id="pmCredentialsConfigured" type="hidden" value="'+(credentialsConfigured?'1':'0')+'">'+
  '<label class="payment-field"><span>شناسه کوتاه</span><input id="pmSlug" maxlength="24" autocapitalize="none" value="'+esc(slug)+'" placeholder="مثل zarinpal"></label>'+
  '<label class="payment-field"><span>نام نمایشی</span><input id="pmName" maxlength="128" value="'+esc(displayName)+'" placeholder="نام نمایشی"></label>'+
  '<label class="payment-field"><span>ترتیب نمایش</span><input id="pmSort" type="number" min="-1000" max="1000" inputmode="numeric" value="'+esc(sortOrder)+'"></label>';
 const actions='<label><input id="pmEnabled" type="checkbox"'+enabledValue+'> فعال</label>'+
  '<button type="button" class="btn small" onclick="savePaymentMethod(this)">'+(editing?'💾 ذخیره تغییرات':'➕ ذخیره '+esc(meta.name))+'</button>'+
  (editing?'<button type="button" class="btn small" onclick="cancelPaymentMethodEdit()">انصراف</button>':'');
 const hint=editing?'<p class="payment-edit-hint">همه فیلدها قابل ویرایش‌اند. برای تغییر نوع، گزینه شماره کارت یا یکی از درگاه‌های بالا را انتخاب کنید.</p>':'';
 const title=(editing?'ویرایش کامل ':'تنظیمات ')+esc(meta.name);
 if(kind==='manual_card')return '<div class="payment-form-panel"><h3>'+title+'</h3>'+hint+'<div class="toolbar">'+common+
  '<label class="payment-field"><span>شماره کارت</span><input id="pmCard" inputmode="numeric" maxlength="19" autocomplete="cc-number" value="'+esc(publicConfig.card_number||'')+'" placeholder="شماره کارت ۱۶ رقمی"></label>'+
  '<label class="payment-field"><span>نام صاحب کارت</span><input id="pmHolder" autocomplete="cc-name" value="'+esc(publicConfig.card_holder||'')+'" placeholder="نام صاحب کارت"></label>'+
  '<label class="payment-field"><span>نام بانک</span><input id="pmBank" value="'+esc(publicConfig.bank_name||'')+'" placeholder="اختیاری"></label>'+
  '<label class="payment-field"><span>شماره شبا</span><input id="pmIban" value="'+esc(publicConfig.iban||'')+'" placeholder="اختیاری"></label>'+actions+'</div></div>';
 const sandbox=kind==='nextpay'?'':'<label><input id="pmSandbox" type="checkbox"'+sandboxValue+'> تست / Sandbox</label>';
 const secretHint=credentialsConfigured?'کلید جدید (خالی = بدون تغییر)':meta.secret;
 return '<div class="payment-form-panel"><h3>'+title+'</h3>'+hint+'<div class="toolbar">'+common+
  '<label class="payment-field"><span>'+esc(meta.secret)+'</span><input id="pmSecret" type="password" autocomplete="new-password" placeholder="'+esc(secretHint)+'"></label>'+sandbox+actions+'</div></div>'
}
function selectPaymentCategory(category,button){
 document.querySelectorAll('[data-payment-category]').forEach(item=>{
   const active=item===button;item.classList.toggle('is-active',active);item.setAttribute('aria-pressed',String(active))
 });
 const providers=$('#paymentProviderPicker'),form=$('#paymentMethodForm');
 if(category==='card'){
   providers.innerHTML='';form.innerHTML=paymentMethodFields('manual_card');return
 }
 providers.innerHTML='<div class="payment-provider-picker" role="group" aria-label="انتخاب درگاه">'+
  '<button type="button" class="payment-choice" data-payment-kind="zarinpal" onclick="selectPaymentKind(\'zarinpal\',this)">زرین‌پال</button>'+
  '<button type="button" class="payment-choice" data-payment-kind="idpay" onclick="selectPaymentKind(\'idpay\',this)">آیدی‌پی</button>'+
  '<button type="button" class="payment-choice" data-payment-kind="zibal" onclick="selectPaymentKind(\'zibal\',this)">زیبال</button>'+
  '<button type="button" class="payment-choice" data-payment-kind="nextpay" onclick="selectPaymentKind(\'nextpay\',this)">نکست‌پی</button></div>';
 form.innerHTML='<div class="empty-state">درگاه موردنظر را انتخاب کنید.</div>'
}
function selectPaymentKind(kind,button){
 if(!paymentKindMeta[kind]||kind==='manual_card')return;
 document.querySelectorAll('.payment-provider-picker .payment-choice').forEach(item=>item.classList.toggle('is-active',item===button));
 $('#paymentMethodForm').innerHTML=paymentMethodFields(kind)
}
function paymentMethodPayload(){
 const kind=$('#pmKind').value;
 const methodId=$('#pmMethodId')?.value||'';
 const originalKind=$('#pmOriginalKind')?.value||'';
 const credentialsConfigured=$('#pmCredentialsConfigured')?.value==='1';
 const slug=requiredText('#pmSlug','شناسه روش پرداخت',2,24).toLowerCase();
 if(!/^[a-z0-9_-]+$/.test(slug))throw new Error('شناسه فقط می‌تواند شامل حروف انگلیسی، عدد، خط تیره و زیرخط باشد.');
 const displayName=requiredText('#pmName','نام نمایشی',1,128);
 const sandbox=$('#pmSandbox')?.checked||false;
 const publicConfig={};
 let secret=$('#pmSecret')?.value.trim()||'';
 if(kind==='manual_card'){
   const card=$('#pmCard').value.replace(/[\s-]/g,'');
   if(!/^\d{16}$/.test(card))throw new Error('شماره کارت باید دقیقاً ۱۶ رقم باشد.');
   publicConfig.card_number=card;
   publicConfig.card_holder=requiredText('#pmHolder','نام صاحب کارت',1,128);
   if($('#pmBank').value.trim())publicConfig.bank_name=$('#pmBank').value.trim();
   if($('#pmIban').value.trim())publicConfig.iban=$('#pmIban').value.trim();
   secret=''
 }else{
   if(kind==='nextpay'&&sandbox)throw new Error('حالت Sandbox برای NextPay پشتیبانی نمی‌شود.');
   const canKeepSecret=Boolean(methodId)&&originalKind===kind&&credentialsConfigured;
   if(!secret&&!(kind==='zibal'&&sandbox)&&!canKeepSecret)throw new Error('Merchant ID یا API Key را وارد کنید.');
 }
 let credentials=paymentCredential(kind,secret);
 if(!secret&&kind==='zibal'&&sandbox&&!(methodId&&originalKind===kind&&credentialsConfigured))credentials={};
 return {methodId,body:{
   slug,kind,display_name:displayName,is_enabled:$('#pmEnabled').checked,sandbox,
   sort_order:integerInput('#pmSort','ترتیب نمایش',-1000,1000),
   public_config:publicConfig,credentials
 }}
}
async function savePaymentMethod(button){
 const editing=Boolean($('#pmMethodId')?.value);
 await runAction(button,async()=>{
   const values=paymentMethodPayload();
   const path=values.methodId?'/admin/payment-methods/'+values.methodId:'/admin/payment-methods';
   await api(path,{method:values.methodId?'PUT':'POST',body:JSON.stringify(values.body)});
   if($('#pmSecret'))$('#pmSecret').value='';
   await show('paymentMethods')
 },editing?'روش پرداخت کامل ویرایش شد.':'روش پرداخت ذخیره شد.')
}
async function togglePaymentMethod(id,enabled,button){
 if(!confirm(enabled?'این روش پرداخت فعال شود؟':'این روش پرداخت غیرفعال شود؟'))return;
 await runAction(button,async()=>{
   const rows=await api('/admin/payment-methods'),r=rows.find(x=>x.id===id);if(!r)throw new Error('روش پرداخت پیدا نشد.');
   const body={slug:r.slug,kind:r.kind,display_name:r.display_name,is_enabled:enabled,sandbox:r.sandbox,sort_order:r.sort_order,public_config:r.public_config,credentials:null};
   await api('/admin/payment-methods/'+id,{method:'PUT',body:JSON.stringify(body)});
   await show('paymentMethods')
 },enabled?'روش پرداخت فعال شد.':'روش پرداخت غیرفعال شد.')
}
async function editPaymentMethod(id,button){
 const method=paymentMethodsCache.find(item=>item.id===id);
 if(!method){notify('روش پرداخت پیدا نشد.');return}
 editingPaymentMethod=method;
 const category=method.kind==='manual_card'?'card':'gateway';
 const categoryButton=document.querySelector('[data-payment-category="'+category+'"]');
 selectPaymentCategory(category,categoryButton);
 if(category==='gateway'){
   const kindButton=document.querySelector('[data-payment-kind="'+method.kind+'"]');
   if(kindButton)selectPaymentKind(method.kind,kindButton)
 }
 $('#paymentMethodForm')?.scrollIntoView({behavior:'smooth',block:'center'})
}
function cancelPaymentMethodEdit(){
 editingPaymentMethod=null;
 document.querySelectorAll('[data-payment-category],.payment-provider-picker .payment-choice').forEach(item=>item.classList.remove('is-active'));
 $('#paymentProviderPicker').innerHTML='';
 $('#paymentMethodForm').innerHTML='<div class="empty-state">یک گزینه را انتخاب کنید تا تنظیمات همان روش نمایش داده شود.</div>'
}
async function deletePaymentMethod(id,button){
 const method=paymentMethodsCache.find(item=>item.id===id);
 const name=method?.display_name||'این روش پرداخت';
 if(!confirm('روش پرداخت «'+name+'» برای همیشه حذف شود؟ روش دارای تراکنش قابل حذف نیست.'))return;
 await runAction(button,async()=>{
   await api('/admin/payment-methods/'+id,{method:'DELETE'});
   await show('paymentMethods')
 },'روش پرداخت حذف شد.')
}
async function createPasarguard(button){
 await runAction(button,async()=>{
   const body={
     name:requiredText('#pgName','نام PasarGuard',2,128),
     base_url:httpUrl(requiredText('#pgUrl','آدرس PasarGuard',8,2048)),
     api_key_env_var:requiredText('#pgEnv','نام متغیر محیطی API Key',1,128),
     bearer_token_env_var:null,
     reseller_role_name:$('#pgRole').value.trim()||null,
     reseller_role_id:null,
     weight:integerInput('#pgWeight','وزن',1,10000),
     is_enabled:$('#pgEnabled').checked
   };
   await api('/admin/pasarguard/instances',{method:'POST',body:JSON.stringify(body)});
   await show('pasarguardInstances')
 },'PasarGuard افزوده شد.')
}
async function togglePasarguard(id,enabled,button){
 if(!confirm(enabled?'این PasarGuard فعال شود؟':'این PasarGuard غیرفعال شود؟'))return;
 await runAction(button,async()=>{
   const rows=await api('/admin/pasarguard/instances'),r=rows.find(x=>x.id===id);if(!r)throw new Error('PasarGuard پیدا نشد.');
   const body={name:r.name,base_url:r.base_url,api_key_env_var:r.api_key_env_var,bearer_token_env_var:r.bearer_token_env_var,reseller_role_name:r.reseller_role_name,reseller_role_id:r.reseller_role_id,weight:r.weight,is_enabled:enabled};
   await api('/admin/pasarguard/instances/'+id,{method:'PATCH',body:JSON.stringify(body)});
   await show('pasarguardInstances')
 },enabled?'PasarGuard فعال شد.':'PasarGuard غیرفعال شد.')
}
async function editPasarguard(id,button){
 await runAction(button,async()=>{
   const rows=await api('/admin/pasarguard/instances'),r=rows.find(x=>x.id===id);if(!r)throw new Error('PasarGuard پیدا نشد.');
   const name=prompt('نام',r.name);if(name===null)return;
   const url=prompt('Base URL',r.base_url);if(url===null)return;
   const env=prompt('نام Env برای API Key',r.api_key_env_var||'');if(env===null)return;
   const role=prompt('نام نقش نماینده',r.reseller_role_name||'');if(role===null)return;
   const weightRaw=prompt('وزن',String(r.weight));if(weightRaw===null)return;
   const weight=Number(weightRaw);
   if(name.trim().length<2)throw new Error('نام PasarGuard باید حداقل ۲ نویسه باشد.');
   if(!env.trim())throw new Error('نام متغیر محیطی API Key الزامی است.');
   if(!Number.isInteger(weight)||weight<1||weight>10000)throw new Error('وزن معتبر نیست.');
   const body={name:name.trim(),base_url:httpUrl(url.trim()),api_key_env_var:env.trim(),bearer_token_env_var:null,reseller_role_name:role.trim()||null,reseller_role_id:r.reseller_role_id,weight,is_enabled:r.enabled};
   await api('/admin/pasarguard/instances/'+id,{method:'PATCH',body:JSON.stringify(body)});
   await show('pasarguardInstances');notify('PasarGuard ویرایش شد.','success')
 })
}
async function checkPasarguards(button){
 await runAction(button,async()=>{
   const rows=await api('/admin/pasarguard/instances/health',{method:'POST'});
   const ok=rows.filter(x=>x.healthy).length;
   await show('pasarguardInstances');
   notify('Health Check: '+ok+' از '+rows.length+' سالم','success')
 })
}
async function staffStatus(id,active,button){
 if(!confirm(active?'این مدیر فعال شود؟':'این مدیر غیرفعال شود؟'))return;
 await runAction(button,async()=>{
   await api('/admin/staff/'+id+'/status',{method:'PATCH',body:JSON.stringify({active})});
   await show('staff')
 },active?'مدیر فعال شد.':'مدیر غیرفعال شد.')
}
async function restoreSession(){
  const params=new URLSearchParams(location.search);
  if(params.get('login_error')==='1'){
    $('#loginError').textContent='نام کاربری یا رمز عبور صحیح نیست.';
  }
  try{
    const headers={};
    if(token())headers['Authorization']='Bearer '+token();
    const response=await fetch('/admin/auth/me',{headers});
    if(!response.ok){
      sessionStorage.removeItem('adminToken');
      sessionStorage.removeItem('adminPermissions');
      sessionStorage.removeItem('adminRole');
      $('#app').classList.add('hidden');
      $('#login').classList.remove('hidden');
      return
    }
    const me=await response.json();
    sessionStorage.setItem('adminPermissions',JSON.stringify(me.permissions||[]));
    sessionStorage.setItem('adminRole',me.role||'');
    $('#login').classList.add('hidden');
    $('#app').classList.remove('hidden');
    applyPermissions();
    show('dashboard');
    if(location.search)history.replaceState({},'',location.pathname);
  }catch(error){
    $('#app').classList.add('hidden');
    $('#login').classList.remove('hidden');
    $('#loginError').textContent='برقراری ارتباط با پنل ممکن نشد؛ دوباره تلاش کنید.'
  }
}
const loginForm=$('#loginForm');
if(loginForm){
  loginForm.addEventListener('submit',event=>{
    login(event);
  });
}
restoreSession()
"""



@router.get("/ui.js", response_class=Response)
async def admin_ui_javascript() -> Response:
    response = Response(_ADMIN_JS, media_type="application/javascript")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@router.get("", response_class=RedirectResponse)
async def admin_root() -> RedirectResponse:
    return RedirectResponse(url="/admin/ui", status_code=307)


@router.get("/ui", response_class=HTMLResponse)
async def admin_ui(request: Request) -> HTMLResponse:
    html = _ADMIN_HTML
    token = request.cookies.get("panelprimepasar_admin_session")
    if token:
        settings = get_settings()
        secret = settings.admin_panel_session_secret or settings.admin_panel_api_key
        if secret is not None:
            try:
                verify_session_token(
                    token,
                    secret=secret.get_secret_value(),
                )
            except WebAdminSecurityError:
                pass
            else:
                html = html.replace(
                    '<section id="login">',
                    '<section id="login" class="hidden">',
                    1,
                ).replace(
                    '<section id="app" class="hidden">',
                    '<section id="app">',
                    1,
                )

    response = HTMLResponse(html)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
