"""Reporting routes — admin only."""
from datetime import datetime, timedelta

from flask import Blueprint, abort, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from ..activity_logger import ACTION_LABELS
from ..extensions import db
from ..models import ApiRequestLog, Integration, LlmModel, LlmRequestLog, User, UserActivityLog

reporting_bp = Blueprint("reporting", __name__, url_prefix="/reporting")


def _admin_required():
    if not current_user.is_authenticated or not current_user.is_admin():
        abort(403)


def _date_range():
    """Parse date_from / date_to from query string, defaulting to last 30 days."""
    today = datetime.utcnow().date()
    try:
        date_from = datetime.strptime(request.args.get("date_from", ""), "%Y-%m-%d").date()
    except ValueError:
        date_from = today - timedelta(days=30)
    try:
        date_to = datetime.strptime(request.args.get("date_to", ""), "%Y-%m-%d").date()
    except ValueError:
        date_to = today
    return date_from, date_to


@reporting_bp.route("/")
@login_required
def index():
    _admin_required()
    active_tab = request.args.get("tab", "llm")

    # ── LLM Requests tab ────────────────────────────────────────────────────
    llm_date_from, llm_date_to = _date_range()
    llm_page = request.args.get("page", 1, type=int)

    llm_q = LlmRequestLog.query.filter(
        LlmRequestLog.created_at >= datetime(llm_date_from.year, llm_date_from.month, llm_date_from.day),
        LlmRequestLog.created_at <= datetime(llm_date_to.year, llm_date_to.month, llm_date_to.day, 23, 59, 59),
    )

    model_id_filter = request.args.get("model_id", type=int)
    if model_id_filter:
        llm_q = llm_q.filter(LlmRequestLog.model_id == model_id_filter)

    use_case_filter = request.args.get("use_case", "").strip() or None
    if use_case_filter:
        llm_q = llm_q.filter(LlmRequestLog.use_case == use_case_filter)

    llm_total      = llm_q.count()
    llm_errors     = llm_q.filter(LlmRequestLog.status == "error").count()
    llm_error_rate = round(llm_errors / llm_total * 100, 1) if llm_total else 0.0
    llm_avg_lat    = int(db.session.query(func.avg(LlmRequestLog.latency_ms))
                         .filter(LlmRequestLog.latency_ms.isnot(None))
                         .scalar() or 0)
    llm_total_tok  = db.session.query(func.sum(LlmRequestLog.total_tokens)).scalar() or 0

    llm_pagination = (
        llm_q.order_by(LlmRequestLog.created_at.desc())
        .paginate(page=llm_page, per_page=50, error_out=False)
    )

    # ── User Activity tab ────────────────────────────────────────────────────
    act_date_from, act_date_to = _date_range()
    act_page = request.args.get("act_page", 1, type=int)
    act_user_id = request.args.get("act_user_id", type=int)
    act_action  = request.args.get("act_action", "").strip() or None

    act_q = UserActivityLog.query.filter(
        UserActivityLog.created_at >= datetime(act_date_from.year, act_date_from.month, act_date_from.day),
        UserActivityLog.created_at <= datetime(act_date_to.year, act_date_to.month, act_date_to.day, 23, 59, 59),
    )
    if act_user_id:
        act_q = act_q.filter(UserActivityLog.user_id == act_user_id)
    if act_action:
        act_q = act_q.filter(UserActivityLog.action == act_action)

    act_total        = act_q.count()
    act_active_users = (act_q.with_entities(func.count(func.distinct(UserActivityLog.user_id)))
                        .scalar() or 0)

    top_act_row = (
        act_q.with_entities(UserActivityLog.action, func.count(UserActivityLog.id).label("cnt"))
        .group_by(UserActivityLog.action)
        .order_by(func.count(UserActivityLog.id).desc())
        .first()
    )
    top_action = ACTION_LABELS.get(top_act_row.action, top_act_row.action) if top_act_row else "—"

    act_pagination = (
        act_q.order_by(UserActivityLog.created_at.desc())
        .paginate(page=act_page, per_page=50, error_out=False)
    )

    # ── External API Requests tab ────────────────────────────────────────────
    api_date_from, api_date_to = _date_range()
    api_page_num = request.args.get("api_page", 1, type=int)
    api_integ_id = request.args.get("integration_id", type=int)

    api_q = ApiRequestLog.query.filter(
        ApiRequestLog.created_at >= datetime(api_date_from.year, api_date_from.month, api_date_from.day),
        ApiRequestLog.created_at <= datetime(api_date_to.year, api_date_to.month, api_date_to.day, 23, 59, 59),
    )
    if api_integ_id:
        api_q = api_q.filter(ApiRequestLog.integration_id == api_integ_id)

    api_total       = api_q.count()
    api_errors      = api_q.filter(ApiRequestLog.status_code >= 400).count()
    api_error_rate  = round(api_errors / api_total * 100, 1) if api_total else 0.0
    api_avg_lat     = int(db.session.query(func.avg(ApiRequestLog.latency_ms))
                          .filter(ApiRequestLog.latency_ms.isnot(None))
                          .scalar() or 0)

    api_pagination = (
        api_q.order_by(ApiRequestLog.created_at.desc())
        .paginate(page=api_page_num, per_page=50, error_out=False)
    )

    return render_template(
        "reporting/index.html",
        active_tab=active_tab,
        # LLM
        llm_logs=llm_pagination.items,
        llm_pagination=llm_pagination,
        llm_summary={
            "total":       llm_total,
            "errors":      llm_errors,
            "error_rate":  llm_error_rate,
            "avg_latency": llm_avg_lat,
            "total_tokens": llm_total_tok,
        },
        llm_models=LlmModel.query.order_by(LlmModel.name).all(),
        llm_filters={
            "date_from": llm_date_from.isoformat(),
            "date_to":   llm_date_to.isoformat(),
            "model_id":  model_id_filter,
            "use_case":  use_case_filter or "",
        },
        # Activity
        act_logs=act_pagination.items,
        act_pagination=act_pagination,
        act_summary={
            "total":        act_total,
            "active_users": act_active_users,
            "top_action":   top_action,
        },
        all_users=User.query.order_by(User.username).all(),
        act_filters={
            "date_from": act_date_from.isoformat(),
            "date_to":   act_date_to.isoformat(),
            "user_id":   act_user_id,
            "action":    act_action or "",
        },
        action_labels=ACTION_LABELS,
        # API
        api_logs=api_pagination.items,
        api_pagination=api_pagination,
        api_summary={
            "total":       api_total,
            "errors":      api_errors,
            "error_rate":  api_error_rate,
            "avg_latency": api_avg_lat,
        },
        integrations=Integration.query.order_by(Integration.name).all(),
        api_filters={
            "date_from":      api_date_from.isoformat(),
            "date_to":        api_date_to.isoformat(),
            "integration_id": api_integ_id,
        },
        breadcrumbs=[
            {"label": "Home", "url": url_for("main.dashboard")},
            {"label": "Reporting", "url": None},
        ],
    )
