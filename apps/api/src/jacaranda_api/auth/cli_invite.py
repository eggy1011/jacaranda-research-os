from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from jacaranda_api.auth.security import digest, new_invite_code
from jacaranda_api.config import get_settings
from jacaranda_api.db.engine import create_engine, create_session_factory
from jacaranda_api.db.models import Invite


async def _create(role: str) -> str:
    engine = create_engine(get_settings().database_url)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            code = new_invite_code()
            session.add(Invite(code_hash=digest(code), role=role))
            await session.commit()
            return code
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    """Bootstrap invites from the server side (e.g. the first admin) without
    ever handling a password: the code is printed once and only its hash is
    stored. Run inside the api/worker container: jacaranda-invite --role admin
    """
    parser = argparse.ArgumentParser(description="Create an invite code")
    parser.add_argument("--role", choices=["member", "reviewer", "admin"], default="member")
    args = parser.parse_args(argv)
    code = asyncio.run(_create(args.role))
    print(code)


if __name__ == "__main__":
    main()
