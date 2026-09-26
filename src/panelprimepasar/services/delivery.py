from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from panelprimepasar.config import Settings
from panelprimepasar.models import Customer
from panelprimepasar.services.provisioning import ProvisioningOutcome


async def deliver_credentials(
    *,
    bot: Bot,
    settings: Settings,
    customer: Customer,
    outcome: ProvisioningOutcome,
) -> bool:
    credentials = outcome.credentials
    if credentials is None:
        return False
    panel_url = str(settings.pasarguard_base_url).rstrip("/")
    message = (
        "<b>پنل نمایندگی شما آماده است.</b>\n\n"
        f"آدرس پنل: <code>{escape(panel_url)}</code>\n"
        f"نام کاربری: <code>{escape(credentials.username)}</code>\n"
        f"رمز عبور: <code>{escape(credentials.password)}</code>\n\n"
        "رمز را در محل امن نگه‌داری کنید."
    )
    try:
        await bot.send_message(customer.telegram_user_id, message)
    except TelegramAPIError:
        return False
    return True
