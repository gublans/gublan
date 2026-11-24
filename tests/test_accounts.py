"""tests for gublan accounts in the studio (studio/account.py): pkce, which settings sync, the three-way merge,
the page the browser lands on after discord, and a whole sign-in against a pretend browser and server.
nothing here talks to the real account server."""
import base64
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from studio import account, config  # noqa: E402


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        err.close()
        return err.code, ""


class PkceTests(unittest.TestCase):
    def test_challenge_is_the_verifiers_sha256(self):
        verifier, challenge = account.pkce_pair()
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(challenge, expected)
        self.assertGreaterEqual(len(verifier), 43)  # what the pkce spec asks for
        self.assertNotIn("=", verifier + challenge)

    def test_pairs_are_different_every_time(self):
        self.assertNotEqual(account.pkce_pair()[0], account.pkce_pair()[0])

    def test_authorize_url(self):
        url = account.authorize_url("abc", account.callback_url())
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertTrue(url.startswith(account.SUPABASE_URL.rstrip("/") + "/auth/v1/authorize?"))
        self.assertEqual(query["provider"], ["discord"])
        self.assertEqual(query["code_challenge"], ["abc"])
        self.assertEqual(query["redirect_to"], [f"http://127.0.0.1:{account.CALLBACK_PORT}{account.CALLBACK_PATH}"])


class SettingsSyncTests(unittest.TestCase):
    def test_computer_only_settings_stay_here(self):
        settings = dict(config.DEFAULTS)
        mine = account.syncable(settings)
        for key in account.LOCAL_ONLY:
            self.assertNotIn(key, mine)
        self.assertTrue(set(mine) <= set(config.DEFAULTS))
        self.assertTrue(mine)

    def test_clean_keeps_only_what_this_studio_understands(self):
        bools = [key for key, value in config.DEFAULTS.items() if isinstance(value, bool) and key not in account.LOCAL_ONLY]
        ints = [key for key, value in config.DEFAULTS.items()
                if isinstance(value, int) and not isinstance(value, bool) and key not in account.LOCAL_ONLY]
        stored = {"made_up_setting": 1, next(iter(account.LOCAL_ONLY)): "x"}
        if bools:
            stored[bools[0]] = "yes"  # wrong kind: dropped
        if ints:
            stored[ints[0]] = 12.0  # a whole number that came back from json as a float
        cleaned = account.clean(stored)
        self.assertNotIn("made_up_setting", cleaned)
        self.assertFalse(set(cleaned) & account.LOCAL_ONLY)
        if bools:
            self.assertNotIn(bools[0], cleaned)
        if ints:
            self.assertEqual(cleaned[ints[0]], 12)
            self.assertIsInstance(cleaned[ints[0]], int)
        self.assertEqual(account.clean(["not", "a", "dict"]), {})

    def test_first_sync_brings_the_clouds_settings(self):
        merged = account.merge({"a": 1, "b": 2}, {"a": 9}, None)
        self.assertEqual(merged, {"a": 9, "b": 2})

    def test_changed_here_wins_and_changed_there_wins(self):
        synced = {"a": 1, "b": 1, "c": 1}
        local = {"a": 2, "b": 1, "c": 1}   # a changed on this computer
        cloud = {"a": 1, "b": 3, "c": 1}   # b changed on another one
        self.assertEqual(account.merge(local, cloud, synced), {"a": 2, "b": 3, "c": 1})

    def test_new_setting_from_the_cloud_is_taken(self):
        self.assertEqual(account.merge({"a": 1}, {"a": 1, "z": 5}, {"a": 1}), {"a": 1, "z": 5})


class AccountStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "account.json")

    def tearDown(self):
        self.temp.cleanup()

    def session(self, user="u1", expires=None):
        return {"access_token": "at-" + user, "refresh_token": "rt-" + user, "expires_at": expires or time.time() + 3600,
                "user": {"id": user, "user_metadata": {"custom_claims": {"global_name": "Moss"}, "avatar_url": "a.png"}}}

    def test_user_and_saved_state(self):
        me = account.Account(self.path)
        self.assertFalse(me.signed_in)
        self.assertIsNone(me.user())
        me.set_session(self.session())
        self.assertEqual(me.user(), {"id": "u1", "name": "Moss", "avatar": "a.png"})
        self.assertTrue(account.Account(self.path).signed_in)  # kept in account.json
        me.forget()
        self.assertFalse(account.Account(self.path).signed_in)

    def test_another_person_starts_unsynced(self):
        me = account.Account(self.path)
        me.set_session(self.session("u1"))
        me.state["synced"] = {"a": 1}
        me.set_session(self.session("u1"))  # a refreshed session: still synced
        self.assertIn("synced", me.state)
        me.set_session(self.session("u2"))
        self.assertNotIn("synced", me.state)

    def test_expired_session_is_refreshed(self):
        me = account.Account(self.path)
        me.set_session(self.session(expires=time.time() - 10))
        fresh = {"access_token": "new", "refresh_token": "rt2", "expires_in": 3600}
        with patch.object(account, "_request", return_value=fresh) as request:
            self.assertEqual(me.token(), "new")
            self.assertEqual(me.token(), "new")  # good for an hour now: no second refresh
        self.assertEqual(request.call_count, 1)
        self.assertEqual(me.user()["id"], "u1")  # the user is kept when the refresh doesn't send it

    def test_revoked_session_signs_out(self):
        me = account.Account(self.path)
        me.set_session(self.session(expires=time.time() - 10))
        with patch.object(account, "_request", side_effect=account.AccountError("invalid refresh token", 400)):
            with self.assertRaises(account.AccountError):
                me.token()
        self.assertFalse(me.signed_in)

    def test_sync_merges_and_keeps_the_playgrounds_part(self):
        me = account.Account(self.path)
        me.set_session(self.session())
        key = next(key for key, value in config.DEFAULTS.items()
                   if isinstance(value, bool) and key not in account.LOCAL_ONLY)
        settings = dict(config.DEFAULTS)
        row = {"settings": {"studio": {key: not settings[key]}, "playground": {"theme": "paper"}}}
        saved = []

        def server(method, path, body=None, token=None, headers=None):
            if method == "GET":
                return [row]
            saved.append(body)
            return None

        with patch.object(account, "_request", side_effect=server):
            result = me.sync(settings)
        self.assertEqual(result[key], not settings[key])  # the first sync takes the cloud's value
        self.assertEqual(saved[-1]["settings"]["playground"], {"theme": "paper"})  # untouched
        self.assertNotIn("project", saved[-1])  # the playground's files are left alone
        self.assertFalse(me.needs_sync(result))


class CallbackTests(unittest.TestCase):
    """the little server the browser comes back to after discord, on 127.0.0.1."""

    def sign_in_with(self, answer):
        """run sign_in with a pretend browser that visits the callback with answer (a query string)."""
        def browser(url):
            redirect = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["redirect_to"][0]
            threading.Thread(target=lambda: self.pages.append(_get(redirect + answer)), daemon=True).start()
            return True

        self.pages = []
        exchanged = []

        def server(method, path, body=None, token=None, headers=None):
            exchanged.append(body)
            return {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "user": {"id": "u1"}}

        with patch.object(account, "_request", side_effect=server), patch.object(account, "configured", return_value=True):
            try:
                return account.sign_in(open_browser=browser, timeout=5), exchanged
            finally:
                for _ in range(50):
                    if self.pages:
                        break
                    time.sleep(0.05)

    def test_sign_in_exchanges_the_code(self):
        session, exchanged = self.sign_in_with("?code=the-code")
        self.assertEqual(session["access_token"], "at")
        self.assertEqual(exchanged[0]["auth_code"], "the-code")
        self.assertTrue(exchanged[0]["code_verifier"])
        status, page = self.pages[0]
        self.assertEqual(status, 200)
        self.assertIn("signed in", page.lower())

    def test_discord_saying_no_is_an_error(self):
        with self.assertRaises(account.AccountError) as caught:
            self.sign_in_with("?error=access_denied&error_description=" + urllib.parse.quote("the user said no <b>"))
        self.assertIn("the user said no", str(caught.exception))
        self.assertNotIn("<b>", self.pages[0][1])  # shown safely on the page

    def test_other_paths_are_not_found(self):
        server = account._CallbackServer()
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        worker.start()
        try:
            self.assertEqual(_get(f"http://127.0.0.1:{account.CALLBACK_PORT}/other")[0], 404)
            self.assertIsNone(server.result)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
