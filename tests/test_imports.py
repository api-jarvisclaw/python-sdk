def test_imports():
    from jarvisclaw import ChatClient, VideoClient, ImageClient, AudioClient, SearchClient, MarketplaceClient
    assert ChatClient is not None
    assert VideoClient is not None


def test_base_client_init():
    from jarvisclaw import ChatClient
    import os
    os.environ["JARVISCLAW_API_KEY"] = "sk-test"
    client = ChatClient()
    assert client is not None
    del os.environ["JARVISCLAW_API_KEY"]
