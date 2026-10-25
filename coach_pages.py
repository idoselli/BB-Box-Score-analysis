"""Public information for the BuzzerBeater Coach plugin."""

from flask import Blueprint, abort, render_template


coach_bp = Blueprint("coach", __name__, url_prefix="/buzzerbeater-coach")


@coach_bp.get("")
@coach_bp.get("/")
def overview():
    return render_template("coach.html", page="overview", title="BuzzerBeater Coach")


@coach_bp.get("/<page>")
def information(page):
    titles = {"support": "Support", "privacy": "Privacy policy", "terms": "Terms of use"}
    if page not in titles:
        abort(404)
    return render_template("coach.html", page=page, title=titles[page])
