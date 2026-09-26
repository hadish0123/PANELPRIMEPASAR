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
