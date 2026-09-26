from panelprimepasar.admin_panel import PlanCreateRequest
from panelprimepasar.admin_ui import _ADMIN_HTML, _ADMIN_JS


def test_mobile_layout_keeps_logout_and_form_actions_available() -> None:
    assert '.nav-label,.side-footer{display:none}' not in _ADMIN_HTML
    assert 'class="btn danger side-logout"' in _ADMIN_HTML
    assert '.toolbar > .btn.small{width:100%!important' in _ADMIN_HTML
    assert '<meta name="viewport" content="width=device-width,initial-scale=1">' in _ADMIN_HTML


def test_admin_actions_have_visible_error_feedback() -> None:
    assert '<div id="notice" class="notice hidden"' in _ADMIN_HTML
    assert 'function humanError(value)' in _ADMIN_JS
    assert "window.addEventListener('unhandledrejection'" in _ADMIN_JS
    assert "throw new Error(humanError(detail))" in _ADMIN_JS


def test_login_clears_secret_fields_after_each_attempt() -> None:
    assert "finally{$('#password').value='';$('#ownerKey').value=''}" in _ADMIN_JS


def test_mutating_controls_use_confirmations_and_action_guard() -> None:
    assert 'async function runAction(button,task,successMessage=' in _ADMIN_JS
    assert "if(!confirm(blocked?'این مشتری مسدود شود؟'" in _ADMIN_JS
    assert "if(!confirm(active?'این مدیر فعال شود؟'" in _ADMIN_JS


def test_plan_form_uses_gigabytes_without_day_limit() -> None:
    assert 'placeholder="حجم (گیگابایت، ۰ = نامحدود)"' in _ADMIN_JS
    assert "const GB_BYTES=1_000_000_000" in _ADMIN_JS
    assert "quota_bytes:quotaInputBytes('#pquota')" in _ADMIN_JS
    assert "formatQuotaGb(r.quota_bytes)" in _ADMIN_JS
    assert 'id="pdays"' not in _ADMIN_JS


def test_completed_orders_offer_quota_sync_without_password_rotation() -> None:
    assert "actions.push('همگام‌سازی حجم / صدور مجدد')" in _ADMIN_JS
    assert "sync:'fulfill'" in _ADMIN_JS


def test_plan_api_accepts_zero_as_unlimited() -> None:
    payload = PlanCreateRequest(
        name="نامحدود",
        quota_bytes=0,
        price_amount=100_000,
    )
    assert payload.quota_bytes == 0
    assert "validity_days" not in PlanCreateRequest.model_fields
