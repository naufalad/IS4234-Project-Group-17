"""Officer assignment board for critical FINMA PEP cases."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from pep_analytics import db as DBM
from pep_analytics.case_board import case_assignment_board
from pep_analytics.ui import sidebar_config

st.set_page_config(page_title="FINMA Case Assignment Management", layout="wide")
DBM.init_db()

st.title("Critical Case Assignment Management")
st.caption(
    "Allocate unassigned critical cases to FINMA officers, confirm ownership, "
    "and track assignment status and notes."
)

sidebar_config()


def _reset_assignment_board() -> None:
    st.session_state["assignment_board_nonce"] = (
        st.session_state.get("assignment_board_nonce", 0) + 1
    )
    st.session_state.pop("pending_case_drop", None)
    st.session_state.pop("pending_case_manage", None)


@st.dialog("Confirm case assignment", width="large", dismissible=False)
def confirm_case_drop_dialog(
    case_id: str,
    officer_id: str,
    previous_officer_id: str | None = None,
) -> None:
    case = DBM.get_case(case_id)
    officers_frame = DBM.list_officers()
    officer_rows = officers_frame[officers_frame["officer_id"] == officer_id]
    if case is None or officer_rows.empty:
        st.error("The selected case or officer no longer exists.")
        if st.button("Reset board", width="stretch"):
            _reset_assignment_board()
            st.rerun()
        return

    officer = officer_rows.iloc[0]
    existing_notes = ""
    if previous_officer_id:
        assignments = DBM.list_officer_cases()
        previous = assignments[
            (assignments["case_id"] == case_id)
            & (assignments["officer_id"] == previous_officer_id)
        ]
        if not previous.empty:
            existing_notes = str(previous.iloc[0]["notes"] or "")

    st.markdown(f"**Case:** `{case_id}` · {case['entity_name']}")
    st.markdown(
        f"**Assign to:** {officer['name']} (`{officer_id}`) · {officer['email']}"
    )
    if previous_officer_id:
        st.info(f"This case will move from `{previous_officer_id}` to `{officer_id}`.")

    notes = st.text_area(
        "Assignment notes",
        value=existing_notes,
        height=160,
        placeholder="Add handover context, priority actions, or review instructions…",
        key=f"drop_notes_{case_id}_{officer_id}",
    )
    cancel_col, submit_col = st.columns(2)
    if cancel_col.button("Cancel", width="stretch", key="cancel_case_drop"):
        _reset_assignment_board()
        st.rerun()
    if submit_col.button(
        "Confirm assignment",
        type="primary",
        width="stretch",
        key="confirm_case_drop",
    ):
        DBM.assign_officer_to_case(case_id, officer_id, notes)
        _reset_assignment_board()
        st.toast(f"{case_id} assigned to {officer['name']}.")
        st.rerun()


@st.dialog("Change case assignment", width="large", dismissible=False)
def manage_assignment_dialog(case_id: str, officer_id: str) -> None:
    assignments = DBM.list_officer_cases()
    current = assignments[
        (assignments["case_id"] == case_id)
        & (assignments["officer_id"] == officer_id)
    ]
    if current.empty:
        st.error("This assignment no longer exists.")
        if st.button("Close", width="stretch", key="manage_close"):
            _reset_assignment_board()
            st.rerun()
        return

    row = current.iloc[0]
    st.markdown(f"**Case:** `{case_id}` · {row['entity_name']}")
    st.markdown(f"**Currently assigned to:** {row['officer_name']} (`{officer_id}`)")

    all_officers = DBM.list_officers()
    others = all_officers[all_officers["officer_id"] != officer_id]
    label_to_id = {f"{r.name} ({r.officer_id})": r.officer_id for r in others.itertuples()}

    choices = ["Remove assignment (back to unassigned)"]
    if label_to_id:
        choices.insert(0, "Reassign to another officer")
    action = st.radio("What would you like to do?", choices, key=f"manage_action_{case_id}")

    new_officer_id = None
    notes = str(row["notes"] or "")
    if action.startswith("Reassign"):
        chosen_label = st.selectbox(
            "New officer", list(label_to_id), key=f"manage_new_officer_{case_id}"
        )
        new_officer_id = label_to_id[chosen_label]
        notes = st.text_area(
            "Handover notes", value=notes, height=140,
            key=f"manage_notes_{case_id}",
        )
    else:
        st.info("The case goes back to **Unassigned critical cases**.")

    cancel_col, submit_col = st.columns(2)
    if cancel_col.button("Cancel", width="stretch", key="cancel_case_manage"):
        _reset_assignment_board()
        st.rerun()
    if submit_col.button(
        "Confirm", type="primary", width="stretch", key="confirm_case_manage"
    ):
        if new_officer_id:
            DBM.assign_officer_to_case(case_id, new_officer_id, notes)
            st.toast(f"{case_id} reassigned to {chosen_label}.")
        else:
            DBM.unassign_case(case_id)
            st.toast(f"{case_id} is unassigned again.")
        _reset_assignment_board()
        st.rerun()

@st.dialog("Assignment notes", width="large")
def assignment_notes_dialog(case_id: str, officer_id: str) -> None:
    assignments = DBM.list_officer_cases()
    selected = assignments[
        (assignments["case_id"] == case_id)
        & (assignments["officer_id"] == officer_id)
    ]
    if selected.empty:
        st.error("This assignment no longer exists.")
        return

    assignment = selected.iloc[0]
    st.markdown(f"**Case:** `{case_id}`")
    st.markdown(
        f"**Officer:** {assignment['officer_name']} "
        f"(`{officer_id}`) · {assignment['email']}"
    )
    status = st.selectbox(
        "Status",
        DBM.OFFICER_CASE_STATUSES,
        index=DBM.OFFICER_CASE_STATUSES.index(assignment["status"]),
        key=f"dialog_status_{case_id}_{officer_id}",
    )
    confirmed = st.checkbox(
        "Officer confirmed ownership",
        value=bool(assignment["confirmed"]),
        key=f"dialog_confirmed_{case_id}_{officer_id}",
    )
    notes = st.text_area(
        "Notes",
        value=assignment["notes"],
        height=180,
        key=f"dialog_notes_{case_id}_{officer_id}",
    )
    if st.button(
        "Save assignment",
        type="primary",
        width="stretch",
        key=f"dialog_save_{case_id}_{officer_id}",
    ):
        DBM.update_officer_case(
            case_id,
            officer_id,
            status=status,
            confirmed=confirmed,
            notes=notes,
        )
        st.success("Assignment updated.")
        st.rerun()


with st.expander("Officer directory", expanded=False):
    officers = DBM.list_officers()
    st.dataframe(officers, width="stretch", hide_index=True)

    with st.form("add_officer_form", clear_on_submit=True):
        col_id, col_name, col_email = st.columns(3)
        new_officer_id = col_id.text_input("Officer ID", placeholder="OFF-005")
        new_officer_name = col_name.text_input("Name", placeholder="Officer name")
        new_officer_email = col_email.text_input(
            "Email", placeholder="officer@finma.example"
        )
        add_submitted = st.form_submit_button("Add officer")
        if add_submitted:
            try:
                DBM.add_officer(
                    new_officer_id,
                    new_officer_name,
                    new_officer_email,
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success("Officer added.")
                st.rerun()

officers = DBM.list_officers()
officer_labels = {
    row.officer_id: f"{row.name} ({row.officer_id})"
    for row in officers.itertuples(index=False)
}

st.divider()
st.subheader("1. Drag cases to an officer")
unassigned = DBM.list_unassigned_critical_cases()
assignments = DBM.list_officer_cases()

u1, u2 = st.columns(2)
u1.metric("Unassigned critical cases", len(unassigned))
u2.metric(
    "Highest unassigned risk",
    f"{unassigned['risk_score'].max():.0f}" if not unassigned.empty else "—",
)

if officers.empty:
    st.warning("Add at least one officer before assigning cases.")
else:
    st.caption(
        "Drag a case card from **Unassigned critical cases** onto an officer.  \n"
        "The assignment is saved only after you add notes and confirm the popup."
    )

    board_nonce = st.session_state.get("assignment_board_nonce", 0)
    drop_event = case_assignment_board(
        unassigned=unassigned[
            ["case_id", "entity_name", "risk_score", "swiss_bank"]
        ].to_dict("records"),
        officers=officers[["officer_id", "name", "email"]].to_dict("records"),
        assignments=assignments[
            ["case_id", "officer_id", "entity_name", "risk_score"]
        ].to_dict("records"),
        key=f"case_assignment_board_{board_nonce}",
    )

    if drop_event and "pending_case_drop" not in st.session_state:
        case_id = drop_event.get("case_id")

        # Click on the x button of an assigned case -> open the manage/remove dialog
    if (
        drop_event
        and drop_event.get("action") == "manage"
        and "pending_case_drop" not in st.session_state
        and "pending_case_manage" not in st.session_state
    ):
        st.session_state["pending_case_manage"] = (
            drop_event.get("case_id"),
            drop_event.get("officer_id"),
        )
    elif (
        drop_event
        and drop_event.get("action") != "manage"
        and "pending_case_drop" not in st.session_state
        and "pending_case_manage" not in st.session_state
    ):
        target_officer = drop_event.get("officer_id")
        source_matches = assignments[assignments["case_id"] == case_id]
        previous_officer = (
            str(source_matches.iloc[0]["officer_id"])
            if not source_matches.empty
            else None
        )
        if case_id and target_officer and previous_officer != target_officer:
            st.session_state["pending_case_drop"] = (
                case_id,
                target_officer,
                previous_officer,
            )

    pending_drop = st.session_state.get("pending_case_drop")
    if pending_drop:
        confirm_case_drop_dialog(*pending_drop)
    
    pending_manage = st.session_state.get("pending_case_manage")
    if pending_manage and not pending_drop:
        manage_assignment_dialog(*pending_manage)
st.divider()
st.subheader("2. Cases assigned to officers")
assignments = DBM.list_officer_cases()

if assignments.empty:
    st.info("No officer assignments have been created.")
else:
    display_columns = [
        "case_id",
        "officer_id",
        "officer_name",
        "status",
        "confirmed",
        "notes",
    ]
    editable = assignments[display_columns].copy()
    editable["confirmed"] = editable["confirmed"].astype(bool)

    edited = st.data_editor(
        editable,
        width="stretch",
        hide_index=True,
        disabled=["case_id", "officer_id", "officer_name"],
        column_config={
            "case_id": st.column_config.TextColumn("Case ID"),
            "officer_id": st.column_config.TextColumn("Officer ID"),
            "officer_name": st.column_config.TextColumn("Officer"),
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=list(DBM.OFFICER_CASE_STATUSES),
                required=True,
            ),
            "confirmed": st.column_config.CheckboxColumn(
                "Confirmed",
                help="Whether the assigned officer accepted ownership.",
            ),
            "notes": st.column_config.TextColumn("Notes", width="large"),
        },
        key="officer_case_editor",
    )

    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button(
            "Save table changes",
            type="primary",
            width="content",
        ):
            for row in edited.itertuples(index=False):
                DBM.update_officer_case(
                    row.case_id,
                    row.officer_id,
                    status=row.status,
                    confirmed=bool(row.confirmed),
                    notes=row.notes or "",
                )
            st.success("All assignment changes saved.")
            st.rerun()

st.divider()
st.subheader("3. All alert cases")
overview = DBM.list_cases()[["case_id", "risk_score"]].merge(
    DBM.list_officer_cases()[["case_id", "officer_name", "status"]],
    on="case_id", how="left",
)
overview["unassigned"] = overview["officer_name"].isna()
overview = overview.sort_values(["unassigned", "risk_score"], ascending=[True, False])
overview["officer_name"] = overview["officer_name"].fillna("—")
overview["status"] = overview["status"].fillna("Not assigned").str.replace("_", " ")
st.dataframe(
    overview[["case_id", "officer_name", "status"]],
    width="stretch",
    hide_index=True,
    column_config={
        "case_id": st.column_config.TextColumn("Case"),
        "officer_name": st.column_config.TextColumn("Officer"),
        "status": st.column_config.TextColumn("Status"),
    },
)
