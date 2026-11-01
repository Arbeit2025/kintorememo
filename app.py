"""前回超え筋トレメモ kintorememo

筋トレの記録（種目・重量・回数・セット数）をつけ、種目を選ぶと
前回のセッションを「前回」パネルで見せてくれる小さなツール。
前回の自分を超えるためのメモ。単一ファイル Flask + SQLite。
"""
import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, Response, g, jsonify, redirect, render_template_string, request, url_for

app = Flask(__name__)
JST = ZoneInfo("Asia/Tokyo")
DB_PATH = os.environ.get("KINTOREMEMO_DB", os.path.join(os.path.dirname(__file__), "kintorememo.db"))


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rdate TEXT NOT NULL,
            exercise TEXT NOT NULL,
            weight REAL,
            reps INTEGER,
            sets INTEGER,
            memo TEXT NOT NULL DEFAULT ''
        );
        """
    )
    db.commit()
    db.close()


def previous_session(db, exercise):
    """その種目の「前回」セッション（最新の日付より前の直近の日付の記録群）。

    記録が1日分しかない場合は空リストを返す。
    """
    dates = db.execute(
        "SELECT DISTINCT rdate FROM records WHERE exercise = ? ORDER BY rdate DESC",
        (exercise,),
    ).fetchall()
    if len(dates) < 2:
        return []
    prev_date = dates[1]["rdate"]
    return db.execute(
        "SELECT * FROM records WHERE exercise = ? AND rdate = ? ORDER BY id ASC",
        (exercise, prev_date),
    ).fetchall()


def record_line(r):
    parts = [r["rdate"], r["exercise"]]
    if r["weight"] is not None:
        parts.append(f"{r['weight']:g}kg")
    if r["reps"] is not None and r["sets"] is not None:
        parts.append(f"{r['reps']}回×{r['sets']}セット")
    if r["memo"]:
        parts.append(r["memo"])
    return " ".join(parts)


PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>前回超え筋トレメモ</title>
<style>body{font-family:sans-serif;max-width:720px;margin:2em auto;padding:0 1em}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ccc;padding:.3em .5em;text-align:left}
.prevbox{background:#eef6ee;border:1px solid #7a7;padding:.5em 1em;border-radius:8px}
#timer{font-size:2em;font-weight:bold}input{margin:.2em}</style>
</head><body>
<h1>前回超え筋トレメモ</h1>
<p>トレーニングを記録して、前回の自分と比べられます。種目を選ぶと「前回」の記録が出ます。</p>

<h2>記録を追加</h2>
<form method="post" action="{{ url_for('add') }}">
  <label>日付 <input type="date" name="rdate" value="{{ today }}" required></label>
  <label>種目 <input type="text" name="exercise" placeholder="例：ベンチプレス" required></label><br>
  <label>重量(kg) <input type="number" name="weight" step="0.5" min="0"></label>
  <label>回数 <input type="number" name="reps" min="0"></label>
  <label>セット数 <input type="number" name="sets" min="0"></label>
  <label>メモ <input type="text" name="memo"></label>
  <button type="submit">追加</button>
</form>

<h2>休憩タイマー</h2>
<p><span id="timer">0:00</span></p>
<p>
<button type="button" onclick="startTimer(60)">60秒</button>
<button type="button" onclick="startTimer(90)">90秒</button>
<button type="button" onclick="startTimer(180)">180秒</button>
<button type="button" onclick="stopTimer()">止める</button>
</p>
<script>
let timerId = null, remain = 0;
function showTimer(){
  const m = Math.floor(remain / 60), s = remain % 60;
  document.getElementById("timer").textContent = m + ":" + String(s).padStart(2, "0");
}
function startTimer(sec){
  stopTimer(); remain = sec; showTimer();
  timerId = setInterval(function(){
    remain -= 1; showTimer();
    if (remain <= 0) { stopTimer(); document.getElementById("timer").textContent = "終わり！"; }
  }, 1000);
}
function stopTimer(){ if (timerId) { clearInterval(timerId); timerId = null; } }
</script>

<h2>種目で絞り込み</h2>
<p><a href="{{ url_for('index') }}">すべて</a>
{% for e in exercises %}／<a href="{{ url_for('index', exercise=e) }}">{{ e }}</a>{% endfor %}
／<a href="{{ url_for('export') }}">テキストでエクスポート</a></p>

{% if selected %}
<h2>「{{ selected }}」の前回</h2>
<div class="prevbox">
{% if prev %}
{% for r in prev %}<p>前回（{{ r.rdate }}）：{{ r.weight }}kg × {{ r.reps }}回 × {{ r.sets }}セット{% if r.memo %} - {{ r.memo }}{% endif %}</p>{% endfor %}
<p>今日はこれを超えていきましょう。</p>
{% else %}<p>前回の記録はまだありません（この種目は1日分だけです）。</p>{% endif %}
</div>
{% endif %}

<h2>記録一覧{% if selected %}（{{ selected }}）{% endif %}</h2>
<table>
<tr><th>日付</th><th>種目</th><th>重量</th><th>回数</th><th>セット</th><th>メモ</th><th>操作</th></tr>
{% for r in records %}
<tr><td>{{ r.rdate }}</td><td>{{ r.exercise }}</td>
<td>{% if r.weight is not none %}{{ r.weight }} kg{% endif %}</td>
<td>{% if r.reps is not none %}{{ r.reps }} 回{% endif %}</td>
<td>{% if r.sets is not none %}{{ r.sets }}{% endif %}</td>
<td>{{ r.memo }}</td>
<td><form method="post" action="{{ url_for('delete', rid=r.id) }}" style="display:inline" onsubmit="return confirm('この記録を削除しますか？')"><button type="submit">削除</button></form></td></tr>
{% else %}<tr><td colspan="7">記録はまだありません</td></tr>
{% endfor %}
</table>
</body></html>"""


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    db = get_db()
    selected = (request.args.get("exercise") or "").strip()
    exercises = [
        r["exercise"]
        for r in db.execute("SELECT DISTINCT exercise FROM records ORDER BY exercise").fetchall()
    ]
    prev = []
    if selected:
        records = db.execute(
            "SELECT * FROM records WHERE exercise = ? ORDER BY rdate DESC, id DESC", (selected,)
        ).fetchall()
        prev = previous_session(db, selected)
    else:
        records = db.execute("SELECT * FROM records ORDER BY rdate DESC, id DESC").fetchall()
    return render_template_string(
        PAGE, records=records, exercises=exercises, selected=selected, prev=prev,
        today=datetime.now(JST).strftime("%Y-%m-%d"),
    )


