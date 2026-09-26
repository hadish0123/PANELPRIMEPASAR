from panelprimepasar.routers.admin import router as admin_router
from panelprimepasar.routers.admin_ops import router as admin_ops_router
from panelprimepasar.routers.customer import router as customer_router
from panelprimepasar.routers.discounts import router as discounts_router
from panelprimepasar.routers.services import router as services_router
from panelprimepasar.routers.wallet import router as wallet_router
from panelprimepasar.routers.support import router as support_router

__all__ = [
    "admin_ops_router",
    "admin_router",
    "customer_router",
    "discounts_router",
    "services_router",
    "support_router",
]
