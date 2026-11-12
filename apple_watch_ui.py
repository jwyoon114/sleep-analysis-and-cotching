"""Account-based wearable sleep dashboard."""
from datetime import date
import streamlit as st
import history_service
import backup_policy
from health_records import delete_session, import_export, list_sessions, overview
from sleep_accounts import AuthenticationError, current_user, delete_account, login, logout, register, update_account

LABELS = {"core": "코어 수면", "deep": "깊은 수면", "rem": "렘수면", "wake": "각성", "unspecified": "수면(단계 미분류)"}
METRICS = {"heartRate": "심박수", "hrvSDNN": "심박변이도(SDNN)", "respiratoryRate": "호흡수", "oxygenSaturation": "산소포화도"}


def duration(value):
    minutes = round(value)
    return f"{minutes // 60}시간 {minutes % 60}분"


def clock(value):
    return value[:19].replace("T", " ")


def login_screen():
    st.title("나의 수면 리포트")
    if message := st.session_state.pop("login_notice", None):
        st.success(message)
    if st.session_state.get("account_backup_pending"):
        status = backup_policy.maintain_backups()
        if status["pending"]:
            st.warning(f"계정은 삭제됐지만 관리 대상 백업 {status['pending']}개의 정리가 아직 완료되지 않았습니다. 파일 접근 상태를 확인한 뒤 다시 시도하세요.")
            if st.button("계정 삭제 후 백업 정리 다시 시도"):
                st.rerun()
        else:
            st.session_state.pop("account_backup_pending", None)
            st.success("관리 대상 백업의 계정 삭제 반영도 완료했습니다.")
    st.write("수면 기록을 올리고, 나의 수면 패턴과 개선할 습관을 알아보세요.")
    st.caption("수면 기록 .md 또는 .json 파일을 지원합니다.")
    sign_in, sign_up = st.tabs(["로그인", "회원가입"])
    with sign_in, st.form("login"):
        username = st.text_input("아이디", key="login_name")
        password = st.text_input("비밀번호", type="password", key="login_password")
        if st.form_submit_button("로그인", type="primary"):
            try:
                result = login(username, password)
                st.session_state["auth_token"] = result["token"]
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    with sign_up, st.form("register"):
        name = st.text_input("새 아이디", help="문자·숫자·밑줄·점·하이픈 3~40자")
        new_password = st.text_input("새 비밀번호", type="password", help="10자 이상")
        confirm = st.text_input("비밀번호 확인", type="password")
        if st.form_submit_button("회원가입"):
            try:
                if new_password != confirm:
                    raise ValueError("비밀번호 확인이 일치하지 않습니다.")
                register(name, new_password)
                st.success("계정을 만들었습니다. 로그인 탭에서 로그인하세요.")
            except ValueError as error:
                st.error(str(error))


def render():
    import sleep_alarms
    sleep_alarms.start_worker()
    try:
        user = current_user(st.session_state.get("auth_token"))
    except AuthenticationError:
        st.session_state.pop("auth_token", None)
        login_screen()
        return
    st.sidebar.title("나의 수면 리포트")
    st.sidebar.write(f"{user['username']} 님")
    st.sidebar.caption("로그인한 계정의 기록만 표시합니다.")
    history_service.expire_trash(user["id"])
    page = st.sidebar.radio("메뉴", ["과거 기록", "새 분석", "기간별 비교", "휴지통·백업", "계정 설정"], key="main_menu")
    if st.sidebar.button("로그아웃"):
        logout(st.session_state["auth_token"])
        st.session_state.clear()
        st.rerun()
    st.title("나의 수면 리포트")
    st.write("수면 시간부터 밤중 각성까지, 기록을 바탕으로 살펴보세요.")
    if message := st.session_state.pop("history_message", None):
        st.success(message)
    if page == "새 분석":
        render_upload(user)
    elif page == "기간별 비교":
        render_comparison(user)
    elif page == "휴지통·백업":
        render_trash(user)
    elif page == "계정 설정":
        render_account_settings(user)
    else:
        render_records(user)


