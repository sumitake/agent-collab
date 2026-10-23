"""A read caller for independent review against sdk.py."""


def read_secrets(client):
    return (
        client.get("54fbb187-3626-4832-b581-2f6fc85cc518"),
        client.list("2b96f0ed-8c6c-45bd-832c-b88fcc4eae07"),
    )
