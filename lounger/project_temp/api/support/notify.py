from lounger.integrations.dingtalk import register_dingtalk_integration


def register_notifications(webhook_url: str, secret: str, title: str = "Lounger Auto Test Summary") -> None:
    """
    Official recommended notification registration helper.
    """
    register_dingtalk_integration(
        webhook_url=webhook_url,
        secret=secret,
        title=title,
    )