def render_upload(user):
    with st.expander("1. 수면 파일 가져오기", expanded=True):
        st.write("Health Data Export .md 또는 Health Export Kit .json 파일을 선택하세요.")
        st.caption("수면 JSON v1도 지원합니다. 시각만 담긴 파일은 날짜 범위와 시간대 정보로 복원합니다. Apple 건강 XML은 지원하지 않습니다.")
        st.caption("분석을 저장하면 로그인한 계정의 서버 저장소에 보관됩니다. 기본 조언은 달잠 서버에서 규칙으로 생성합니다. OpenAI 방식이 활성화된 서버에서는 조언 생성 시 기록 요약과 생활습관 입력을 OpenAI에 전송합니다.")
        from json_sleep import EXAMPLE_JSON
        st.download_button("JSON 예제 다운로드 · 가상 기록", EXAMPLE_JSON, "sleep_example.json", "application/json")
        uploaded = st.file_uploader("수면 기록 파일", type=["md", "json"], key="watch_upload")
        if st.button("분석하고 내 기록에 저장", type="primary", disabled=uploaded is None):
            try:
                result = import_export(uploaded.getvalue().decode("utf-8-sig"), uploaded.name, user["id"])
                st.session_state["watch_preview_ids"] = result["analysis_ids"]
                if result["added_sessions"]:
                    st.success(f"새 수면 기록 {result['added_sessions']}건을 저장했습니다.")
                else:
                    st.info("이미 저장한 기록입니다. 중복으로 저장하지 않았습니다.")
                st.caption("아래에서 실제 분석 그래프를 확인하세요. 저장된 결과는 ‘과거 기록’에서도 다시 볼 수 있습니다.")
            except (ValueError, KeyError, UnicodeError, OverflowError) as error:
                st.error(f"파일 형식을 확인하세요: {error}")

    preview_ids = set(st.session_state.get("watch_preview_ids", []))
    if preview_ids:
        # Fetch only the signed-in account's records; preview IDs never grant access.
        previews = [s for s in list_sessions(user["id"]) if s["analysis_id"] in preview_ids]
        if previews:
            st.subheader("분석 결과 · 시간별 수면 양상")
            choices = {s["analysis_id"]: s for s in previews}
            selected = st.selectbox("그래프로 볼 분석 기록", list(choices), key=f"watch_preview_{user['id']}",
                                    format_func=lambda sid: f"{clock(choices[sid]['start'])} · 수면 {duration(choices[sid]['asleep_minutes'])}")
            record = choices[selected]
            left, right = st.columns(2)
            left.metric("기기 추정 수면 시간", duration(record["asleep_minutes"]))
            right.metric("각성 시간", duration(record["awake_minutes"]))
            render_sleep_pattern(record)
            if record["unrecorded_minutes"] > 0:
                st.warning(f"미기록 구간 {duration(record['unrecorded_minutes'])}은 그래프에서 비워 표시합니다.")
            for warning in record["warnings"]:
                st.warning(warning)


def render_sleep_pattern(record):
    """Draw the actual saved intervals directly in the program, without AI calls."""
    import altair as alt
    import pandas as pd
    intervals = pd.DataFrame([{"시작": pd.Timestamp(v["start"]), "종료": pd.Timestamp(v["end"]),
                              "단계": LABELS[v["stage"]], "분": round(v["minutes"], 2)} for v in record["segments"]])
    if intervals.empty:
        st.info("이 기록에는 시간별 수면 구간이 없습니다.")
        return intervals
    chart_data = intervals.copy()
    # Preserve recorded wall-clock time; UTC conversion would shift the graph.
    chart_data["시작"] = chart_data["시작"].dt.tz_localize(None)
    chart_data["종료"] = chart_data["종료"].dt.tz_localize(None)
    stage_order = ["각성", "렘수면", "코어 수면", "깊은 수면", "수면(단계 미분류)"]
    chart = alt.Chart(chart_data).mark_bar(cornerRadius=3).encode(
        x=alt.X("시작:T", title=f"기록 시각 ({record['timezone']})", axis=alt.Axis(format="%H:%M")),
        x2="종료:T", y=alt.Y("단계:N", title="기기에 기록된 단계", sort=stage_order),
        color=alt.Color("단계:N", scale=alt.Scale(domain=stage_order, range=["#e9b590", "#d0c0e8", "#a18acb", "#6856a5", "#c8ccd3"]), legend=None),
        tooltip=[alt.Tooltip("시작:T", format="%m/%d %H:%M:%S"), alt.Tooltip("종료:T", format="%m/%d %H:%M:%S"), "단계:N", "분:Q"],
    ).properties(height=260)
    st.altair_chart(chart, width="stretch")
    st.caption("실제 업로드한 기록의 시간과 단계입니다. 그래프에 마우스를 올리면 구간을 확인할 수 있습니다. 미기록 시간은 비워 표시하며, 기기 추정값은 진단 결과가 아닙니다.")
    return intervals


