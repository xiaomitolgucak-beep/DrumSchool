import streamlit as st
from datetime import datetime, time, timedelta, date
from typing import List, Dict, Any
import json
import os
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="Haftalık Ders Planı", layout="wide")

# ---------- Sabitler ----------
DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"]
TIME_SLOTS: List[time] = [time(h, m) for h in range(8, 22) for m in (0, 30)]
if time(22, 0) not in TIME_SLOTS:
    TIME_SLOTS.append(time(22, 0))
DATA_FILE = "ritim_data.json"
LOGO_FILE = "drumschool.jpeg"

# ---------- State (Veri Yönetimi) ----------
def save_state():
    data_to_save = st.session_state.app.copy()
    schedule_str = {day: [] for day in DAYS}
    for day, lessons in data_to_save.get("schedule", {}).items():
        for lesson in lessons:
            lesson_copy = lesson.copy()
            lesson_copy["start"] = lesson["start"].strftime('%H:%M:%S')
            lesson_copy["end"] = lesson["end"].strftime('%H:%M:%S')
            schedule_str[day].append(lesson_copy)
    data_to_save["schedule"] = schedule_str
    students_str = []
    for student in data_to_save.get("students", []):
        student_copy = student.copy()
        for key in ["dob", "next_payment_due_date", "last_payment_date"]:
             if student_copy.get(key) and isinstance(student_copy[key], date):
                student_copy[key] = student_copy[key].isoformat()
        if "payment_history" in student_copy:
            student_copy["payment_history"] = [d.isoformat() for d in student_copy["payment_history"]]
        students_str.append(student_copy)
    data_to_save["students"] = students_str
    data_to_save["working_hours"] = [t.strftime('%H:%M:%S') for t in data_to_save["working_hours"]]
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=4)

def load_state():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if data.get("students"):
                migrated_students = []
                for i, student_data in enumerate(data["students"]):
                    if isinstance(student_data, str): 
                        migrated_students.append({"id": i + 1, "name": student_data, "parent_name": "", "parent_phone": "", "dob": None, "payment_day": 1, "next_payment_due_date": None, "last_payment_date": None, "payment_history": []})
                    else:
                        student_data.pop("credits", None)
                        if "payment_day" not in student_data: student_data["payment_day"] = 1
                        if "next_payment_due_date" not in student_data: student_data["next_payment_due_date"] = None
                        if "last_payment_date" not in student_data: student_data["last_payment_date"] = None
                        if "payment_history" not in student_data: student_data["payment_history"] = []
                        migrated_students.append(student_data)
                data["students"] = migrated_students
            
            for day, lessons in data.get("schedule", {}).items():
                for lesson in lessons:
                    lesson["start"] = datetime.strptime(lesson["start"], '%H:%M:%S').time()
                    lesson["end"] = datetime.strptime(lesson["end"], '%H:%M:%S').time()
            
            for student in data.get("students", []):
                for key in ["dob", "next_payment_due_date", "last_payment_date"]:
                    if student.get(key):
                        try: student[key] = datetime.fromisoformat(student[key]).date()
                        except (ValueError, TypeError): student[key] = None
                if "payment_history" in student:
                    student["payment_history"] = sorted([datetime.fromisoformat(d).date() for d in student["payment_history"]], reverse=True)

            data["working_hours"] = tuple(datetime.strptime(t, '%H:%M:%S').time() for t in data["working_hours"])
            return data
            
    return {"students": [{"id": i, "name": f"Öğrenci {i}", "parent_name": "", "parent_phone": "", "dob": None, "payment_day": 1, "next_payment_due_date": None, "last_payment_date": None, "payment_history": []} for i in range(1, 41)],"schedule": {day: [] for day in DAYS},"working_hours": (time(8, 0), time(22, 0))}

def init_state():
    if "app" not in st.session_state:
        st.session_state.app = load_state()
    if "selected_lesson" not in st.session_state:
        st.session_state.selected_lesson = None
init_state()

# ---------- Helpers ----------
def to_dt(t: time) -> datetime: return datetime.combine(date.today(), t)
def hhmm(t: time) -> str: return t.strftime("%H:%M")
def check_conflict(day: str, start_t: time, end_t: time) -> bool:
    for ev in st.session_state.app["schedule"].get(day, []):
        if to_dt(start_t) < to_dt(ev["end"]) and to_dt(end_t) > to_dt(ev["start"]):
            return True
    return False
