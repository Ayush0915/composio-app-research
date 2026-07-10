from dotenv import load_dotenv
import os
from composio import Composio
from composio.types import auth_scheme

load_dotenv(override=True)

composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))

connection = composio.connected_accounts.initiate(
    user_id="default",
    auth_config_id="ac_GQ2ghk6Cb7xo",
    config=auth_scheme.api_key({
        "generic_api_key": os.getenv("TAVILY_API_KEY"),
    }),
)

print("Connection status:", connection.status)
print("Connection ID:", connection.id)  