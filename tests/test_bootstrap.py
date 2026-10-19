import pytest
from app.core.bootstrap import bootstrap_admin
from app.database import db_manager


@pytest.mark.asyncio
async def test_admin_bootstrap_idempotent():
    db = db_manager.db
    # Clean users
    await db.users.delete_many({})

    # 1. Run bootstrap first time
    await bootstrap_admin(db)
    admins = await db.users.find({"role": "ADMIN"}).to_list(length=10)
    assert len(admins) == 1
    assert admins[0]["email"] == "admin@clararosa.pt"
    first_pwd_hash = admins[0]["password_hash"]

    # 2. Run bootstrap second and third time
    await bootstrap_admin(db)
    await bootstrap_admin(db)

    admins_after = await db.users.find({"role": "ADMIN"}).to_list(length=10)
    assert len(admins_after) == 1
    assert admins_after[0]["password_hash"] == first_pwd_hash
