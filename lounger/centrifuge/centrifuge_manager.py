import asyncio
import threading

from lounger.centrifuge.centrifuge_client_factory import ClientRole, create_client, subscribe_to_shop_channel
from lounger.commons.load_config import global_test_config
from lounger.log import log
from lounger.utils.cache import cache


class BackgroundLoop:
    """
    Global background event loop (never blocking)
    """

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        t = threading.Thread(target=self.start, daemon=True)
        t.start()

    def start(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro):
        """Submit coroutine to background loop for execution across threads"""
        return asyncio.run_coroutine_threadsafe(coro, self.loop)


bg_loop = BackgroundLoop()


class CentrifugeClientManager:
    """
    Centrifuge Client Manager
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._clients = {}
        return cls._instance

    def get_client(self, client_type: str):
        return self._clients.get(client_type.lower())

    def set_client(self, client_type: str, client):
        self._clients[client_type.lower()] = client

    def has_clients(self):
        return len(self._clients) > 0


client_manager = CentrifugeClientManager()


async def centrifuge_send_message(client, *args, **kwargs):
    message = kwargs.get("message")
    if not message:
        raise ValueError("Missing required 'message' parameter")

    data = {
        "content": f"<p><span style=\"white-space: pre-wrap;\">{message}</span></p>",
        "message_type": "text",
        "conversation_id": client.conversation_id,
        "shop_id": client.shop_id,
        "receiver_user_ids": [""],
    }

    await client.rpc("send_message", data)


async def centrifuge_custom_method(client, *args, **kwargs):
    data = kwargs.get("data")
    return await client.rpc(kwargs["custom_method"], data)


# Initialize clients (must run on background loop)
async def _async_init_clients():
    config = _get_centrifuge_config()

    # create C client role
    c_client = create_client(
        ClientRole.C, config["shop_id"], config["conversation_id"],
        config["url"], config["default_headers"], config["c_headers"]
    )

    # create B client role
    b_client = create_client(
        ClientRole.B, config["shop_id"], config["conversation_id"],
        config["url"], config["default_headers"], config["c_headers"]
    )
    b_client.conversation_id = c_client.conversation_id

    # Subscribe
    await subscribe_to_shop_channel(c_client, config["shop_id"])
    await subscribe_to_shop_channel(b_client, config["shop_id"])

    # Save
    client_manager.set_client(ClientRole.C, c_client)
    client_manager.set_client(ClientRole.B, b_client)

    log.info("Centrifuge clients initialized")


def _get_centrifuge_config():
    url = global_test_config("url")
    return {
        "url": url,
        "shop_id": cache.get("shop_id"),
        "conversation_id": cache.get("conversation_id"),
        "default_headers": cache.get("default_headers"),
        "c_headers": cache.get("c_headers"),
    }


def _initialize_clients():
    """Initialize only once, and must be completed in the background thread loop"""
    future = bg_loop.submit(_async_init_clients())
    future.result()  # Wait for initialization to complete


# External unified API (non-blocking, no run_until_complete)
def send_centrifuge(role, action, *args, **kwargs):
    # Initialization
    if not client_manager.has_clients():
        _initialize_clients()

    client = client_manager.get_client(role)

    if action == "send_message":
        bg_loop.submit(centrifuge_send_message(client, *args, **kwargs))
    elif action == "disconnect":
        bg_loop.submit(client.disconnect())
    elif action == "custom":
        bg_loop.submit(centrifuge_custom_method(client, *args, **kwargs))
    else:
        raise ValueError(f"Unsupported action: {action}")

    return True
