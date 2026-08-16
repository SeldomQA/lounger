from lounger.centrifuge.centrifuge_client import (
    CentrifugeClient,
    ClientEventLoggerHandler,
    SubscriptionEventLoggerHandler,
)
from lounger.log import log


class ClientRole:
    B = "B"  # business
    C = "C"  # consumer


async def subscribe_to_shop_channel(client: CentrifugeClient, shop_id: str) -> None:
    """
    Subscribe to the shop channel using the given shop_id.
    This is a business-specific method that should be in the business layer.
    
    :param client: CentrifugeClient instance to use for connection.
    :param shop_id: The shop identifier to subscribe to.
    """
    sub = client.new_subscription(
        channel=f"shop:{shop_id}",
        events=SubscriptionEventLoggerHandler(),
    )
    await client.connect()
    await sub.subscribe()
    log.info(f"Centrifuge connection established to shop: {shop_id}")


def create_client(
        role: str,
        shop_id: str,
        conversation_id: str,
        websocket_url: str,
        default_headers: dict,
        c_headers: dict):
    """
    Create and configure a WebSocket client for B or C end.
    All business data (shop_id, tokens, etc.) is passed in explicitly.
    """
    params: dict = {
        "address": websocket_url,
        "events": ClientEventLoggerHandler(),
        "headers": {"x-livechat-token": ''},
        "use_protobuf": False,
    }

    if role == ClientRole.B:
        token = default_headers['Authorization']
        livechat_token = default_headers['x-livechat-token']
        params['headers']['x-livechat-token'] = livechat_token
        params['token'] = token
        log.info(f"🔷 B-end uses token - Auth: {token[:20]}..., x-livechat: {livechat_token[:20]}...")

    elif role == ClientRole.C:
        livechat_token = c_headers['x-livechat-token']
        params['headers']['x-livechat-token'] = livechat_token
        log.info(f"🔶 C-end uses x-livechat-token: {livechat_token[:20]}...")

    client = CentrifugeClient(**params)
    client.conversation_id = conversation_id
    client.shop_id = shop_id
    return client
