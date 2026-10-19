"""A second read caller for independent review against sdk.py."""

from uuid import UUID


def read_secrets(client):
    return (
        client.get(UUID("54fbb187-3626-4832-b581-2f6fc85cc518")),
        client.list(UUID("2b96f0ed-8c6c-45bd-832c-b88fcc4eae07")),
    )
