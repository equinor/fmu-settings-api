#!/usr/bin/env python

"""Launches a web server, performs OAuth auth, retrieves token, then shuts down."""

import json
import sys
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

from dotenv import dotenv_values

CONFIG = dotenv_values(".env")
# Convert csv scopes into JSON serializable list
CONFIG["SCOPES"] = [
    scope.strip()
    for scope in CONFIG.get("SCOPES", "User.Read").split(",")  # type: ignore
]
# Port must be accepted by Azure app registration
PORT: Final[int] = 3000
REDIRECT_URI: Final[str] = f"http://localhost:{PORT}"
TOKEN_FILE: Final[Path] = Path(".token")

HTML = f"""
<!DOCTYPE html>
<html>
<head>
  <title>Get access token</title>
  <script
    type="text/javascript"
    src="https://alcdn.msauth.net/browser/2.38.2/js/msal-browser.min.js"
  ></script>
</head>
<body>
  <h1>fmu-settings-api</h1>
  <p>Clicking this will acquire an SSO access token for the scopes set in .env</p>
  <p>This token will be written to <code>.token</code></p>
  <button id="btn" onclick="signIn()">Get token</button>
  <div id="status"></div>

  <script>
    const msalConfig = {{
      auth: {{
        clientId: "{CONFIG["CLIENT_ID"]}",
        authority: "https://login.microsoftonline.com/{CONFIG["TENANT_ID"]}",
        redirectUri: "{REDIRECT_URI}",
      }},
      cache: {{
        cacheLocation: "sessionStorage",
        storeAuthStateInCookie: false,
      }}
    }};

    const loginRequest = {{
      scopes: {json.dumps(CONFIG["SCOPES"])}
    }};

    const msalInstance = new msal.PublicClientApplication(msalConfig);

    async function signIn() {{
        try {{
          document.getElementById("status").innerHTML = "<div>Authenticating...</div>";
          const loginResponse = await msalInstance.loginPopup(loginRequest);

          const tokenRequest = {{
            scopes: {json.dumps(CONFIG["SCOPES"])},
            account: loginResponse.account,
          }};

          const tokenResponse = await msalInstance.acquireTokenSilent(tokenRequest);

          // Send token to self
          await fetch("/", {{
            method: "POST",
            headers: {{
                "Content-Type": "application/json",
            }},
            body: JSON.stringify({{
                accessToken: tokenResponse.accessToken,
                idToken: tokenResponse.idToken,
                account: tokenResponse.account,
                scopes: tokenResponse.scopes,
            }})
          }});

          document.getElementById("status").innerHTML = "<div>Success!</div>";
          document.getElementById("btn").remove();
        }} catch (error) {{
          console.error("Auth failed:", error);
          document.getElementById("status").innerHTML = "<div>Failed auth</div>";
        }}
      }}
  </script>
</body>
</html>
"""

server_instance = None


def epoch_to_expired(future_epoch: float) -> str:
    """Converts a UNIX epoch expiration date into human readable format."""
    current_time = time.time()
    future_time = datetime.fromtimestamp(float(future_epoch))
    time_difference = future_time - datetime.fromtimestamp(current_time)
    days, seconds = time_difference.days, time_difference.seconds
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{days} days, {hours} hours, {minutes} minutes, and {seconds} seconds."


class AuthHandler(BaseHTTPRequestHandler):
    """HTTP Request handler for OAuth."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        """Handle POST requests (token submission)."""
        if self.path == "/":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)

            try:
                token_data = json.loads(post_data.decode("utf-8"))

                with open(".token", "w", encoding="utf-8") as f:
                    f.write(token_data["accessToken"])

                print()
                print(f"Token for scope(s) {token_data['scopes']} written to .token")
                exp_str = epoch_to_expired(
                    float(token_data["account"]["idTokenClaims"]["exp"])
                )
                print(f"Token expires in {exp_str}")

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())
                self.shutdown_server()
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def shutdown_server(self) -> None:
        """Shutdown the server."""
        print("Exiting...")
        sys.exit()

    def log_message(self, format: object, *args: object) -> None:
        """Suppress logging."""


def main() -> None:
    """Main."""
    try:
        server_instance = HTTPServer(("localhost", PORT), AuthHandler)
        webbrowser.open(f"http://localhost:{PORT}")
        server_instance.serve_forever()
    except KeyboardInterrupt:
        print("Server interrupted")
        if server_instance:
            server_instance.shutdown()
    except Exception as e:
        print(f"Error: {e}")
        if server_instance:
            server_instance.shutdown()


if __name__ == "__main__":
    main()
