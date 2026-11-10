"""SIWC para un perfil local de Windows. Nunca utiliza una API key."""
import base64
import hashlib
import json
import math
import os
import re
import secrets
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
import requests
import win32crypt

ROOT = Path(__file__).resolve().parent
AUTH_DIR = ROOT / ".auth"
ISSUER = "https://auth.openai.com"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
USAGE = "https://chatgpt.com/settings/usage"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
HTTP = requests.Session()
# Evita que .netrc sustituya el Bearer o que se hereden credenciales del entorno.
HTTP.trust_env = False


class CompanionError(Exception):
    pass


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def host_id():
    path = AUTH_DIR / "host.json"
    if not path.exists():
        atomic_write(path, json.dumps({"ext_agent_host_id": f"urn:uuid:{uuid.uuid4()}"}).encode())
    value = json.loads(path.read_text("utf-8"))["ext_agent_host_id"]
    if not value.startswith("urn:uuid:") or uuid.UUID(value[9:]).version != 4:
        raise CompanionError("Identificador de instalacion invalido.")
    return value


def load_profile():
    path = AUTH_DIR / "profile.dpapi"
    if not path.exists():
        return {}
    # DPAPI cifra los tokens para el usuario actual de Windows.
    try:
        raw = win32crypt.CryptUnprotectData(path.read_bytes(), None, None, None, 1)[1]
        return json.loads(raw)
    except Exception:
        raise CompanionError("No se pudo descifrar el perfil con este usuario de Windows.") from None


def save_profile(profile):
    raw = json.dumps(profile).encode("utf-8")
    encrypted = win32crypt.CryptProtectData(raw, "OSRS GPT Companion", None, None, None, 1)
    atomic_write(AUTH_DIR / "profile.dpapi", encrypted)


def check_http(response):
    if 200 <= response.status_code < 300:
        return
    # No imprimir cuerpos arbitrarios: pueden contener datos de autenticacion.
    try:
        error = response.json().get("error", {})
        code = error.get("code", "unknown_error") if isinstance(error, dict) else error
    except (ValueError, AttributeError):
        code = "unknown_error"
    code = code if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,80}", code) else "unknown_error"
    raise CompanionError(f"HTTP {response.status_code}: {code}. Revisa la sesion o {USAGE}")


def json_request(method, url, **kwargs):
    with HTTP.request(method, url, timeout=(10, 45), allow_redirects=False, **kwargs) as r:
        check_http(r)
        return r.json()


def trusted_auth_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.netloc != "auth.openai.com":
        raise CompanionError("Endpoint de identidad inesperado.")
    return value


def verify_identity(id_token, client_id, nonce=None, previous=None):
    metadata = json_request("GET", ISSUER + "/.well-known/openid-configuration")
    if metadata.get("issuer") != ISSUER:
        raise CompanionError("Emisor de identidad inesperado.")
    jwks = json_request("GET", trusted_auth_url(metadata["jwks_uri"]))
    try:
        header = jwt.get_unverified_header(id_token)
        key = next(k for k in jwks["keys"] if k.get("kid") == header.get("kid"))
        claims = jwt.decode(
            id_token, jwt.PyJWK.from_dict(key).key, algorithms=["RS256"],
            audience=client_id, issuer=ISSUER, leeway=30,
            options={"require": ["iss", "sub", "aud", "exp", "iat"]},
        )
    except (jwt.PyJWTError, StopIteration, KeyError, TypeError, ValueError):
        raise CompanionError("El ID token no supera la validacion criptografica.") from None
    if nonce is not None and not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise CompanionError("Nonce de identidad incorrecto.")
    if claims.get("azp", client_id) != client_id:
        raise CompanionError("Cliente de identidad incorrecto.")
    if previous and previous.get("subject") and claims["sub"] != previous["subject"]:
        raise CompanionError("La identidad no coincide con el perfil guardado.")
    return {"subject": claims["sub"], "issuer": claims["iss"], "email": claims.get("email", "")}


def callback_handler(state, pending_client, result):
    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No registrar URLs con codigos OAuth.

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            if parsed.path != "/auth/callback":
                self.reply(404, "Ruta no disponible.")
                return
            if any(len(v) != 1 for v in query.values()) or not secrets.compare_digest(
                query.get("state", [""])[0], state
            ):
                self.reply(400, "Callback invalido.")
                return
            if "error" in query:
                result["error"] = "Autorizacion cancelada o rechazada."
            else:
                client = query.get("client_id", [pending_client])[0]
                code = query.get("code", [""])[0]
                if not code or not client or client == "dynamic_agent_client" or (
                    pending_client and client != pending_client
                ):
                    result["error"] = "Codigo o client_id de callback invalido."
                else:
                    result.update(code=code, client_id=client)
            self.reply(200, "Callback recibido. Vuelve a la consola para comprobar el resultado.")

        def reply(self, status, text):
            body = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)
    return Callback


