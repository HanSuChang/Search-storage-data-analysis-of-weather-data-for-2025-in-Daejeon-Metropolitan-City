import sys
import glob
import importlib.util
from pathlib import Path
from tkinter import ttk
import os
import re
import calendar
from datetime import date

import pandas as pd
import tkinter as tk
from tkinter import messagebox


# 0) CSV 로드 + 전처리
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "OBS_ASOS_DD_20260115112034.csv")


def load_weather_df(csv_path: str) -> pd.DataFrame:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다:\n{csv_path}")

    # ASOS CSV는 보통 cp949 (안 열리면 'euc-kr')
    df = pd.read_csv(csv_path, encoding="cp949")

    # 컬럼명 앞뒤 공백/줄바꿈 제거
    df.columns = df.columns.astype(str).str.strip()

    if "일시" not in df.columns:
        raise KeyError("CSV에 '일시' 컬럼이 없습니다. 파일/컬럼명을 확인하세요.")

    df["일시"] = pd.to_datetime(df["일시"], errors="coerce")
    if df["일시"].isna().any():
        bad = df[df["일시"].isna()].head(5)
        raise ValueError(f"일시 datetime 변환 실패 행이 있어요. 예시:\n{bad}")

    df["date"] = df["일시"].dt.date

    # 강수량: 숫자화 + NaN -> 0
    if "일강수량(mm)" in df.columns:
        df["일강수량(mm)"] = pd.to_numeric(df["일강수량(mm)"], errors="coerce").fillna(0)
    else:
        pass

    return df


# 1) 날짜 입력
def parse_date_input(date_text: str):

    if date_text is None:
        raise ValueError("날짜 입력이 비었습니다.")

    s = str(date_text).strip()
    if not s:
        raise ValueError("날짜 입력이 비었습니다.")

    # 숫자만 입력된 경우 처리
    if re.fullmatch(r"\d+", s):
        # YYYYMMDD
        if len(s) == 8:
            s = f"{s[0:4]}-{s[4:6]}-{s[6:8]}"

        # YYMMDD
        elif len(s) == 6:
            s = f"20{s[0:2]}-{s[2:4]}-{s[4:6]}"

        # 7자리(YYMMDDD) 케이스
        elif len(s) == 7:
            year = s[0:2]
            month = s[2:4]
            day = s[4:7]
            day = day.lstrip("0")  # 031 -> 31
            s = f"20{year}-{month}-{day}"

    # 구분자 통일
    s = s.replace("/", "-").replace(".", "-")

    dt = pd.to_datetime(s, errors="coerce")
    if pd.isna(dt):
        raise ValueError(
            f"날짜 형식을 인식할 수 없습니다: '{date_text}'\n"
            f"(예: 2025-03-01 / 20250301 / 2503031)"
        )

    return dt.date()


# 2) 날짜로 검색
def find_by_date(df: pd.DataFrame, date_text: str) -> pd.DataFrame:
    target = parse_date_input(date_text)
    return df[df["date"] == target].copy()


# 3) 검색 결과 CSV 저장
def save_result_csv(result_df: pd.DataFrame, export_dir="exports", prefix="daejeon_weather") -> str:
    if result_df is None or result_df.empty:
        raise ValueError("저장할 검색 결과가 없습니다(빈 결과).")

    export_path = os.path.join(BASE_DIR, export_dir)
    os.makedirs(export_path, exist_ok=True)

    d = result_df["date"].iloc[0]
    out_file = f"{prefix}_{d}.csv"
    full_path = os.path.join(export_path, out_file)

    result_df.to_csv(full_path, index=False, encoding="utf-8-sig")
    return full_path


# 4) UI 표시용 유틸
def safe_value(row: pd.Series, col: str, default="-"):
    if col not in row.index:
        return default
    v = row[col]
    if pd.isna(v):
        return default
    return v