def render_records(user):
    sessions = list_sessions(user["id"])
    st.subheader("저장된 분석 기록 다시 보기")
    st.caption("파일을 다시 올리지 않아도 아래에서 과거 분석과 저장된 AI 코칭을 조회할 수 있습니다.")
    if not sessions:
        st.info("아직 내 기록이 없습니다. ‘새 분석’에서 파일을 올리거나 ‘휴지통·백업’에서 기록을 복원하세요.")
        return
    # Keep chart and AI SDK imports out of the login and empty-history paths.
    import altair as alt
    import pandas as pd
    import coaching_service
    earliest = date.fromisoformat(sessions[-1]["start"][:10])
    latest = date.fromisoformat(sessions[0]["start"][:10])
    period = st.sidebar.date_input("조회 기간 · 수면 시작일 기준", value=(earliest, latest), min_value=earliest, max_value=latest, key=f"period_{user['id']}_{earliest}_{latest}")
    if len(period) != 2:
        st.info("조회 시작일과 종료일을 선택하세요.")
        return
    sessions = [s for s in sessions if period[0].isoformat() <= s["start"][:10] <= period[1].isoformat()]
    if not sessions:
        st.info("선택한 기간에 기록이 없습니다.")
        return
    summary = overview(sessions)
    st.subheader("2. 기간별 수면 패턴")
    a, b, c = st.columns(3)
    a.metric("기록이 있는 날짜", f"{summary['recorded_days']}일")
    b.metric("기록일당 수면 합계 평균", duration(summary["average_asleep_minutes_per_recorded_day"]))
    c.metric("수면 기록", f"{summary['session_count']}회")
    st.caption(summary["note"])
    daily = pd.DataFrame(summary["daily"]).rename(columns={"date": "수면 시작일", "asleep_minutes": "수면(분)", "awake_minutes": "각성(분)"})
    st.bar_chart(daily.set_index("수면 시작일")[["수면(분)", "각성(분)"]])
    st.dataframe(pd.DataFrame([{"수면 시작": clock(s["start"]), "기록 종료": clock(s["end"]), "기기 추정 수면": duration(s["asleep_minutes"]), "각성": duration(s["awake_minutes"]), "저장된 코칭": s["coaching_count"]} for s in sessions]), hide_index=True, width="stretch")
    selected_id = st.selectbox("3. 자세히 볼 수면 기록", [s["analysis_id"] for s in sessions], format_func=lambda sid: next(f"{clock(s['start'])} · 코칭 {s['coaching_count']}건" for s in sessions if s["analysis_id"] == sid))
    s = next(s for s in sessions if s["analysis_id"] == selected_id)
    a, b, c = st.columns(3)
    a.metric("기기 추정 수면 시간", duration(s["asleep_minutes"]))
    b.metric("기기 추정 각성 시간", duration(s["awake_minutes"]))
    c.metric("각성 구간", f"{s['wake_segment_count']}회")
    st.write(f"{clock(s['start'])} ~ {clock(s['end'])} ({s['timezone']})")
    from json_sleep import to_json_export
    st.download_button("선택 기록 JSON 다운로드", to_json_export({"timezone": s["timezone"], "sessions": [s]}), "sleep_record.json", "application/json")
    with st.expander("선택한 분석 기록 삭제"):
        st.info("이 분석과 연결된 AI 코칭을 휴지통으로 옮깁니다. 30일 동안 복원할 수 있으며, 이후 앱 이용 시 자동으로 영구 삭제됩니다.")
        confirm_delete = st.checkbox("이 분석 기록과 연결된 AI 코칭을 삭제하겠습니다.", key=f"confirm_record_{selected_id}")
        if st.button("분석 기록 삭제", disabled=not confirm_delete, key=f"delete_record_{selected_id}"):
            if delete_session(selected_id, user["id"]):
                st.session_state["history_message"] = "선택한 분석과 연결된 코칭을 휴지통으로 옮겼습니다. 30일 안에 복원할 수 있습니다."
            st.rerun()
    st.caption("웨어러블 기기의 추정 기록입니다. 수면검사나 진단 결과가 아닙니다.")
    if s["unrecorded_minutes"] > 0:
        st.warning(f"이 기록에는 {duration(s['unrecorded_minutes'])}의 미기록 구간이 있습니다.")
    for warning in s["warnings"]:
        st.warning(warning)
    st.subheader("시간별 수면 양상")
    intervals = render_sleep_pattern(s)
    st.subheader("단계별 수면 시간")
    st.bar_chart(pd.DataFrame([{"단계": LABELS[k], "분": round(v, 1)} for k, v in s["stage_minutes"].items() if v > 0]).set_index("단계"))
    with st.expander("수면·각성 구간 전체 보기"):
        readable = intervals.copy()
        for column in ["시작", "종료"]:
            readable[column] = readable[column].map(lambda dt: dt.isoformat().replace("T", " "))
        st.dataframe(readable, hide_index=True, width="stretch")
        st.download_button("구간 CSV 다운로드", readable.to_csv(index=False).encode("utf-8-sig"), "sleep_intervals.csv", "text/csv")
    st.subheader("함께 측정된 생체지표")
    if s["vitals_summary"]:
        vitals = [{"지표": METRICS.get(v.get("metric"), v.get("metric")), "단위": v.get("unit"), "표본 수": v.get("n"), "평균": v.get("avg"), "최소": v.get("min"), "최대": v.get("max")} for v in s["vitals_summary"]]
        st.dataframe(pd.DataFrame(vitals), hide_index=True, width="stretch")
    else:
        st.info("이 기록에는 생체지표 요약이 없습니다.")
    st.caption("표본이 적거나 일부 구간에만 있으면 밤 전체의 상태를 대표하지 않을 수 있습니다.")
    st.subheader("4. 나의 기록에 맞춘 AI 코칭")
    with st.form("coaching"):
        age = st.selectbox("연령 구분", ["미입력", "성인", "미성년자"])
        caffeine = st.selectbox("취침 전 6시간 이내 카페인", ["미입력", "없음", "있음"])
        regularity = st.selectbox("평소 취침·기상 시간", ["미입력", "대체로 일정함", "자주 달라짐"])
        satisfaction = st.selectbox("수면 만족도", ["미입력", "좋음", "보통", "나쁨"])
        st.caption("기본 조언은 달잠 서버에서 기록과 생활습관 입력을 분석해 생성합니다. 서버에서 OpenAI 방식을 활성화한 경우 기록 요약과 입력이 전송되며 API 사용료가 발생할 수 있습니다.")
        if st.form_submit_button("AI 조언 생성"):
            try:
                with st.spinner("나의 기록을 바탕으로 조언을 작성하고 있습니다…"):
                    generated = coaching_service.generate(user["id"], selected_id, {"age_group": age, "caffeine": caffeine, "regularity": regularity, "satisfaction": satisfaction})
                st.session_state[f"coaching_history_{selected_id}"] = generated["id"]
                st.session_state["history_message"] = "새 AI 코칭을 저장했습니다. 아래에서 생성 근거도 확인할 수 있습니다."
                st.rerun()
            except Exception as error:
                code = getattr(error, "code", None)
                if code:
                    st.error(coaching_service.api_limit_detail(error)['message'])
                elif isinstance(error, (ValueError, RuntimeError)):
                    st.error(str(error))
                else:
                    st.error("조언 생성에 실패했습니다. 잠시 후 다시 시도하세요. 수면 기록은 저장되어 있습니다.")
    history = coaching_service.list_coaching(user["id"], selected_id)
    st.subheader("저장된 AI 코칭 다시 보기")
    if history:
        by_id = {item["id"]: item for item in history}
        coaching_id = st.selectbox("생성 시각별 AI 코칭", list(by_id), key=f"coaching_history_{selected_id}", format_func=lambda cid: pd.Timestamp(by_id[cid]["created_at"]).tz_convert("Asia/Seoul").strftime("%Y-%m-%d %H:%M:%S") + " (한국 시간)")
        saved = by_id[coaching_id]
        st.caption(f"이 분석에 저장된 코칭 {len(history)}건 · 최신순")
        st.write(saved["coaching"])
        render_alarm_settings(user, saved)
        with st.expander("코칭 생성 근거 · 사용 모델과 기록 범위"):
            context = saved.get("context")
            if context:
                st.write(f"모델: {context['model']} · 코칭 지침 버전: {context['prompt_version']}")
                st.write(f"참고 기록 {context['record_count']}회 · {clock(context['window_start'])} ~ {clock(context['window_end'])}")
                st.caption("아래는 생성 당시에 사용한 요약입니다. 현재 기록을 다시 계산한 값과 다를 수 있습니다.")
                st.json(context["input_summary"], expanded=False)
            else:
                st.info("이 코칭의 생성 근거는 저장되어 있지 않습니다. 기능 추가 전 코칭이거나 관련 분석의 영구 삭제로 요약이 정리된 경우입니다.")
        with st.expander("코칭 생성 당시 생활습관 입력"):
            names = {"age_group": "연령 구분", "caffeine": "취침 전 카페인", "regularity": "취침·기상 규칙성", "satisfaction": "수면 만족도"}
            for key, label in names.items():
                st.write(f"{label}: {saved['lifestyle'].get(key, '미입력')}")
        confirm_coaching = st.checkbox("선택한 AI 코칭을 삭제하겠습니다.", key=f"confirm_coaching_{coaching_id}")
        if st.button("선택한 AI 코칭 삭제", disabled=not confirm_coaching, key=f"delete_coaching_{coaching_id}"):
            if coaching_service.delete_coaching(user["id"], selected_id, coaching_id):
                st.session_state["history_message"] = "선택한 코칭을 휴지통으로 옮겼습니다. 분석 기록은 계속 조회할 수 있습니다."
            st.rerun()
    else:
        st.info("이 분석 기록에 저장된 AI 코칭이 없습니다.")


