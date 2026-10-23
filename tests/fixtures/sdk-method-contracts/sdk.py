"""Synthetic SDK with deliberately different read and create contracts."""

import json
from uuid import UUID


class Secrets:
    def _command(self, operation: str, arguments: dict) -> str:
        return json.dumps({"operation": operation, "arguments": arguments})

    def get(self, identifier: str) -> str:
        return self._command("get", {"id": identifier})

    def list(self, organization_id: str) -> str:
        return self._command("list", {"organizationId": organization_id})

    def create(self, identifier: UUID) -> str:
        return self._command("create", {"id": identifier.bytes.hex()})