def _num_or_none(v, cast):
    try:
        return cast(v) if v not in (None, "") else None
    except ValueError:
        return None


@app.route("/add", methods=["POST"])
def add():
    rdate = (request.form.get("rdate") or "").strip() or datetime.now(JST).strftime("%Y-%m-%d")
    exercise = (request.form.get("exercise") or "").strip()
    if exercise:
        db = get_db()
        db.execute(
            "INSERT INTO records(rdate, exercise, weight, reps, sets, memo) VALUES(?, ?, ?, ?, ?, ?)",
            (
                rdate, exercise,
                _num_or_none(request.form.get("weight"), float),
                _num_or_none(request.form.get("reps"), int),
                _num_or_none(request.form.get("sets"), int),
                (request.form.get("memo") or "").strip(),
            ),
        )
        db.commit()
    return redirect(url_for("index"))


@app.route("/delete/<int:rid>", methods=["POST"])
def delete(rid):
    db = get_db()
    db.execute("DELETE FROM records WHERE id = ?", (rid,))
    db.commit()
    return redirect(url_for("index"))


@app.route("/export")
def export():
    db = get_db()
    rows = db.execute("SELECT * FROM records ORDER BY rdate ASC, id ASC").fetchall()
    text = "\n".join(record_line(r) for r in rows) + ("\n" if rows else "")
    return Response(
        text,
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=kintorememo.txt"},
    )


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