def render_alarm_settings(user, saved):
    import sleep_alarms
    from datetime import time
    sleep_alarms.start_worker()
    settings = sleep_alarms.get_settings(user['id'])
    proposal = (saved.get('context') or {}).get('alarm_schedule')
    st.subheader('취침·기상 알람')
    st.caption('매일 반복 · Windows PC 알람. PC가 켜져 있고 프로그램 서버가 실행 중이어야 합니다. 종료·절전 상태에서는 울리지 않습니다. 브라우저를 닫거나 로그아웃해도 서버가 실행 중이면 저장한 알람이 울립니다.')
    prefix = 'alarm_' + user['id']
    if proposal:
        st.write(f"AI 제안: 취침 {proposal.get('bedtime') or '추가 정보 필요'} · 기상 {proposal.get('wake_time') or '추가 정보 필요'} ({proposal['timezone']})")
        st.caption(proposal.get('reason',''))
        if proposal.get('bedtime') and proposal.get('wake_time') and st.button('AI 제안 시간 불러오기',key=prefix+'apply'):
            st.session_state[prefix+'bed']=time.fromisoformat(proposal['bedtime'])
            st.session_state[prefix+'wake']=time.fromisoformat(proposal['wake_time'])
            st.session_state[prefix+'zone']=proposal['timezone']
    else:
        st.info('이 코칭에는 제안 시간이 없습니다. 새 코칭을 생성하거나 시간을 직접 입력하세요.')
    with st.form(prefix+'form'):
        bed=st.time_input('취침 시간',value=time.fromisoformat(settings['bedtime']),key=prefix+'bed')
        wake=st.time_input('기상 시간',value=time.fromisoformat(settings['wake_time']),key=prefix+'wake')
        zone=st.text_input('시간대',value=settings['timezone'],key=prefix+'zone')
        enabled=st.checkbox('매일 알람 켜기',value=settings['enabled'],disabled=not settings['desktop_available'])
        if st.form_submit_button('알람 설정 저장'):
            try:
                sleep_alarms.save_settings(user['id'],bed.strftime('%H:%M'),wake.strftime('%H:%M'),zone,enabled)
                st.success('매일 알람을 저장했습니다.' if enabled else '알람을 껐습니다.')
            except ValueError as error: st.error(str(error))
    if st.button('알람 소리 시험',key=prefix+'test',disabled=not settings['desktop_available']):
        sleep_alarms.notify('bedtime')
        st.info('PC의 알람 창에서 확인을 누르면 소리가 멈춥니다. 소리는 최대 1분 동안 재생됩니다.')


