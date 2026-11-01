import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["KINTOREMEMO_DB"] = _tmp.name

import app as app_module  # noqa: E402


class KintoreMemoTest(unittest.TestCase):
    def setUp(self):
        app_module.init_db()
        self.client = app_module.app.test_client()
        with app_module.app.app_context():
            conn = app_module.get_db()
            conn.execute("DELETE FROM records")
            conn.commit()

    def _add(self, **kw):
        data = {
            "rdate": "2026-10-20", "exercise": "ベンチプレス",
            "weight": "60", "reps": "10", "sets": "3", "memo": "",
        }
        data.update(kw)
        return self.client.post("/add", data=data)

    def test_healthz(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "ok")

    def test_index_ok(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("前回超え筋トレメモ", body)
        self.assertIn("休憩タイマー", body)

    def test_previous_panel(self):
        # 2回分のセッション：前回パネルには古い方（10-20、60kg）が出る
        self._add(rdate="2026-10-20", weight="60", reps="10", sets="3")
        self._add(rdate="2026-10-27", weight="65", reps="8", sets="3")
        res = self.client.get("/?exercise=ベンチプレス")
        body = res.get_data(as_text=True)
        self.assertIn("前回（2026-10-20）：60.0kg × 10回 × 3セット", body)
        # 一覧には両方出る
        self.assertIn("65", body)

    def test_previous_panel_single_session(self):
        self._add(rdate="2026-10-20")
        res = self.client.get("/?exercise=ベンチプレス")
        body = res.get_data(as_text=True)
        self.assertIn("前回の記録はまだありません", body)

    def test_previous_session_function(self):
        self._add(rdate="2026-10-20", weight="60")
        self._add(rdate="2026-10-27", weight="65")
        self._add(rdate="2026-10-27", weight="65", reps="9")
        with app_module.app.app_context():
            conn = app_module.get_db()
            prev = app_module.previous_session(conn, "ベンチプレス")
        self.assertEqual(len(prev), 1)
        self.assertEqual(prev[0]["rdate"], "2026-10-20")

    def test_export(self):
        self._add(rdate="2026-10-20", weight="60", reps="10", sets="3")
        res = self.client.get("/export")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/plain", res.content_type)
        text = res.get_data(as_text=True)
        self.assertIn("2026-10-20 ベンチプレス 60kg 10回×3セット", text)

    def test_add_and_delete(self):
        self._add(memo="調子よかった")
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("調子よかった", body)
        with app_module.app.app_context():
            conn = app_module.get_db()
            rid = conn.execute("SELECT id FROM records").fetchone()["id"]
        res = self.client.post(f"/delete/{rid}")
        self.assertEqual(res.status_code, 302)
        self.assertNotIn("調子よかった", self.client.get("/").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