def make_summary_text(result_df: pd.DataFrame) -> str:
    row = result_df.iloc[0]

    items = [
        ("평균기온(°C)", "평균기온(°C)"),
        ("최고기온(°C)", "최고기온(°C)"),
        ("최저기온(°C)", "최저기온(°C)"),
        ("일강수량(mm)", "일강수량(mm)"),
        ("평균 상대습도(%)", "평균 상대습도(%)"),
        ("평균 풍속(m/s)", "평균 풍속(m/s)"),
        ("안개 계속시간(hr)", "안개 계속시간(hr)"),
        ("합계 일조시간(hr)", "합계 일조시간(hr)"),
    ]

    lines = [f" 검색 성공: {row['date']}", ""]
    for label, col in items:
        val = safe_value(row, col, default="-")
        if col == "일강수량(mm)" and val != "-":
            try:
                val = float(val)
                if val == 0.0:
                    val = 0
            except Exception:
                pass
        lines.append(f"- {label}: {val}")
    return "\n".join(lines)


# 5) 달력: 계절 테마 + 이모지/요약
def season_from_month(month: int) -> str:
    if month in (3, 4, 5):
        return "봄"
    if month in (6, 7, 8):
        return "여름"
    if month in (9, 10, 11):
        return "가을"
    return "겨울"  # 12, 1, 2


SEASON_THEME = {
    "봄": {"bg": "#FFF5FA", "header_bg": "#FFD6E7", "accent": "#D81B60", "empty_bg": "#FFF9FC"},
    "여름": {"bg": "#F2FBFF", "header_bg": "#CDEFFF", "accent": "#0277BD", "empty_bg": "#F7FCFF"},
    "가을": {"bg": "#FFF7E6", "header_bg": "#FFE0A3", "accent": "#E65100", "empty_bg": "#FFFBF2"},
    "겨울": {"bg": "#F3F6FF", "header_bg": "#DDE6FF", "accent": "#1A237E", "empty_bg": "#F8FAFF"},
}


def get_emoji_for_day(row: pd.Series) -> str:
    # 비/안개/눈 판단 (없으면 맑음)
    rain = row.get("일강수량(mm)", 0)
    fog = row.get("안개 계속시간(hr)", 0)
    snow = row.get("합계 일적설(cm)", 0)  # 파일에 없을 수도 있음

    try:
        rain = 0 if pd.isna(rain) else float(rain)
    except Exception:
        rain = 0

    try:
        fog = 0 if pd.isna(fog) else float(fog)
    except Exception:
        fog = 0

    try:
        snow = 0 if pd.isna(snow) else float(snow)
    except Exception:
        snow = 0

    # (우선순위: 눈 > 안개 > 비 > 맑음)
    if snow > 0:
        return "❄️"
    if fog > 0:
        return "🌫️"
    if rain > 0:
        return "🌧️"
    return "☀️"


def build_day_summary(row: pd.Series) -> str:

    tmax = row.get("최고기온(°C)", None)
    tmin = row.get("최저기온(°C)", None)

    try:
        tmax = None if pd.isna(tmax) else float(tmax)
    except Exception:
        tmax = None
    try:
        tmin = None if pd.isna(tmin) else float(tmin)
    except Exception:
        tmin = None

    if tmax is None or tmin is None:
        temp_text = "-"
    else:
        temp_text = f"{tmax:.1f}/{tmin:.1f}℃"

    rain_mm = row.get("일강수량(mm)", 0)
    try:
        rain_mm = 0 if pd.isna(rain_mm) else float(rain_mm)
    except Exception:
        rain_mm = 0

    if rain_mm > 0:
        if float(rain_mm).is_integer():
            rain_text = f"{int(rain_mm)}mm"
        else:
            rain_text = f"{rain_mm:.1f}mm"
        return f"{temp_text}\n☔ {rain_text}"

    return temp_text