def render_comparison(user):
    import altair as alt
    import pandas as pd
    st.subheader("기간별 수면 기록 비교")
    sessions = list_sessions(user["id"])
    if not sessions:
        st.info("비교할 기록이 없습니다. ‘새 분석’에서 기록을 저장하세요.")
        return
    days = st.radio("비교 단위", [7, 30], format_func=lambda n: f"{n}일", horizontal=True)
    end = st.date_input("비교 기준일", value=date.fromisoformat(sessions[0]["start"][:10]), key="comparison_end")
    st.caption("기본 기준일은 가장 최근 기록의 수면 시작일입니다. 기준일까지의 기간과 바로 앞의 같은 길이 기간을 비교합니다.")
    result = history_service.compare_periods(sessions, end, days)
    rows = []
    for label, period in (("선택 기간", result["current"]), ("직전 기간", result["previous"])):
        rows.append({"구분": label, "기간": f"{period['start']} ~ {period['end']}", "기록 있는 날": period["recorded_days"], "기록 수": period["session_count"], "기록일당 수면 합계 평균": duration(period["average_asleep_minutes_per_recorded_day"]) if period["recorded_days"] else "기록 없음", "기록일당 각성 합계 평균": duration(period["average_awake_minutes_per_recorded_day"]) if period["recorded_days"] else "기록 없음"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    current, previous = result["current"], result["previous"]
    if current["recorded_days"] and previous["recorded_days"]:
        difference = current["average_asleep_minutes_per_recorded_day"] - previous["average_asleep_minutes_per_recorded_day"]
        st.write(f"기록일당 수면 합계 평균 차이: {difference:+.1f}분")
    else:
        st.info("한쪽 기간에 기록이 없어 평균 차이를 계산하지 않습니다.")
    daily = pd.DataFrame(previous["daily"] + current["daily"]).rename(columns={"date": "수면 시작일", "asleep_minutes": "수면(분)", "awake_minutes": "각성(분)"})
    st.bar_chart(daily.set_index("수면 시작일")[["수면(분)", "각성(분)"]])
    st.caption("빈 날짜는 미기록입니다. 평균은 기록이 있는 날만 계산하며, 같은 날의 여러 기록은 합산합니다. 두 기간의 측정 범위가 다르면 직접적인 개선·악화로 해석할 수 없습니다.")
    starts = []
    for label, period in (("선택 기간", current), ("직전 기간", previous)):
        for session in period["sessions"]:
            t = pd.Timestamp(session["start"])
            starts.append({"날짜": session["start"][:10], "시작 시각(시)": t.hour + t.minute / 60, "시작": clock(session["start"]), "시간대": session["timezone"], "기간": label})
    if starts:
        st.write("기록별 수면 시작 시각")
        st.altair_chart(alt.Chart(pd.DataFrame(starts)).mark_circle(size=90).encode(x=alt.X("날짜:T"), y=alt.Y("시작 시각(시):Q", scale=alt.Scale(domain=[0, 24])), color="기간:N", tooltip=["시작:N", "시간대:N", "기간:N"]), width="stretch")
        st.caption("시각은 각 기록의 현지 시간입니다. 여러 시간대의 기록은 시간대 차이도 함께 고려하세요.")
    with st.expander("날짜별 수치 · 미기록 포함"):
        st.dataframe(daily, hide_index=True, width="stretch")


def render_trash(user):
    import pandas as pd
    st.subheader("휴지통")
    st.write("삭제한 기록과 코칭은 30일 동안 복원할 수 있습니다. 30일이 지나면 다음 로그인이나 앱 이용 시 영구 삭제합니다.")
    history = history_service.trash_history(user["id"])
    for kind, title, items in (("session", "분석 기록", history["sessions"]), ("coaching", "개별 삭제한 코칭", history["coaching"])):
        st.write(f"{title} · {len(items)}건")
        if not items:
            st.caption("휴지통에 항목이 없습니다.")
            continue
        choices = {item["id"]: item for item in items}
        def label(rid, choices=choices, kind=kind):
            item = choices[rid]
            start = item["record"]["start"] if kind == "session" else item["session_start"]
            suffix = "" if kind == "session" else f" · 코칭 생성 {clock(item['created_at'])} UTC"
            return clock(start) + suffix
        rid = st.selectbox(title, list(choices), format_func=label, key=f"trash_select_{kind}")
        item = choices[rid]
        expires = pd.Timestamp(item["expires_at"]).tz_convert("Asia/Seoul").strftime("%Y-%m-%d %H:%M")
        st.caption(f"복원 기한: {expires} (한국 시간)")
        blocked = kind == "coaching" and bool(item["parent_in_trash"])
        if kind == "coaching":
            st.write(item["coaching"])
            if blocked:
                st.info("연결된 분석이 휴지통에 있습니다. 분석을 먼저 복원해야 코칭을 복원할 수 있습니다.")
        if st.button(f"{title} 복원", key=f"restore_{kind}_{rid}", disabled=blocked):
            if history_service.restore_record(kind, rid, user["id"]):
                st.session_state["history_message"] = "복원했습니다. ‘과거 기록’에서 확인하세요."
            else:
                st.session_state["history_message"] = "기록이 변경되었거나 복원 기한이 지났습니다."
            st.rerun()
        confirm = st.checkbox("복구할 수 없는 영구 삭제에 동의합니다.", key=f"purge_confirm_{kind}_{rid}")
        if st.button(f"{title} 영구 삭제", key=f"purge_{kind}_{rid}", disabled=not confirm):
            history_service.purge_record(kind, rid, user["id"])
            st.session_state["history_message"] = "앱 DB에서 영구 삭제했습니다. 아래 백업 처리 상태도 확인하세요."
            st.rerun()
    render_backup_policy()


def render_backup_policy():
    st.subheader("백업 보관 및 영구 삭제 범위")
    status = backup_policy.maintain_backups()
    st.write(f"앱이 관리하는 DB 백업: {status['backup_count']}개 · 보관 기간: 30일")
    st.caption("백업은 앱 업데이트 시 생성하며, 이 화면을 열거나 다음 업데이트를 실행할 때 30일이 지난 관리 대상 백업을 정리합니다. 앱이 꺼져 있는 동안에는 정리 작업이 실행되지 않습니다.")
    if status["pending"]:
        st.warning(f"백업 {status['pending']}개의 정리가 완료되지 않았습니다. 파일 접근 상태를 확인하고 ‘백업 정리 다시 시도’를 눌러 주세요. 영구 삭제 대상은 재시도를 위해 식별자만 보관합니다.")
    else:
        st.success("현재 관리 대상 백업에 영구 삭제 내역을 반영했습니다.")
    if st.button("백업 정리 다시 시도"):
        st.rerun()
    st.write("분석을 영구 삭제하면 앱 DB와 관리 대상 백업에서 해당 분석·수면 구간·직접 연결된 코칭 및 다른 분석과 공유하지 않는 해당 구간의 표본을 정리합니다. 다른 코칭의 참고 요약에 포함된 사본도 제거합니다.")
    st.caption("직접 업로드한 원본 파일, 외부에 복사한 DB·백업, 다운로드 파일은 삭제 대상이 아닙니다. 호스팅 업체가 만드는 자동 스냅샷은 업체의 보관·삭제 정책을 따릅니다. 다른 분석에 저장된 코칭 문장에 간접적으로 반영된 내용은 자동 수정하지 않습니다. 저장 장치의 물리적 복구 불가능성을 보장하는 기능은 아닙니다.")


def account_changed(message, pending=False):
    st.session_state.clear()
    st.session_state["login_notice"] = message
    if pending:
        st.session_state["account_backup_pending"] = True
    st.rerun()


def render_account_settings(user):
    st.subheader("계정 설정")
    st.write(f"현재 아이디: {user['username']}")
    st.caption("아이디·비밀번호를 변경하려면 현재 비밀번호를 확인합니다. 변경 후 모든 기기에서 로그아웃되며 다시 로그인해야 합니다. 기존 수면 기록과 코칭은 유지됩니다.")
    with st.form("account_username"):
        st.write("아이디 변경")
        username = st.text_input("변경할 아이디", value=user["username"], key="account_new_username", help="문자·숫자·밑줄·점·하이픈 3~40자")
        password = st.text_input("현재 비밀번호", type="password", key="account_username_password")
        if st.form_submit_button("아이디 변경"):
            try:
                result = update_account(user["id"], password, new_username=username)
                account_changed(f"아이디를 {result['username']}로 변경했습니다. 변경한 아이디로 다시 로그인하세요.")
            except ValueError as error:
                st.error(str(error))
    with st.form("account_password"):
        st.write("비밀번호 변경")
        current = st.text_input("현재 비밀번호", type="password", key="account_current_password")
        new = st.text_input("새 비밀번호", type="password", key="account_new_password", help="10~128자")
        confirm = st.text_input("새 비밀번호 확인", type="password", key="account_confirm_password")
        if st.form_submit_button("비밀번호 변경"):
            try:
                if new != confirm:
                    raise ValueError("새 비밀번호 확인이 일치하지 않습니다.")
                update_account(user["id"], current, new_password=new)
                account_changed("비밀번호를 변경했습니다. 새 비밀번호로 다시 로그인하세요.")
            except ValueError as error:
                st.error(str(error))
    with st.expander("계정 삭제"):
        st.warning("계정을 삭제하면 로그인 정보, 수면 분석, AI 코칭, 휴지통, 생체지표를 영구 삭제합니다. 계정 삭제에는 30일 복원 기간이 없으며 되돌릴 수 없습니다.")
        st.caption("관리 대상 백업에도 계정 삭제를 반영합니다. 원본 업로드 파일·다운로드 파일·외부 복사본은 삭제하지 않습니다. 호스팅 업체의 자동 스냅샷은 업체 보관 정책을 따릅니다. 백업 처리 재시도를 위해 계정 식별자와 삭제 시각은 남기며, 요청 한도 집계에는 계정과 분리한 요청 시각만 남깁니다.")
        with st.form("account_delete"):
            delete_password = st.text_input("삭제 확인용 현재 비밀번호", type="password", key="account_delete_password")
            confirmation = st.text_input("확인 문구: 계정 삭제", key="account_delete_confirmation")
            agreed = st.checkbox("이 계정과 모든 저장 기록을 영구 삭제하는 데 동의합니다.", key="account_delete_agreed")
            if st.form_submit_button("계정 영구 삭제"):
                try:
                    if not agreed:
                        raise ValueError("영구 삭제 동의란을 체크하세요.")
                    result = delete_account(user["id"], delete_password, confirmation)
                    account_changed("계정과 해당 계정의 저장 데이터를 영구 삭제했습니다.", pending=bool(result["backups"]["pending"]))
                except ValueError as error:
                    st.error(str(error))
