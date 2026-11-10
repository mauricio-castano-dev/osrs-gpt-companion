"""Pruebas locales: no utilizan credenciales ni llaman a OpenAI."""
import contextlib
import io
import json
import tempfile
import threading
import time
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric import rsa

import auth
import inference
import osrs_reader


class CompanionTests(unittest.TestCase):
    def test_host_stable_and_credentials_encrypted(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(auth, "AUTH_DIR", Path(folder)):
            self.assertEqual(auth.host_id(), auth.host_id())
            profile = {"refresh_token": "secret-fixture", "client_id": "client"}
            auth.save_profile(profile)
            self.assertEqual(auth.load_profile(), profile)
            self.assertNotIn(b"secret-fixture", (Path(folder) / "profile.dpapi").read_bytes())

    def test_callback_checks_state_and_client(self):
        for query, expected in [
            ("state=wrong&code=abc&client_id=client", {}),
            ("state=ok&state=ok&code=abc&client_id=client", {}),
            ("state=ok&code=abc", {"code": "abc", "client_id": "client"}),
            ("state=ok&error=access_denied", {"error": "Autorizacion cancelada o rechazada."}),
        ]:
            result = {}
            with HTTPServer(("127.0.0.1", 0), auth.callback_handler("ok", "client", result)) as server:
                worker = threading.Thread(target=server.handle_request)
                worker.start()
                with requests.Session() as http:
                    http.trust_env = False
                    http.get(f"http://127.0.0.1:{server.server_port}/auth/callback?{query}", timeout=5)
                worker.join(5)
            self.assertEqual(result, expected)
        result = {}
        with HTTPServer(("127.0.0.1", 0), auth.callback_handler("ok", "client", result)) as server:
            worker = threading.Thread(target=server.handle_request)
            worker.start()
            with requests.Session() as http:
                http.trust_env = False
                http.get(f"http://127.0.0.1:{server.server_port}/auth/callback?state=ok&code=c&client_id=other", timeout=5)
            worker.join(5)
        self.assertIn("error", result)

    def test_identity_rejects_bad_nonce_signature_audience_and_account(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk["kid"] = "test"
        claims = dict(iss=auth.ISSUER, sub="subject", aud="client", iat=time.time(),
                      exp=time.time() + 600, nonce="nonce")
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})
        def metadata(*args, **kwargs):
            return {"keys": [jwk]} if args[1].endswith("/jwks") else {
                "issuer": auth.ISSUER, "jwks_uri": auth.ISSUER + "/jwks"}
        with patch.object(auth, "json_request", side_effect=metadata):
            self.assertEqual(auth.verify_identity(token, "client", "nonce")["subject"], "subject")
            for client, nonce, previous in [("client", "bad", None), ("bad", "nonce", None),
                                             ("client", "nonce", {"subject": "other"})]:
                with self.assertRaises(auth.CompanionError):
                    auth.verify_identity(token, client, nonce, previous)
            other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            forged = jwt.encode(claims, other_key, algorithm="RS256", headers={"kid": "test"})
            with self.assertRaises(auth.CompanionError):
                auth.verify_identity(forged, "client", "nonce")

    def test_refresh_rotation_and_scope_gate(self):
        profile = dict(client_id="issued", access_token="old-access", refresh_token="old-refresh",
                       expires_at=0, scope="chatgpt.tokens.use.direct")
        response = dict(access_token="new-access", refresh_token="new-refresh", token_type="Bearer", expires_in=3600)
        with patch.object(auth, "load_profile", return_value=profile), \
             patch.object(auth, "json_request", return_value=response) as post, \
             patch.object(auth, "save_profile") as save:
            self.assertEqual(auth.access_token(), "new-access")
            self.assertEqual(save.call_args.args[0]["refresh_token"], "new-refresh")
            self.assertEqual(post.call_args.kwargs["data"]["client_id"], "issued")
            self.assertNotIn("scope", post.call_args.kwargs["data"])
        with patch.object(auth, "load_profile", return_value={**profile, "expires_at": time.time()+600, "scope": "openid"}):
            with self.assertRaises(auth.CompanionError):
                auth.access_token()

    def test_state_reloaded_and_invalid_json_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(osrs_reader, "ROOT", Path(folder)):
            file = Path(folder) / "kpn_hooligan.json"
            for level in (5, 99):
                file.write_text(json.dumps({"attack": level}), encoding="utf-8")
                self.assertIn(str(level), osrs_reader.system_message()["content"])
                self.assertEqual(osrs_reader.system_message()["role"], "system")
            for bad in ("{", "[]", '{"attack": NaN}'):
                file.write_text(bad, encoding="utf-8")
                with self.assertRaises(auth.CompanionError):
                    osrs_reader.system_message()



if __name__ == "__main__":
    unittest.main()