def add_lesson(day: str, start_t: time, dur_minutes: int, student_name: str) -> bool:
    end_t = (to_dt(start_t) + timedelta(minutes=dur_minutes)).time()
    wh_start, wh_end = st.session_state.app["working_hours"]
    if to_dt(start_t) < to_dt(wh_start) or to_dt(end_t) > to_dt(wh_end):
        st.error("Ders mesai saatleri dışında."); return False
    if check_conflict(day, start_t, end_t):
        st.error("Bu zaman aralığında çakışma var."); return False
    st.session_state.app["schedule"][day].append({"student": student_name, "start": start_t, "end": end_t, "status": "Planlandı"})
    st.session_state.app["schedule"][day].sort(key=lambda e: e["start"])
    save_state()
    return True
def duration_to_slots(start_t: time, end_t: time) -> int:
    mins = int((to_dt(end_t) - to_dt(start_t)).total_seconds() // 60)
    return max(1, mins // 30)
def calculate_statistics():
    wh_start, wh_end = st.session_state.app["working_hours"]
    daily_available_minutes = (to_dt(wh_end) - to_dt(wh_start)).total_seconds() / 60
    total_available_minutes = daily_available_minutes * len(DAYS)
    total_filled_minutes = 0
    for day in DAYS:
        for lesson in st.session_state.app["schedule"].get(day, []):
            lesson_duration = (to_dt(lesson["end"]) - to_dt(lesson["start"])).total_seconds() / 60
            total_filled_minutes += lesson_duration
    total_empty_minutes = total_available_minutes - total_filled_minutes
    occupancy_rate = (total_filled_minutes / total_available_minutes) * 100 if total_available_minutes > 0 else 0
    return {"filled_hours": total_filled_minutes / 60, "empty_hours": total_empty_minutes / 60, "occupancy_rate": occupancy_rate}

# ---------- Callback Fonksiyonları ----------
def update_status_and_close(day, index, new_status):
    st.session_state.app["schedule"][day][index]["status"] = new_status
    save_state()
    st.session_state.selected_lesson = None

def delete_payment(student_index, payment_to_delete):
    student = st.session_state.app["students"][student_index]
    history = student["payment_history"]
    if payment_to_delete in history:
        history.remove(payment_to_delete)
        history.sort(reverse=True)
        if history:
            new_last_payment = history[0]
            student["last_payment_date"] = new_last_payment
            payment_day = student.get("payment_day", 1)
            next_due_date = new_last_payment + relativedelta(months=1)
            try: next_due_date = next_due_date.replace(day=payment_day)
            except ValueError: next_due_date = (next_due_date + relativedelta(months=1)).replace(day=1) - timedelta(days=1)
            student["next_payment_due_date"] = next_due_date
        else:
            student["last_payment_date"] = None
            student["next_payment_due_date"] = None
        save_state()
        st.success(f"{payment_to_delete.strftime('%d %b')} tarihli ödeme silindi.")

# ---------- Başlık ve Arayüz Ayarları ----------
st.markdown("""<style>.block-container {padding-top: 2rem;}</style>""", unsafe_allow_html=True)
st.markdown("## 🥁 Haftalık Ders Planı (Drum School)")

# ---------- Sidebar ----------
with st.sidebar:
    with st.expander("➕ Ders Ekle", expanded=True):
        day = st.selectbox("Gün", DAYS)
        start_str = st.selectbox("Başlangıç", [t.strftime('%H:%M') for t in TIME_SLOTS])
        duration_map = {"30 dk": 30, "1 saat": 60, "2 saat": 120}
        duration_str = st.selectbox("Süre", list(duration_map.keys()), index=1)
        dur_minutes = duration_map[duration_str]
        start_t = datetime.strptime(start_str, '%H:%M').time()
        students = st.session_state.app["students"]
        student_to_add = st.selectbox("Öğrenci Seç", students, format_func=lambda s: s['name'])
        if st.button("Dersi Ekle", use_container_width=True):
            if student_to_add and add_lesson(day, start_t, dur_minutes, student_to_add['name']):
                st.success(f"Eklendi: {day} {start_str} - {student_to_add['name']}")
                st.rerun()

    with st.expander("👥 Öğrenci Yönetimi"):
        st.write("Öğrenci Bilgilerini Düzenle")
        all_students = st.session_state.app["students"]
        selected_student_manage = st.selectbox("Düzenlenecek Öğrenci", all_students, format_func=lambda s: s['name'], key="student_select_manage")
        if selected_student_manage:
            student_index = next((i for i, s in enumerate(all_students) if s['id'] == selected_student_manage['id']), None)
            if student_index is not None:
                due_date = selected_student_manage.get("next_payment_due_date")
                if due_date and date.today() > due_date:
                    overdue_days = (date.today() - due_date).days
                    st.error(f"Ödeme Durumu: {overdue_days} gün gecikmede!")
                elif due_date:
                    st.info(f"Sonraki Ödeme: {due_date.strftime('%d %B %Y')}")
                else:
                    st.warning("Ödeme planı henüz ayarlanmamış.")
                with st.form(key=f"student_form_{selected_student_manage['id']}"):
                    st.subheader(f"{selected_student_manage['name']} Bilgileri")
                    new_name = st.text_input("Öğrenci Adı", value=selected_student_manage['name'])
                    parent_name = st.text_input("Veli Adı", value=selected_student_manage.get('parent_name', ''))
                    parent_phone = st.text_input("Veli Telefonu", value=selected_student_manage.get('parent_phone', ''))
                    dob = st.date_input("Doğum Tarihi", value=selected_student_manage.get('dob'), min_value=datetime(1950,1,1).date(), max_value=date.today())
                    if st.form_submit_button("Bilgileri Kaydet", use_container_width=True):
                        all_students[student_index]['name'] = new_name
                        all_students[student_index]['parent_name'] = parent_name
                        all_students[student_index]['parent_phone'] = parent_phone
                        all_students[student_index]['dob'] = dob
                        save_state()
                        st.success(f"{new_name} bilgileri güncellendi.")
                        st.rerun()

    with st.expander("💰 Ödeme Yönetimi"):
        st.write("Aylık Ödeme Takibi")
        all_students = st.session_state.app["students"]
        student_for_payment = st.selectbox("Öğrenci Seç", all_students, format_func=lambda s: s['name'], key="student_payment")
        if student_for_payment:
            student_index = next((i for i, s in enumerate(all_students) if s['id'] == student_for_payment['id']), None)
            due_date = student_for_payment.get("next_payment_due_date")
            st.markdown("##### Güncel Durum")
            if due_date and date.today() > due_date:
                overdue_days = (date.today() - due_date).days
                st.error(f"{overdue_days} GÜN GECİKMEDE")
            elif due_date:
                st.success(f"ÖDENDİ")
            else:
                st.warning("İlk ödeme bekleniyor.")
            st.info(f"Sonraki Ödeme Tarihi: **{due_date.strftime('%d %B %Y') if due_date else 'Belirsiz'}**")
            st.markdown("---")
            st.markdown("##### Ödeme Kaydı")
            if st.button("Ödeme Alındı", use_container_width=True, type="primary"):
                payment_date = date.today()
                payment_day = all_students[student_index].get("payment_day", 1)
                next_due_date = payment_date + relativedelta(months=1)
                try: next_due_date = next_due_date.replace(day=payment_day)
                except ValueError: next_due_date = (next_due_date + relativedelta(months=1)).replace(day=1) - timedelta(days=1)
                all_students[student_index]["last_payment_date"] = payment_date
                all_students[student_index]["next_payment_due_date"] = next_due_date
                if payment_date not in all_students[student_index]["payment_history"]:
                    all_students[student_index]["payment_history"].insert(0, payment_date)
                save_state()
                st.success(f"Ödeme kaydedildi. Sonraki ödeme: {next_due_date.strftime('%d %B %Y')}")
                st.rerun()
            with st.form("past_payment_form"):
                st.markdown("###### Geçmiş Bir Ödemeyi Ekle")
                past_payment_date = st.date_input("Ödemenin Alındığı Tarih", max_value=date.today())
                if st.form_submit_button("Geçmiş Ödemeyi Kaydet"):
                    history = all_students[student_index]["payment_history"]
                    if past_payment_date not in history:
                        history.append(past_payment_date)
                        history.sort(reverse=True)
                        last_payment = history[0]
                        payment_day = all_students[student_index].get("payment_day", 1)
                        next_due_date = last_payment + relativedelta(months=1)
                        try: next_due_date = next_due_date.replace(day=payment_day)
                        except ValueError: next_due_date = (next_due_date + relativedelta(months=1)).replace(day=1) - timedelta(days=1)
                        all_students[student_index]["last_payment_date"] = last_payment
                        all_students[student_index]["next_payment_due_date"] = next_due_date
                        save_state()
                        st.success(f"Geçmiş ödeme {past_payment_date.strftime('%d %b')} tarihinde kaydedildi.")
                        st.rerun()
                    else:
                        st.warning("Bu tarihte zaten bir ödeme kaydı var.")
            st.markdown("---")
            st.markdown("##### Ödeme Geçmişi")
            history = student_for_payment.get("payment_history", [])
            if not history:
                st.write("Kayıtlı ödeme yok.")
            else:
                for p_date in history:
                    col1, col2 = st.columns([3, 1])
                    col1.text(p_date.strftime('%d %B %Y, %A'))
                    col2.button("Sil", key=f"del_{student_for_payment['id']}_{p_date.isoformat()}", on_click=delete_payment, args=(student_index, p_date), use_container_width=True)

    with st.expander("⚙️ Mesai Saatleri"):
        current_wh_start, current_wh_end = st.session_state.app["working_hours"]
        time_str_list = [t.strftime('%H:%M') for t in TIME_SLOTS]
        start_index = time_str_list.index(current_wh_start.strftime('%H:%M'))
        end_index = time_str_list.index(current_wh_end.strftime('%H:%M'))
        wh_start_str = st.selectbox("Gün Başlangıcı", time_str_list, index=start_index)
        wh_end_str = st.selectbox("Gün Bitişi", time_str_list, index=end_index)
        whs = datetime.strptime(wh_start_str, '%H:%M').time()
        whe = datetime.strptime(wh_end_str, '%H:%M').time()
        if (whs, whe) != st.session_state.app["working_hours"]:
            if to_dt(whs) >= to_dt(whe):
                st.warning("Başlangıç, bitişten önce olmalı.")
            else:
                st.session_state.app["working_hours"] = (whs, whe)
                save_state()
                st.rerun()
    
    st.divider()
    if os.path.exists(LOGO_FILE):
        st.image(LOGO_FILE, use_container_width=True)

# (Kalan kodlar öncekiyle aynı)
# Adres Çubuğu ve Pop-up Mantığı
if 'action' in st.query_params and 'day' in st.query_params and 'start' in st.query_params:
    day = st.query_params['day']
    start_time = datetime.strptime(st.query_params['start'], '%H:%M:%S').time()
    lesson_index, lesson = next(
        ((idx, l) for idx, l in enumerate(st.session_state.app["schedule"].get(day, [])) if l['start'] == start_time), (None, None))
    if lesson:
        st.session_state.selected_lesson = {"lesson": lesson, "day": day, "index": lesson_index}
    st.query_params.clear()
if st.session_state.selected_lesson:
    info = st.session_state.selected_lesson
    lesson = info["lesson"]
    @st.dialog(f"Ders Durumunu Güncelle")
    def status_popup():
        st.markdown(f"**Öğrenci:** {lesson['student']}")
        st.markdown(f"**Zaman:** {info['day']} {hhmm(lesson['start'])} - {hhmm(lesson['end'])}")
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        if c1.button("✅ Yapıldı", use_container_width=True, type="primary"):
            update_status_and_close(info['day'], info['index'], "Yapıldı"); st.rerun()
        if c2.button("👤 Yapılmadı (Öğrenci)", use_container_width=True):
            update_status_and_close(info['day'], info['index'], "Yapılmadı-Öğrenci"); st.rerun()
        if c3.button("👨‍🏫 Yapılmadı (Eğitmen)", use_container_width=True):
            update_status_and_close(info['day'], info['index'], "Yapılmadı-Eğitmen"); st.rerun()
    status_popup()
# CSS Kodları
st.markdown("""<style>.table-container { height: 75vh; overflow-y: auto; } .schedule-table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 13px; } .schedule-table th, .schedule-table td { border: 1px solid rgba(255,255,255,0.15); padding: 0; text-align: center; vertical-align: top; } .schedule-table thead th { position: sticky; top: -1px; background: rgba(17, 17, 17, 0.95); z-index: 10; padding: 6px 8px; } .time-col { position: sticky; left: 0; background: rgba(17, 17, 17, 0.95); font-weight: 700; width: 80px; z-index: 11; padding: 6px 8px; } .lesson-link { display: block; height: 100%; text-decoration: none; color: white; padding: 6px 8px; } .cell-text { line-height: 1.3; } .cell-text small { opacity: .8; } .cell-occupied { background: #2F3C7E; } .cell-done { background: #1E5128; } .cell-student-absent { background: #D04E00; } .cell-teacher-absent { background: #A04000; } </style>""", unsafe_allow_html=True)
# Tablo Render
def render_table_html() -> str:
    wh_start, wh_end = st.session_state.app["working_hours"]
    html = ['<table class="schedule-table">']
    html.append("<thead><tr><th class='time-col'>Saat</th>")
    for d in DAYS: html.append(f"<th>{d}</th>")
    html.append("</tr></thead><tbody>")
    skip = set()
    for row_idx, slot_start in enumerate(TIME_SLOTS):
        if slot_start == time(22, 0): continue
        row_html = [f'<td class="time-col">{hhmm(slot_start)}</td>']
        for day in DAYS:
            key = (day, row_idx)
            if key in skip: continue
            ev = next((cand for cand in st.session_state.app["schedule"].get(day, []) if cand["start"] == slot_start), None)
            if ev:
                span = duration_to_slots(ev["start"], ev["end"])
                for k in range(1, span): skip.add((day, row_idx + k))
                status = ev.get("status", "Planlandı")
                color_map = {"Planlandı": "cell-occupied", "Yapıldı": "cell-done", "Yapılmadı-Öğrenci": "cell-student-absent", "Yapılmadı-Eğitmen": "cell-teacher-absent"}
                cls = color_map.get(status, "cell-occupied")
                link_href = f"?action=edit_lesson&day={day}&start={ev['start'].strftime('%H:%M:%S')}"
                cell_content = (f"<a href='{link_href}' target='{'_self'}' class='lesson-link'><div class='cell-text'><b>{ev['student']}</b><br><small>{hhmm(ev['start'])}–{hhmm(ev['end'])}</small><br><small><i>{status}</i></small></div></a>")
                row_html.append(f'<td class="{cls}" rowspan="{span}">{cell_content}</td>')
            else:
                if to_dt(slot_start) < to_dt(wh_start) or to_dt(slot_start) >= to_dt(wh_end):
                    row_html.append('<td style="background:rgba(0,0,0,0.3);"></td>')
                else:
                    row_html.append('<td></td>')
        html.append("<tr>" + "".join(row_html) + "</tr>")
    html.append("</tbody></table>")
    return "\n".join(html)
table_html = render_table_html()
st.markdown(f'<div class="table-container">{table_html}</div>', unsafe_allow_html=True)
# Öğrenci Bazlı Özet ve İstatistikler
st.divider()
with st.expander("📊 Öğrenci Bazlı Özet (Yapılmayan Dersler)"):
    any_uncompleted = False
    for s_obj in st.session_state.app["students"]:
        student_fault = 0
        teacher_fault = 0
        for d in DAYS:
            for ev in st.session_state.app["schedule"].get(d, []):
                if ev["student"] == s_obj['name']:
                    if ev.get("status") == "Yapılmadı-Öğrenci":
                        student_fault += 1
                    elif ev.get("status") == "Yapılmadı-Eğitmen":
                        teacher_fault += 1
        total_uncompleted = student_fault + teacher_fault
        if total_uncompleted > 0:
            any_uncompleted = True
            st.markdown(f"**{s_obj['name']}**")
            st.markdown(f"- Telafi Sayısı: **{total_uncompleted}** (Öğrenci: {student_fault} - Eğitmen: {teacher_fault})")
    if not any_uncompleted:
        st.info("Yapılmamış ders bulunmuyor.")
stats = calculate_statistics()
with st.expander("📈 Haftalık İstatistikler", expanded=True):
    col1, col2, col3 = st.columns(3)
    col1.metric(label="Doluluk Oranı", value=f"{stats['occupancy_rate']:.1f}%")
    col2.metric(label="Dolu Saatler", value=f"{stats['filled_hours']:.1f} saat")
    col3.metric(label="Boş Saatler", value=f"{stats['empty_hours']:.1f} saat")