# 6) Tkinter 앱
class WeatherApp:
    def __init__(self, root: tk.Tk, df: pd.DataFrame):
        self.root = root
        self.df = df
        self.last_result = None

        # 달력에서 월 이동을 위해 상태 저장
        self.cal_year = 2025
        self.cal_month = 1

        # date -> row 빠른 접근
        self.date_map = {}
        for _, r in self.df.iterrows():
            self.date_map[r["date"]] = r

        root.title("대전 2025 일별 날씨 검색/저장")
        root.geometry("520x300")
        root.resizable(False, False)

        top_row = tk.Frame(root)
        top_row.pack(padx=12, pady=(12, 4), fill="x")

        self.lbl = tk.Label(
            top_row,
            text="날짜 입력 (예: 250301 / 20250301):",
            anchor="w"
        )
        self.lbl.pack(side="left")

        tk.Button(
            top_row,
            text="저장된 날씨",
            command=self.show_saved_weather
        ).pack(side="right")

        tk.Button(
            top_row,
            text="연간 분석",
            command=self.open_year_weather
        ).pack(side="right", padx=(6, 0))

        self.entry = tk.Entry(root, width=30)
        self.entry.pack(padx=12, pady=(0, 10), anchor="w")
        self.entry.focus()

        self.result_var = tk.StringVar()
        self.result_var.set("검색 결과가 여기에 표시됩니다.")
        self.result_label = tk.Label(root, textvariable=self.result_var, justify="left", anchor="nw")
        self.result_label.pack(padx=12, pady=(0, 10), fill="both", expand=True)

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="검색(Enter)", width=12, command=self.on_search).grid(row=0, column=0, padx=8)
        tk.Button(btn_frame, text="검색결과 저장", width=12, command=self.on_save).grid(row=0, column=1, padx=8)
        tk.Button(btn_frame, text="달력", width=12, command=self.open_calendar).grid(row=0, column=2, padx=8)

        root.bind("<Return>", lambda e: self.on_search())

    def on_search(self):
        date_text = self.entry.get().strip()

        try:
            result = find_by_date(self.df, date_text)
            if result.empty:
                self.last_result = None
                target = parse_date_input(date_text)
                self.result_var.set(f" 검색 결과 없음: {target}\n(해당 날짜 데이터가 없습니다.)")
                return

            self.last_result = result
            self.result_var.set(make_summary_text(result))

        except Exception as e:
            self.last_result = None
            messagebox.showerror("오류", str(e))

    def on_save(self):
        if self.last_result is None or self.last_result.empty:
            messagebox.showwarning("저장 불가", "먼저 검색을 성공해야 저장할 수 있어요.")
            return

        try:
            saved_path = save_result_csv(self.last_result)
            messagebox.showinfo("저장 완료", f"CSV 저장 완료\n{saved_path}")
        except Exception as e:
            messagebox.showerror("저장 오류", str(e))

    def open_year_weather(self):
        try:
            base = Path(__file__).resolve().parent
            candidates = [
                base / "1year weather.py",
                base / "year_weather.py",
                base / "UI" / "1year weather.py",
            ]

            target = None
            for p in candidates:
                if p.exists():
                    target = p
                    break

            if target is None:
                raise FileNotFoundError("1year weather.py 파일을 찾을 수 없습니다.")

            spec = importlib.util.spec_from_file_location("year_weather", target)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            module.WeatherGUI(self.root)

        except Exception as e:
            messagebox.showerror("연간 분석 오류", str(e))

    def show_saved_weather(self):
        export_dir = "exports"
        export_path_abs = os.path.join(BASE_DIR, export_dir)

        if not os.path.isdir(export_path_abs):
            messagebox.showinfo("저장된 날씨", "아직 저장된 파일이 없어요. (exports 폴더가 없습니다)")
            return

        files = sorted(glob.glob(os.path.join(export_path_abs, "*.csv")), reverse=True)
        if not files:
            messagebox.showinfo("저장된 날씨", "exports 폴더에 CSV가 아직 없어요.")
            return

        win = tk.Toplevel(self.root)
        win.title("저장된 날씨 목록")
        win.geometry("1100x650")
        win.minsize(950, 550)

        top = tk.Frame(win)
        top.pack(fill="x", padx=12, pady=(12, 6))

        tk.Label(top, text="저장된 파일 선택 → 오른쪽에서 미리보기", font=("Segoe UI", 11, "bold")).pack(anchor="w")

        selected_var = tk.StringVar(value="선택된 파일: (없음)")
        tk.Label(top, textvariable=selected_var, fg="gray").pack(anchor="w", pady=(4, 0))

        body = tk.Frame(win)
        body.pack(fill="both", expand=True, padx=12, pady=10)

        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)

        left = tk.Frame(body)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        tk.Label(left, text="저장된 CSV 파일", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        listbox = tk.Listbox(left, width=35, height=25)
        listbox.pack(fill="y", expand=True, pady=(6, 0))

        basename_list = [os.path.basename(fp) for fp in files]
        for name in basename_list:
            listbox.insert("end", name)

        right = tk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")

        tk.Label(right, text="미리보기", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        summary_frame = tk.Frame(right, bd=1, relief="solid")
        summary_frame.pack(fill="both", expand=True, pady=(6, 0))

        summary_canvas = tk.Canvas(summary_frame, highlightthickness=0)
        summary_scroll = tk.Scrollbar(summary_frame, orient="vertical", command=summary_canvas.yview)
        summary_canvas.configure(yscrollcommand=summary_scroll.set)

        summary_scroll.pack(side="right", fill="y")
        summary_canvas.pack(side="left", fill="both", expand=True)

        summary_inner = tk.Frame(summary_canvas)
        summary_window = summary_canvas.create_window((0, 0), window=summary_inner, anchor="nw")

        def _sync_summary_scrollregion(event=None):
            summary_canvas.configure(scrollregion=summary_canvas.bbox("all"))

        def _sync_summary_width(event=None):
            summary_canvas.itemconfigure(summary_window, width=summary_canvas.winfo_width())

        summary_inner.bind("<Configure>", _sync_summary_scrollregion)
        summary_canvas.bind("<Configure>", _sync_summary_width)

        table_frame = tk.Frame(right)

        tree = ttk.Treeview(table_frame, show="headings")
        tree.pack(side="left", fill="both", expand=True)

        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)

        y_scroll.pack(side="right", fill="y")
        x_scroll.pack(side="bottom", fill="x")

        def set_tree_from_df(df: pd.DataFrame):
            for col in tree["columns"]:
                tree.heading(col, text="")
                tree.column(col, width=0)
            tree.delete(*tree.get_children())

            max_cols = 15
            cols = list(df.columns)[:max_cols]
            tree["columns"] = cols

            for c in cols:
                tree.heading(c, text=c)
                tree.column(c, width=120, anchor="center", stretch=True)

            for _, row in df.head(50).iterrows():
                values = []
                for c in cols:
                    v = row[c]
                    if pd.isna(v):
                        v = ""
                    values.append(v)
                tree.insert("", "end", values=values)

        def show_summary_2col(df: pd.DataFrame):
            for w in summary_inner.winfo_children():
                w.destroy()

            if df is None or df.empty:
                tk.Label(summary_inner, text="데이터가 비어있어요.", fg="gray").pack(padx=10, pady=10)
                return

            row = df.iloc[0].to_dict()

            items = []
            for k, v in row.items():
                k = str(k).strip()
                if pd.isna(v):
                    v = ""
                items.append((k, str(v)))

            summary_inner.grid_columnconfigure(1, weight=1)
            summary_inner.grid_columnconfigure(3, weight=1)

            pad_y = 6
            pad_x = 10
            r = 0

            for i in range(0, len(items), 2):
                k1, v1 = items[i]
                k2, v2 = ("", "")
                if i + 1 < len(items):
                    k2, v2 = items[i + 1]

                tk.Label(summary_inner, text=k1, anchor="w",
                         font=("Segoe UI", 9, "bold"), fg="#333") \
                    .grid(row=r, column=0, sticky="w", padx=(pad_x, 6), pady=(pad_y, 0))
                tk.Label(summary_inner, text=v1, anchor="w") \
                    .grid(row=r, column=1, sticky="we", padx=(0, 16), pady=(pad_y, 0))

                tk.Label(summary_inner, text=k2, anchor="w",
                         font=("Segoe UI", 9, "bold"), fg="#333") \
                    .grid(row=r, column=2, sticky="w", padx=(pad_x, 6), pady=(pad_y, 0))
                tk.Label(summary_inner, text=v2, anchor="w") \
                    .grid(row=r, column=3, sticky="we", padx=(0, pad_x), pady=(pad_y, 0))

                r += 1

        def open_selected():
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning("선택 없음", "왼쪽에서 파일을 하나 선택.")
                return

            fp = files[sel[0]]
            selected_var.set(f"선택된 파일: {fp}")

            try:
                df = pd.read_csv(fp, encoding="utf-8-sig")
            except UnicodeDecodeError:
                df = pd.read_csv(fp, encoding="cp949")
            df.columns = df.columns.astype(str).str.strip()

            if len(df) <= 1:
                table_frame.pack_forget()
                summary_frame.pack(fill="both", expand=True, pady=(6, 0))
                show_summary_2col(df)
            else:
                summary_frame.pack_forget()
                table_frame.pack(fill="both", expand=True, pady=(6, 0))
                set_tree_from_df(df)

        def open_exports_folder():
            try:
                if os.name == "nt":
                    os.startfile(export_path_abs)
                elif sys.platform == "darwin":
                    os.system(f'open "{export_path_abs}"')
                else:
                    os.system(f'xdg-open "{export_path_abs}"')
            except Exception as e:
                messagebox.showerror("폴더 열기 실패", str(e))

        bottom = tk.Frame(win)
        bottom.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(bottom, text="exports 폴더 열기", command=open_exports_folder).pack(side="right")

        def on_list_select(event=None):
            if listbox.curselection():
                open_selected()

        listbox.bind("<<ListboxSelect>>", on_list_select)
        listbox.bind("<Double-Button-1>", on_list_select)

        listbox.selection_set(0)
        open_selected()

    # ---- 상세 ----
    def open_detail_window(self, target_date: date, row: pd.Series):
        win = tk.Toplevel(self.root)
        win.title(f"상세 데이터: {target_date}")
        win.geometry("760x620")
        win.minsize(650, 500)

        txt = tk.Text(win, wrap="word")
        txt.pack(fill="both", expand=True, padx=10, pady=10)

        txt.insert("end", f"[날짜] {target_date}\n\n")
        for col in row.index:
            val = row[col]
            if pd.isna(val):
                continue
            txt.insert("end", f"- {col}: {val}\n")

        txt.config(state="disabled")

    # ---- 달력 ----
    def open_calendar(self):
        self.cal_win = tk.Toplevel(self.root)
        self.cal_win.title("달력 (요약 보기)")

        # 창 크게 + 최소 크기
        self.cal_win.geometry("1700x1050")
        self.cal_win.minsize(1500, 950)
        self.cal_win.resizable(True, True)

        # 폰트 (잘림 방지용)
        self.EMOJI_FONT = ("Segoe UI Emoji", 22)
        self.SUMMARY_FONT = ("Segoe UI", 10)
        self.DAY_FONT = ("Segoe UI", 11, "bold")

        # --- 상단 바(이전/제목/다음) ---
        top = tk.Frame(self.cal_win)
        top.pack(fill="x", padx=8, pady=6)

        tk.Button(top, text="◀", width=4, command=self.cal_prev_month).pack(side="left")

        self.cal_title_var = tk.StringVar()
        tk.Label(top, textvariable=self.cal_title_var, font=("Segoe UI", 18, "bold")).pack(side="left", expand=True)

        tk.Button(top, text="▶", width=4, command=self.cal_next_month).pack(side="right")

        # --- 달력 본문 프레임 ---
        self.cal_frame = tk.Frame(self.cal_win)
        self.cal_frame.pack(fill="both", expand=True, padx=8, pady=6)

        self.render_calendar()

    def cal_prev_month(self):
        self.cal_month -= 1
        if self.cal_month == 0:
            self.cal_month = 12
            self.cal_year -= 1
        self.render_calendar()

    def cal_next_month(self):
        self.cal_month += 1
        if self.cal_month == 13:
            self.cal_month = 1
            self.cal_year += 1
        self.render_calendar()

    def render_calendar(self):
        for w in self.cal_frame.winfo_children():
            w.destroy()

        y, m = self.cal_year, self.cal_month
        self.cal_title_var.set(f"{y}.{m:02d}")

        #  계절 테마 적용
        season = season_from_month(m)
        theme = SEASON_THEME[season]

        # 요일 헤더(계절 색)
        days = ["일", "월", "화", "수", "목", "금", "토"]
        for c, dname in enumerate(days):
            tk.Label(
                self.cal_frame,
                text=dname,
                font=("Segoe UI", 12, "bold"),
                bg=theme["header_bg"],
                fg=theme["accent"]
            ).grid(row=0, column=c, sticky="nsew", pady=8)

        # 그리드 비율(열/행 모두 균등)
        for c in range(7):
            self.cal_frame.grid_columnconfigure(c, weight=1, uniform="col")
        for r in range(0, 7):
            self.cal_frame.grid_rowconfigure(r, weight=1, uniform="row")

        first_wday, last_day = calendar.monthrange(y, m)  # 월0..일6
        start_col = (first_wday + 1) % 7  # 일요일=0

        day_num = 1
        row_idx = 1
        col_idx = start_col

        while day_num <= last_day:
            target = date(y, m, day_num)
            has_data = target in self.date_map

            #  데이터 있으면 bg, 없으면 empty_bg
            cell_bg = theme["bg"] if has_data else theme["empty_bg"]

            # 셀(칸) 테두리 + 계절 배경색
            cell = tk.Frame(self.cal_frame, relief="ridge", bd=2, bg=cell_bg)
            cell.grid(row=row_idx, column=col_idx, sticky="nsew", padx=4, pady=4)

            # 내부 레이아웃: 날짜(고정) / 이모지(중간) / 요약(아래)
            cell.grid_rowconfigure(0, weight=0)
            cell.grid_rowconfigure(1, weight=1)
            cell.grid_rowconfigure(2, weight=1)
            cell.grid_columnconfigure(0, weight=1)

            # 날짜 라벨
            day_lbl = tk.Label(
                cell,
                text=str(day_num),
                anchor="nw",
                font=self.DAY_FONT,
                bg=cell_bg,
                fg=theme["accent"]
            )
            day_lbl.grid(row=0, column=0, sticky="nw", padx=8, pady=(8, 0))

            if has_data:
                row = self.date_map[target]
                emoji = get_emoji_for_day(row)
                summary = build_day_summary(row)

                emoji_lbl = tk.Label(cell, text=emoji, font=self.EMOJI_FONT, bg=cell_bg)
                emoji_lbl.grid(row=1, column=0, sticky="n", pady=(8, 2))

                summary_lbl = tk.Label(
                    cell,
                    text=summary,
                    font=self.SUMMARY_FONT,
                    justify="center",
                    anchor="n",
                    wraplength=170,
                    bg=cell_bg
                )
                summary_lbl.grid(row=2, column=0, sticky="n", padx=8, pady=(2, 8))

                def make_handler(t=target, rr=row):
                    return lambda e: self.open_detail_window(t, rr)

                for widget in (cell, day_lbl, emoji_lbl, summary_lbl):
                    widget.bind("<Button-1>", make_handler())
            else:
                no_lbl = tk.Label(cell, text="(데이터 없음)", font=("Segoe UI", 10), fg="gray", bg=cell_bg)
                no_lbl.grid(row=1, column=0, sticky="n", pady=25)

            day_num += 1
            col_idx += 1
            if col_idx >= 7:
                col_idx = 0
                row_idx += 1


if __name__ == "__main__":
    df = load_weather_df(CSV_FILE)

    root = tk.Tk()
    app = WeatherApp(root, df)
    root.mainloop()

    #완성