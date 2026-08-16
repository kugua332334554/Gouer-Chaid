import asyncio
import logging
from aiohttp import web
from telethon import TelegramClient, errors
from telethon.tl.functions.payments import GetSavedStarGiftsRequest

API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
SESSION_FILE = 'acc.session'
PORT = 9191

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
lock = asyncio.Lock()

async def get_user_id(username: str) -> int:
    if username.startswith('@'):
        username = username[1:]
    try:
        entity = await client.get_entity(username)
        return entity.id
    except errors.UsernameNotOccupiedError:
        raise ValueError(f"Username '{username}' not found.")
    except errors.FloodWaitError as e:
        raise ValueError(f"Flood wait: {e.seconds} seconds.")
    except Exception as e:
        raise ValueError(f"Telethon error: {str(e)}")


async def get_user_full(username: str) -> dict:
    if username.startswith('@'):
        username = username[1:]
    try:
        entity = await client.get_entity(username)
    except errors.UsernameNotOccupiedError:
        raise ValueError(f"Username '{username}' not found.")
    except errors.FloodWaitError as e:
        raise ValueError(f"Flood wait: {e.seconds} seconds.")
    except Exception as e:
        raise ValueError(f"Telethon error: {str(e)}")

    usernames = []
    if getattr(entity, 'username', None):
        usernames.append(entity.username)
    for u in getattr(entity, 'usernames', None) or []:
        name = getattr(u, 'username', None)
        if name and name not in usernames:
            usernames.append(name)

    gifts = []
    try:
        res = await client(GetSavedStarGiftsRequest(peer=entity, offset='', limit=100))
        for saved in res.gifts:
            gift = getattr(saved, 'gift', None)
            title = getattr(gift, 'title', None)
            if title:
                gifts.append(title)
    except Exception as e:
        logger.warning(f"get gifts failed for {username}: {e}")

    return {
        "user_id": entity.id,
        "premium": bool(getattr(entity, 'premium', False)),
        "phone": getattr(entity, 'phone', None),
        "usernames": usernames,
        "gifts": gifts,
    }


async def handle(request: web.Request) -> web.Response:
    username = request.query.get('username')
    if not username:
        return web.json_response({'error': 'Missing "username" query parameter.'}, status=400)
    async with lock:
        logger.info(f"Processing username: {username}")
        try:
            user_id = await get_user_id(username)
            logger.info(f"Found user {username} -> ID {user_id}")
            return web.json_response({'username': username, 'user_id': user_id})
        except ValueError as e:
            logger.warning(f"Failed: {e}")
            return web.json_response({'error': str(e)}, status=404)
        except Exception as e:
            logger.exception("Unexpected error")
            return web.json_response({'error': 'Internal server error'}, status=500)

async def handle_getuserfull(request: web.Request) -> web.Response:
    username = request.query.get('username')
    if not username:
        return web.json_response({'error': 'Missing "username" query parameter.'}, status=400)
    async with lock:
        logger.info(f"getuserfull for: {username}")
        try:
            data = await get_user_full(username)
            logger.info(f"getuserfull {username} -> id={data['user_id']} gifts={len(data['gifts'])}")
            return web.json_response(data)
        except ValueError as e:
            logger.warning(f"getuserfull failed: {e}")
            return web.json_response({'error': str(e)}, status=404)
        except Exception as e:
            logger.exception("getuserfull unexpected error")
            return web.json_response({'error': 'Internal server error'}, status=500)


async def init_app() -> web.Application:
    app = web.Application()
    app.router.add_get('/', handle)
    app.router.add_get('/getuserfull', handle_getuserfull)
    return app

async def main():
    await client.start()
    logger.info("Telegram client started.")
    try:
        me = await client.get_me()
        logger.info(f"Logged in as: @{me.username} (id: {me.id})")
    except Exception as e:
        logger.error(f"Failed to get current user: {e}")
        return
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"HTTP server running on port {PORT}")
    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
