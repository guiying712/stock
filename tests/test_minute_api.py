import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from stockradar.connection_settings import ConnectionSettings
from stockradar.minute_feed import MinuteFeed
from stockradar.server import handler_for
from stockradar.service import Application


class MinuteAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = Application(str(self.root / "test.sqlite3"), seed=False)
        self.app.connections = ConnectionSettings(self.root / ".connections", environ={})
        self.app.minutes = MinuteFeed(self.root / "minutes", self.app.connections)
        self.server = ThreadingHTTPServer(("127.0.0.1",0),handler_for(self.app,"synthetic-access-token"))
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.value = {"schema_version":1,"mode":"latest","symbols":["600519.SH"],"start_date":None,"end_date":None,"access_confirmed":True}

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self, endpoint="minute-data", method="GET", body=None, auth=True, origin=None):
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port)
        headers={"Authorization":"Bearer synthetic-access-token"} if auth else {}
        if body is not None:headers["Content-Type"]="application/json"
        if origin:headers["Origin"]=origin
        connection.request(method,"/api/v1/"+endpoint,json.dumps(body) if body is not None else None,headers)
        response=connection.getresponse();payload=json.loads(response.read());connection.close()
        return response.status,payload

    def test_auth_origin_and_read_requests_never_capture(self):
        with patch("stockradar.vendor_samples.request.build_opener") as network:
            self.assertEqual(self.request(auth=False)[0],401)
            self.assertEqual(self.request("minute-data/fetch","POST",self.value,auth=False)[0],401)
            self.assertEqual(self.request("minute-data/fetch","POST",self.value,origin="https://evil.invalid")[0],403)
            status,result=self.request()
            self.assertEqual(status,200)
            self.assertIsNone(result["capture"])
            network.assert_not_called()
        self.assertFalse(self.app.minutes.directory.exists())

    def test_prepare_and_unconfigured_fetch_are_zero_requests(self):
        with patch("stockradar.vendor_samples.request.build_opener") as network:
            status,result=self.request("minute-data/prepare","POST",self.value)
            self.assertEqual(status,200)
            self.assertEqual(result["sent_requests"],0)
            self.assertIn("CREDENTIAL_MISSING",result["reason_codes"])
            self.assertEqual(self.request("minute-data/fetch","POST",self.value)[0],400)
            self.assertEqual(self.request("minute-data/prepare","POST",dict(self.value,api_key="synthetic-must-not-echo"))[0],400)
            network.assert_not_called()
        self.assertFalse(self.app.minutes.directory.exists())

    def test_capture_is_visible_and_separate_from_strategy_database(self):
        from test_minute_feed import Opener
        self.app.connections.save("tushare",{"schema_version":1,"revision":"new","key_action":"replace","api_key":"synthetic-minute-secret",
            "authorization":{"confirmed":True,"reference":"synthetic-permission"}})
        fields="ts_code,time,open,high,low,close,vol,amount".split(",")
        opener=Opener([{"code":0,"data":{"fields":fields,"items":[["600519.SH","2026-11-06 14:59:00",10,11,9,10.5,100,1000]]}}])
        original=self.app.minutes.fetch
        self.app.minutes.fetch=lambda value:original(value,opener=opener,sleep=lambda _:None)
        status,result=self.request("minute-data/fetch","POST",self.value)
        self.assertEqual(status,200)
        self.assertEqual(result["capture"]["bar_count"],1)
        self.assertEqual(len(opener.calls),1)
        self.assertFalse(result["strategy_input_ready"])
        self.assertNotIn("synthetic-minute-secret",json.dumps(result))
        self.assertEqual(self.request()[1]["capture"]["id"],result["capture"]["id"])
        with self.app.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM scans").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM outbox").fetchone()[0],0)
        self.assertEqual(self.app.config["mode"],"fixture")

    def test_view_module_is_served_but_raw_data_and_connections_are_private(self):
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port)
        for path,expected in (("/minute-view.js",200),("/minute-data/latest.json",404),("/minute-data/../../data/.api-token",404)):
            connection.request("GET",path);response=connection.getresponse();body=response.read()
            self.assertEqual(response.status,expected)
            if expected==200:self.assertIn(b"minutePage",body)
        connection.close()