class LoopbackServer(HTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(3)
        return connection, address


def token_record(data, profile, identity=None):
    for name in ("access_token", "refresh_token"):
        if not isinstance(data.get(name), str) or not data[name]:
            raise CompanionError(f"Respuesta OAuth sin {name}.")
    if str(data.get("token_type", "")).lower() != "bearer":
        raise CompanionError("Tipo de token inesperado.")
    lifetime = float(data["expires_in"])
    if not math.isfinite(lifetime) or lifetime <= 0:
        raise CompanionError("Caducidad de token invalida.")
    return {
        **profile, **(identity or {}),
        "access_token": data["access_token"], "refresh_token": data["refresh_token"],
        "id_token": data.get("id_token", profile.get("id_token")),
        "scope": data.get("scope", profile.get("scope", "")),
        "expires_at": time.time() + lifetime,
    }


def login():
    profile = load_profile()
    pending_client = profile.get("client_id")
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    result = {}
    with LoopbackServer(("127.0.0.1", 0), callback_handler(state, pending_client, result)) as server:
        server.timeout = 1
        redirect = f"http://127.0.0.1:{server.server_port}/auth/callback"
        params = dict(client_id=pending_client or "dynamic_agent_client",
                      ext_agent_host_id=host_id(), response_type="code", redirect_uri=redirect,
                      scope=SCOPES, resource=RESOURCE, state=state, nonce=nonce,
                      code_challenge_method="S256", code_challenge=challenge)
        if not pending_client:
            params["agent_name_hint"] = "OSRS GPT Companion"
        print("Continue with ChatGPT: autoriza el uso de tu plan en el navegador.")
        url = AUTHORIZE + "?" + urlencode(params)
        if not webbrowser.open(url):
            print("Abre esta URL (no contiene tokens):", url)
        deadline = time.monotonic() + 180
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if not result:
        raise CompanionError("Tiempo de inicio de sesion agotado.")
    if "error" in result:
        raise CompanionError(result["error"])
    # Guardar el registro incluso si el codigo caduca durante el canje.
    profile["client_id"] = result["client_id"]
    save_profile(profile)
    data = json_request("POST", TOKEN, data=dict(
        grant_type="authorization_code", client_id=profile["client_id"],
        code=result["code"], code_verifier=verifier, redirect_uri=redirect, resource=RESOURCE))
    identity = verify_identity(data["id_token"], profile["client_id"], nonce, profile)
    profile = token_record(data, profile, identity)
    save_profile(profile)
    return profile


def access_token():
    profile = load_profile()
    if not profile.get("access_token"):
        profile = login()
    if time.time() >= profile["expires_at"] - 60:
        data = json_request("POST", TOKEN, data=dict(
            grant_type="refresh_token", client_id=profile["client_id"],
            refresh_token=profile["refresh_token"], resource=RESOURCE))
        identity = verify_identity(data["id_token"], profile["client_id"], previous=profile) if data.get("id_token") else None
        profile = token_record(data, profile, identity)
        save_profile(profile)
    if "chatgpt.tokens.use.direct" not in profile.get("scope", "").split():
        raise CompanionError("No se concedio Token Sharing. Revisa ChatGPT y ejecuta --login.")
    return profile["access_token"]


def logout():
    profile = load_profile()
    confirmed = not profile.get("refresh_token")
    try:
        if not confirmed:
            metadata = json_request("GET", ISSUER + "/.well-known/openid-configuration")
            endpoint = trusted_auth_url(metadata["revocation_endpoint"])
            for attempt in range(3):
                try:
                    with HTTP.post(endpoint, data=dict(token=profile["refresh_token"],
                                   token_type_hint="refresh_token", client_id=profile["client_id"]),
                                   timeout=(10, 20), allow_redirects=False) as r:
                        confirmed = r.status_code == 200
                        if confirmed or r.status_code < 500:
                            break
                except requests.RequestException:
                    pass
                time.sleep(2 ** attempt)
    except (requests.RequestException, CompanionError, ValueError, KeyError):
        pass
    finally:
        save_profile({k: v for k, v in profile.items() if k in ("client_id", "subject", "issuer", "email")})
    print("Sesion local cerrada." if confirmed else
          "Sesion local cerrada; revocacion remota no confirmada. Desconecta la app en ChatGPT Settings.")
