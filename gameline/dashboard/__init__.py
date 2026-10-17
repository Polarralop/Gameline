"""Local settings/dashboard page (Flask, plain HTML forms).

Flask pattern in brief: create_app() builds the app, each @app.route function
handles one URL, and forms POST back and then redirect (Post/Redirect/Get) so
a page refresh never resubmits. flash() carries a one-off message across
that redirect.
"""

from __future__ import annotations

from flask import Flask, flash, redirect, render_template, request, url_for

from ..context import AppContext, parse_local_datetime
from ..models import Deadline, Style
from ..planner import assess

HOST, PORT = "127.0.0.1", 5157
URL = f"http://{HOST}:{PORT}/"


def create_app(ctx: AppContext) -> Flask:
    app = Flask(__name__)
    app.secret_key = "gameline-local-only"

    @app.get("/")
    def index():
        state = ctx.store.load()
        now = ctx.clock.now()
        rows = [assess(d, state.working_style, now) for d in sorted(state.deadlines, key=lambda d: d.due)]
        return render_template(
            "index.html",
            rows=rows,
            state=state,
            now=now,
            styles=list(Style),
            status=ctx.status_line(),
            demo=ctx.demo_mode,
            fake_running=ctx.fake_game_running,
        )

    @app.post("/deadlines")
    def add_deadline():
        state = ctx.store.load()
        try:
            due = parse_local_datetime(request.form["due"])
        except ValueError:
            flash("Please enter a valid due date.")
            return redirect(url_for("index"))
        state.deadlines.append(
            Deadline(title=request.form["title"].strip(), due=due, notes=request.form.get("notes", "").strip())
        )
        for err in ctx.save_and_estimate(state):
            flash(err)
        return redirect(url_for("index"))

    @app.post("/deadlines/<did>/edit")
    def edit_deadline(did):
        state = ctx.store.load()
        d = state.get(did)
        if d:
            d.title = request.form["title"].strip()
            d.due = parse_local_datetime(request.form["due"])
            d.notes = request.form.get("notes", "").strip()
            for err in ctx.save_and_estimate(state):
                flash(err)
        return redirect(url_for("index"))

    @app.post("/deadlines/<did>/delete")
    def delete_deadline(did):
        state = ctx.store.load()
        state.deadlines = [d for d in state.deadlines if d.id != did]
        ctx.store.save(state)
        return redirect(url_for("index"))

    @app.post("/deadlines/<did>/chunks/<int:i>")
    def toggle_chunk(did, i):
        state = ctx.store.load()
        d = state.get(did)
        if d and d.estimate and 0 <= i < len(d.estimate.chunks):
            d.estimate.chunks[i].done = not d.estimate.chunks[i].done
            ctx.store.save(state)
        return redirect(url_for("index"))

    @app.post("/settings")
    def settings():
        state = ctx.store.load()
        ws = state.working_style
        ws.style = Style(request.form["style"])
        ws.daily_work_hours = float(request.form["daily_work_hours"])
        ws.max_gaming_minutes = int(request.form["max_gaming_minutes"])
        tags = request.form.get("tagged_games", "")
        state.tagged_games = [t.strip() for t in tags.split(",") if t.strip()]
        ctx.store.save(state)
        flash("Settings saved.")
        return redirect(url_for("index"))

    @app.post("/demo/<action>")
    def demo(action):
        if action == "seed":
            ctx.seed_demo_data()
        elif action == "speed":
            ctx.set_demo_mode(not ctx.demo_mode)
        elif action == "launch":
            ctx.start_fake_game()
        elif action == "quit":
            ctx.stop_fake_game()
        return redirect(url_for("index"))

    return app
