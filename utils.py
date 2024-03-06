import aioconsole
import asyncio
import time

from datetime import datetime, timedelta

import gmail


def input(prompt):
    return asyncio.run(aioconsole.ainput(prompt))

async def from_input(prompt):
    return await aioconsole.ainput(prompt)

async def get_otp(after_ts):
    done, _ = await asyncio.wait(
            (asyncio.create_task(gmail.get_otp(after_ts)),
             asyncio.create_task(from_input('Enter otp\n>>> '))),
            return_when=asyncio.FIRST_COMPLETED
    )
    return list(done)[0].result()
