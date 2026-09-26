"""Local bootstrap: python -m panelprimepasar.manage create-admin --username owner."""

import argparse
import asyncio
import getpass

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from panelprimepasar.admin_schemas import AdminInput
from panelprimepasar.db import SessionFactory, engine
from panelprimepasar.models import WebAdmin
from panelprimepasar.security.auth import hash_password
from panelprimepasar.security.permissions import AdminRole
from panelprimepasar.services.audit import record_audit_event


async def create_admin(body: AdminInput) -> None:
    try:
        async with SessionFactory() as session:
            admin = WebAdmin(
                username=body.username, password_hash=hash_password(body.password), role=body.role
            )
            session.add(admin)
            await session.flush()
            await record_audit_event(
                session,
                actor_type="local_cli",
                actor_id=None,
                action="admin.created",
                entity_type="admin",
                entity_id=str(admin.id),
                metadata={"role": body.role.value},
            )
            await session.commit()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="PANELPRIMEPASAR administrator bootstrap")
    parser.add_argument("command", choices=["create-admin"])
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", choices=list(AdminRole), default=AdminRole.OWNER)
    args = parser.parse_args()
    password = getpass.getpass("Password (12-128 characters): ")
    if password != getpass.getpass("Repeat password: "):
        parser.exit(1, "Passwords do not match.\n")
    try:
        body = AdminInput(username=args.username, role=args.role, password=password)
        asyncio.run(create_admin(body))
    except ValidationError:
        parser.exit(1, "Invalid username, role, or password length.\n")
    except IntegrityError:
        parser.exit(1, "Username already exists.\n")
    print("Administrator created.")


if __name__ == "__main__":
    main()
