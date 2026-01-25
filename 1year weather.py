import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def strip_unit(name: str) -> str:
    s = str(name)
    if "(" in s and ")" in s:
        s = s.split("(")[0].strip()
    return s


def wrap_label(text: str, width: int = 6) -> str:
    s = str(text)
    if len(s) <= width:
        return s
    return "\n".join(s[i:i + width] for i in range(0, len(s), width))


class WeatherGUI(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)

        self.title("기상 데이터 분석 및 수정 도구 (통합본)")
        self.geometry("1400x900")

        self.file_path = None
        self.df_raw = None
        self.df_current = None
        self.df_base = None

        self.canvas = None

        plt.rcParams["font.family"] = ["Malgun Gothic", "NanumGothic", "AppleGothic", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False

        # --- 메뉴바 설정 ---
        self.setup_menu()

        # --- 상단 UI 및 컨트롤 패널 ---
        top = ttk.Frame(self, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)

        self.path_var = tk.StringVar(value="파일을 선택하세요.")
        ttk.Label(top, textvariable=self.path_var).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Button(top, text="CSV 선택", command=self.pick_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="타입변환+정렬", command=self.transform_and_sort).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="계절 2x2 히트맵", command=self.plot_season_heatmaps).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="현재 데이터 저장(CSV)", command=self.save_current_csv).pack(side=tk.LEFT, padx=4)

        opt = ttk.Frame(self, padding=(10, 0, 10, 10))
        opt.pack(side=tk.TOP, fill=tk.X)

        self.encoding_var = tk.StringVar(value="cp949")
        ttk.Label(opt, text="인코딩").pack(side=tk.LEFT)
        ttk.Entry(opt, textvariable=self.encoding_var, width=10).pack(side=tk.LEFT, padx=5)

        # self.method_var = tk.StringVar(value="pearson")

        ttk.Label(opt, text="상관방법").pack(side=tk.LEFT)
        ttk.Label(opt, text="pearson").pack(side=tk.LEFT, padx=5)

        self.method_var = tk.StringVar(value="pearson")

        # ttk.Label(opt, text="상관방법").pack(side=tk.LEFT)
        # ttk.Combobox(opt, textvariable=self.method_var, values=["pearson"], width=10, state="readonly").pack(
        #     side=tk.LEFT, padx=5
        # )

        self.k_var = tk.IntVar(value=8)
        ttk.Label(opt, text="변수개수").pack(side=tk.LEFT)
        ttk.Spinbox(opt, from_=2, to=20, textvariable=self.k_var, width=6).pack(side=tk.LEFT, padx=5)

        # 히트맵 옵션(그대로 유지)
        self.nonnull_ratio_var = tk.DoubleVar(value=0.7)
        self.min_rows_season_var = tk.IntVar(value=30)
        self.annot_thr_var = tk.DoubleVar(value=0.5)

        # --- 필터 패널 ---
        flt = ttk.LabelFrame(self, text="조건 판단 및 시각화", padding=10)
        flt.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 10))

        self.filter_col_var = tk.StringVar(value="")
        self.filter_col_cb = ttk.Combobox(flt, textvariable=self.filter_col_var, width=24, state="readonly")
        self.filter_col_cb.pack(side=tk.LEFT, padx=5)

        self.filter_op_var = tk.StringVar(value="==")
        ttk.Combobox(
            flt,
            textvariable=self.filter_op_var,
            values=[">", ">=", "<", "<=", "==", "!=", "contains", "in"],
            width=12,
            state="readonly",
        ).pack(side=tk.LEFT, padx=5)

        self.filter_val_var = tk.StringVar(value="")
        ttk.Entry(flt, textvariable=self.filter_val_var, width=20).pack(side=tk.LEFT, padx=5)

        ttk.Button(flt, text="판단 열 추가", command=self.apply_filter).pack(side=tk.LEFT, padx=4)
        ttk.Button(flt, text="자세히 보기", command=self.show_detailed_view).pack(side=tk.LEFT, padx=4)
        ttk.Button(flt, text="필터 해제/복구", command=self.reset_filter).pack(side=tk.LEFT, padx=4)

        # --- 메인 컨테이너 (왼쪽 표/로그 + 오른쪽 그래프(숨김)) ---
        self.main_container = ttk.Frame(self)
        self.main_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.main_container.columnconfigure(0, weight=1)
        self.main_container.columnconfigure(1, weight=0)
        self.main_container.rowconfigure(0, weight=1)

        self.left_area = ttk.Frame(self.main_container)
        self.left_area.grid(row=0, column=0, sticky="nsew")

        self.right_area = ttk.Frame(self.main_container)
        self.plot_frame = self.right_area

        self.left_paned = ttk.PanedWindow(self.left_area, orient=tk.VERTICAL)
        self.left_paned.pack(fill=tk.BOTH, expand=True)

        # --- 이 부분을 집중적으로 수정합니다 ---
        table_frame = ttk.Frame(self.left_paned, padding=5)
        self.left_paned.add(table_frame, weight=3)

        # 1. Treeview 생성
        self.table = ttk.Treeview(table_frame, show="headings")

        # 2. 세로 스크롤바 생성 및 연결
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=yscroll.set)

        # 3. 가로 스크롤바 생성 및 연결 (추가)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(xscrollcommand=xscroll.set)

        # 4. Grid 레이아웃으로 배치 (스크롤바들을 표의 우측과 하단에 고정)
        self.table.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        # 표가 있는 0번 행과 0번 열이 가득 차도록 설정
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        # ---------------------------------------

        log_frame = ttk.Frame(self.left_paned, padding=5)
        self.left_paned.add(log_frame, weight=1)

        self.log_text = tk.Text(log_frame, height=8, wrap="word", state="disabled")
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.log("프로그램 시작")

    # -------------------- 메뉴 구성 (수정됨) --------------------
    def setup_menu(self):
        menubar = tk.Menu(self)

        # 1. 데이터 수정 메뉴
        edit_data_menu = tk.Menu(menubar, tearoff=0)
        edit_data_menu.add_command(label="열 삭제", command=self.popup_delete_column)
        menubar.add_cascade(label="데이터 수정", menu=edit_data_menu)

        # 2. 데이터 분석 메뉴
        analysis_menu = tk.Menu(menubar, tearoff=0)
        analysis_menu.add_command(label="전체 요약 통계량", command=self.show_summary_stats)
        analysis_menu.add_command(label="1~12월 주요항목 평균치", command=self.show_monthly_summary)
        menubar.add_cascade(label="데이터 분석", menu=analysis_menu)

        # 3. 데이터 조회 메뉴
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="강수 발생일 기록", command=self.process_rainfall_frequency)
        view_menu.add_command(label="기온 탐색 결과", command=self.explore_avg_temp)
        menubar.add_cascade(label="데이터 조회", menu=view_menu)

        # 4. 이상치 제거 메뉴 (최대 풍속으로 변경) ★
        outlier_menu = tk.Menu(menubar, tearoff=0)
        outlier_menu.add_command(label="최대 풍속(m/s)", command=self.remove_wind_speed_outliers)
        menubar.add_cascade(label="이상치 제거", menu=outlier_menu)

        self.config(menu=menubar)

    # -------------------- 이상치 제거 기능 (최대 풍속 기준) ★ --------------------
    def remove_wind_speed_outliers(self):
        """IQR 방식을 이용해 최대 풍속(m/s)의 이상치를 제거합니다."""
        if self.df_current is None:
            messagebox.showwarning("알림", "데이터가 로드되지 않았습니다.")
            return

        # 컬럼명 설정 (파일의 실제 컬럼명과 일치해야 합니다)
        col = "최대 풍속(m/s)"
        if col not in self.df_current.columns:
            messagebox.showerror("오류", f"'{col}' 컬럼을 찾을 수 없습니다.\n파일에 해당 컬럼이 있는지 확인하세요.")
            return

        try:
            df = self.df_current.copy()
            df[col] = pd.to_numeric(df[col], errors='coerce')

            valid_data = df[col].dropna()
            if valid_data.empty:
                messagebox.showinfo("알림", "분석할 유효한 데이터가 없습니다.")
                return

            # IQR 계산
            Q1 = valid_data.quantile(0.25)
            Q3 = valid_data.quantile(0.75)
            IQR = Q3 - Q1

            # 이상치 경계 설정 (1.5배)
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR

            # 물리적 한계 보정 (풍속은 0 미만일 수 없음)
            lower_bound = max(lower_bound, 0)

            # 필터링 수행
            before_cnt = len(df)
            filtered_df = df[(df[col] >= lower_bound) & (df[col] <= upper_bound)]
            after_cnt = len(filtered_df)

            removed_cnt = before_cnt - after_cnt

            if removed_cnt == 0:
                messagebox.showinfo("결과", f"통계적 기준({upper_bound:.2f} m/s 초과)을 벗어나는 이상치가 발견되지 않았습니다.")
                return

            if messagebox.askyesno("이상치 제거 확인",
                                   f"계산된 정상 범위: {lower_bound:.2f} ~ {upper_bound:.2f} m/s\n"
                                   f"제거될 데이터 수: {removed_cnt}개\n\n"
                                   f"이 작업을 수행하시겠습니까?"):
                self.df_current = filtered_df
                self.df_base = filtered_df.copy()

                self.render_table(self.df_current)
                self.log(f"이상치 제거 완료: {col} ({removed_cnt}행 삭제)")
                messagebox.showinfo("완료", f"{removed_cnt}개의 이상치가 제거되었습니다.")

        except Exception as e:
            messagebox.showerror("오류", f"이상치 제거 중 오류 발생: {e}")
            self.log(f"이상치 제거 실패: {e}")

    # -------------------- 공통 --------------------
    def log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{now_str()}] {msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def pick_file(self):
        path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if not path:
            return
        self.file_path = path
        self.path_var.set(path)
        self.load_csv()

    def load_csv(self):
        try:
            enc = self.encoding_var.get().strip() or "cp949"
            df = pd.read_csv(self.file_path, encoding=enc)

            self.df_raw = df.copy()
            self.df_current = df.copy()
            self.df_base = df.copy()

            self.refresh_filter_columns()
            self.render_table(self.df_current)  # .head(250)을 삭제하여 전체 표시

            self.clear_plot()
            self.hide_right_plot()

            self.log(f"CSV 로드: {len(df)}행")
        except Exception as e:
            messagebox.showerror("오류", str(e))
            self.log(f"로드 실패: {e}")

    def refresh_filter_columns(self):
        if self.df_current is None:
            self.filter_col_cb["values"] = []
            self.filter_col_var.set("")
            return
        cols = list(self.df_current.columns)
        self.filter_col_cb["values"] = cols
        if cols:
            self.filter_col_var.set(cols[0])

    def _display_name_fix(self, col_name: str) -> str:
        s = str(col_name)
        if s == "평균 상대습도(%)":
            return "평균상대습도(%)"
        return s

    def render_table(self, df_show: pd.DataFrame):
        self.table.delete(*self.table.get_children())
        cols = list(df_show.columns)
        self.table["columns"] = cols

        for col in cols:
            header = self._display_name_fix(col)
            self.table.heading(col, text=header)

            width = 120
            if col == "평균 상대습도(%)":
                width = 170

                # stretch=False를 추가해야 창보다 열이 많을 때 가로 스크롤이 생깁니다.
            self.table.column(col, width=width, anchor="center", stretch=False)

        for _, row in df_show.iterrows():
            self.table.insert("", tk.END, values=[row[c] for c in cols])

    # -------------------- 데이터 수정 기능 --------------------
    def popup_delete_column(self):
        """삭제할 열을 선택하는 팝업창을 띄웁니다."""
        if self.df_current is None:
            messagebox.showwarning("알림", "데이터가 로드되지 않았습니다.")
            return

        # 새 창 띄우기
        pop = tk.Toplevel(self)
        pop.title("삭제할 열 선택")
        pop.geometry("300x450")
        pop.grab_set()  # 팝업창이 떠 있는 동안 메인 창 조작 방지

        ttk.Label(pop, text="삭제할 컬럼을 체크하세요:", font=("맑은 고딕", 10, "bold")).pack(pady=10)

        # 스크롤 가능한 프레임 생성 (컬럼이 많을 경우 대비)
        container = ttk.Frame(pop)
        container.pack(fill="both", expand=True, padx=20)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 체크박스 변수 저장용 딕셔너리
        self.check_vars = {}
        for col in self.df_current.columns:
            var = tk.BooleanVar()
            self.check_vars[col] = var
            ttk.Checkbutton(scrollable_frame, text=col, variable=var).pack(anchor="w", pady=2)

        # 하단 버튼
        btn_frame = ttk.Frame(pop, padding=10)
        btn_frame.pack(fill="x")

        def execute_delete():
            # 체크된 열 이름만 추출
            to_delete = [col for col, var in self.check_vars.items() if var.get()]

            if not to_delete:
                messagebox.showwarning("알림", "삭제할 열을 선택하지 않았습니다.")
                return

            confirm = messagebox.askyesno("확인", f"선택한 {len(to_delete)}개의 열을 삭제하시겠습니까?\n이 작업은 원본 메모리를 수정합니다.")
            if confirm:
                try:
                    # 진짜 수정 발생: 원본(df_current)과 기준(df_base)에서 열 삭제
                    self.df_current.drop(columns=to_delete, inplace=True)
                    self.df_base.drop(columns=to_delete, inplace=True)

                    # UI 갱신
                    self.refresh_filter_columns()
                    self.render_table(self.df_current)
                    self.log(f"열 삭제 완료: {', '.join(to_delete)}")

                    messagebox.showinfo("완료", "선택한 열이 삭제되었습니다.")
                    pop.destroy()
                except Exception as e:
                    messagebox.showerror("오류", f"삭제 중 오류 발생: {e}")

        ttk.Button(btn_frame, text="삭제 실행", command=execute_delete).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="취소", command=pop.destroy).pack(side="right")


    # -------------------- 분석 --------------------
    def show_summary_stats(self):
        if self.df_current is None:
            return

        # include="all"을 제거하여 숫자형 데이터만 요약합니다.
        # 이렇게 하면 오른쪽 사진처럼 count, mean, std, min... 행만 깔끔하게 나옵니다.
        desc = self.df_current.describe().reset_index()

        # 팝업창에 표시
        self.display_df_popup(desc.round(2), "전체 요약 통계량")

    def show_monthly_summary(self):
        """
         '월' 글자 붙는 문제 제거 (사진 요구사항)
        """
        if self.df_current is None:
            return
        try:
            df = self.df_current.copy()
            if "일시" not in df.columns:
                messagebox.showerror("오류", "일시 컬럼이 없습니다.")
                return

            df["일시"] = pd.to_datetime(df["일시"], errors="coerce")
            df["월"] = df["일시"].dt.month

            target = ["평균기온(°C)", "평균 상대습도(%)", "일강수량(mm)"]
            avail = [c for c in target if c in df.columns]
            if not avail:
                messagebox.showwarning("알림", "요약할 대상 컬럼이 없습니다.")
                return

            res = df.groupby("월")[avail].mean().reset_index().round(2)


            # res["월"] = res["월"].astype(str) + "월"  # <- 제거

            # 표시용 이름만 보정(데이터 컬럼은 유지)
            res = res.rename(columns={"평균 상대습도(%)": "평균상대습도(%)"})
            self.display_df_popup(res, "1~12월 주요항목 평균치")
        except Exception as e:
            messagebox.showerror("오류", str(e))

    def process_rainfall_frequency(self):
        if self.df_current is None:
            return
        try:
            df = self.df_current.copy()
            rain_col = "일강수량(mm)"
            if rain_col not in df.columns:
                messagebox.showwarning("알림", f"{rain_col} 컬럼이 없습니다.")
                return

            df[rain_col] = pd.to_numeric(df[rain_col], errors="coerce")
            res = df[df[rain_col] > 0].copy()
            if "일시" in res.columns:
                res["일시"] = pd.to_datetime(res["일시"], errors="coerce").dt.date
            self.display_df_popup(res[["일시", rain_col]].dropna(), "강수 발생일 기록")
        except Exception as e:
            messagebox.showerror("오류", str(e))

    def explore_avg_temp(self):
        if self.df_current is None:
            return
        try:
            df = self.df_current.copy()
            if "일시" not in df.columns or "평균기온(°C)" not in df.columns:
                messagebox.showwarning("알림", "일시 / 평균기온(°C) 컬럼이 필요합니다.")
                return

            df["dt"] = pd.to_datetime(df["일시"], errors="coerce")
            df = df.dropna(subset=["dt"])
            # 월(month) 정보는 더 이상 분류 기준에 필요 없으므로 생략하거나 유지해도 무방합니다.
            df["평균기온(°C)"] = pd.to_numeric(df["평균기온(°C)"], errors="coerce")

            def get_stat(row):
                t = row["평균기온(°C)"]
                if pd.isna(t):
                    return None

                # 요청하신 새로운 기온 기준 적용
                if t <= 0:
                    return "매우 추움"
                elif t <= 10:
                    return "추움"
                elif t <= 20:
                    return "보통"
                elif t <= 30:
                    return "더움"
                else:
                    return "매우 더움"

            df["상태"] = df.apply(get_stat, axis=1)

            # 상태가 분류된 데이터만 추출
            res = df[df["상태"].notnull()].copy()
            res["날짜"] = res["dt"].dt.date

            # 결과 표시 (날짜, 기온, 상태 순)
            self.display_df_popup(res[["날짜", "평균기온(°C)", "상태"]], "기온 탐색 결과")

            self.log(f"기온 탐색 완료: {len(res)}행 분류됨")

        except Exception as e:
            messagebox.showerror("오류", f"기온 탐색 중 오류 발생: {e}")

    # -------------------- 판단/상세보기/그래프 (사진 핵심) --------------------
    def apply_filter(self):
        if self.df_base is None:
            messagebox.showwarning("알림", "먼저 CSV를 선택하세요.")
            return

        col = self.filter_col_var.get().strip()
        op = self.filter_op_var.get().strip()
        val = self.filter_val_var.get().strip()

        if not col:
            messagebox.showwarning("알림", "컬럼을 선택하세요.")
            return
        if val == "" and op not in ["contains", "in"]:
            messagebox.showwarning("알림", "값을 입력하세요.")
            return

        try:
            df = self.df_base.copy()
            res_name = f"판단({op})"
            s = df[col]

            if op == "contains":
                mask = s.astype(str).str.contains(val, na=False)

            elif op == "in":
                items = [x.strip() for x in val.split(",") if x.strip() != ""]
                if not items:
                    raise ValueError("in 연산은 콤마로 구분된 값을 입력하세요. 예: 133,108")

                nums = []
                all_num = True
                for it in items:
                    n = pd.to_numeric(it, errors="coerce")
                    if pd.isna(n):
                        all_num = False
                        break
                    nums.append(n)

                if all_num:
                    s_num = pd.to_numeric(s, errors="coerce")
                    mask = s_num.isin(nums)
                else:
                    mask = s.astype(str).isin(items)

            else:
                s_num = pd.to_numeric(s, errors="coerce")
                v_num = pd.to_numeric(val, errors="coerce")
                if pd.isna(v_num) and op in [">", ">=", "<", "<="]:
                    raise ValueError(">,>=,<,<= 는 숫자 값이 필요합니다.")

                if op == ">":
                    mask = s_num > v_num
                elif op == ">=":
                    mask = s_num >= v_num
                elif op == "<":
                    mask = s_num < v_num
                elif op == "<=":
                    mask = s_num <= v_num
                elif op == "==":
                    if not pd.isna(v_num):
                        mask = (s_num == v_num)
                    else:
                        mask = (s.astype(str) == val)
                elif op == "!=":
                    if not pd.isna(v_num):
                        mask = (s_num != v_num)
                    else:
                        mask = (s.astype(str) != val)
                else:
                    raise ValueError(f"지원하지 않는 연산자: {op}")

            df[res_name] = np.where(mask, 0, 1)  #  사진처럼 0/1

            self.df_current = df
            self.render_table(self.df_current)  # .head(250)을 삭제하여 전체 표시
            self.hide_right_plot()
            self.clear_plot()

            self.log(f"판단 열 추가: {col} {op} {val} -> {res_name} 생성")
        except Exception as e:
            messagebox.showerror("오류", f"판단 조건을 확인하세요.\n\n{e}")
            self.log(f"판단 실패: {e}")

    def show_detailed_view(self):
        if self.df_current is None:
            return

        res_cols = [c for c in self.df_current.columns if "판단(" in c]
        if not res_cols:
            messagebox.showwarning("알림", "먼저 '판단 열 추가'를 완료하세요.")
            return

        target_res_col = res_cols[-1]
        target_val_col = self.filter_col_var.get().strip()

        try:
            df = self.df_current.copy()
            sub = df[pd.to_numeric(df[target_res_col], errors="coerce") == 0].copy()
            if sub.empty:
                messagebox.showinfo("알림", "조건을 만족하는 데이터가 없습니다.")
                return

            self.show_right_plot()

            display_cols = []
            if "일시" in sub.columns:
                display_cols.append("일시")
            if target_val_col in sub.columns:
                display_cols.append(target_val_col)
            display_cols.append(target_res_col)

            self.render_table(sub[display_cols])
            self.plot_line_chart(sub, target_val_col)

            self.log(f"상세보기: {target_res_col} 만족(0) 데이터 {len(sub)}행 표시")
        except Exception as e:
            self.log(f"상세보기 오류: {e}")

    def show_right_plot(self):
        self.main_container.columnconfigure(1, weight=3)
        self.main_container.columnconfigure(0, weight=1)
        self.right_area.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.update_idletasks()

    def hide_right_plot(self):
        self.right_area.grid_forget()
        self.main_container.columnconfigure(1, weight=0)

    def plot_line_chart(self, df: pd.DataFrame, val_col: str):
        self.clear_plot()
        try:
            plot_df = df.copy()
            if "일시" in plot_df.columns:
                plot_df["일시"] = pd.to_datetime(plot_df["일시"], errors="coerce")
                plot_df = plot_df.dropna(subset=["일시"]).sort_values("일시")
                x = plot_df["일시"]
            else:
                x = plot_df.index

            y = pd.to_numeric(plot_df[val_col], errors="coerce")
            plot_df = plot_df.assign(_y=y).dropna(subset=["_y"])

            fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
            ax.plot(
                plot_df["일시"] if "일시" in plot_df.columns else plot_df.index,
                plot_df["_y"],
                marker="o",
            )
            ax.set_title(f"{val_col} (조건 만족 데이터)")
            ax.set_xlabel("일시" if "일시" in plot_df.columns else "index")
            ax.set_ylabel(val_col)

            self.canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            self.log(f"그래프 생성 중 오류: {e}")

    def clear_plot(self):
        if self.canvas is not None:
            self.canvas.get_tk_widget().destroy()
            self.canvas = None

    def reset_filter(self):
        if self.df_base is None:
            return
        self.df_current = self.df_base.copy()
        self.render_table(self.df_current.head(250))
        self.clear_plot()
        self.hide_right_plot()
        self.log("필터 해제/복구 완료")

    # -------------------- 전처리/저장 --------------------
    def transform_and_sort(self):
        if self.df_current is None:
            messagebox.showwarning("알림", "먼저 CSV를 선택하세요.")
            return

        try:
            df = self.df_current.copy()

            if "일시" in df.columns:
                df["일시"] = pd.to_datetime(df["일시"], errors="coerce")
            if "지점" in df.columns:
                df["지점"] = pd.to_numeric(df["지점"], errors="coerce").astype("Int64")
            if "지점명" in df.columns:
                df["지점명"] = df["지점명"].astype("category")

            fixed = {"지점", "지점명", "일시"}
            for c in df.columns:
                if c not in fixed:
                    df[c] = pd.to_numeric(df[c], errors="coerce")

            sort_cols = [c for c in ["지점", "일시"] if c in df.columns]
            if sort_cols:
                df = df.sort_values(sort_cols).reset_index(drop=True)

            self.df_current = df
            self.df_base = df.copy()

            self.refresh_filter_columns()
            self.render_table(self.df_current.head(250))

            self.clear_plot()
            self.hide_right_plot()

            self.log("전처리(타입변환+정렬) 완료")
            messagebox.showinfo("완료", "타입 변환 및 정렬 완료(미리보기 250행 표시).")
        except Exception as e:
            messagebox.showerror("전처리 실패", f"타입 변환/정렬 중 오류:\n{e}")
            self.log(f"전처리 실패: {e}")

    def save_current_csv(self):
        if self.df_current is None:
            messagebox.showwarning("알림", "저장할 데이터가 없습니다.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not path:
            return
        try:
            self.df_current.to_csv(path, index=False, encoding="utf-8-sig")
            self.log(f"현재 데이터 저장: {path} (rows={len(self.df_current)})")
            messagebox.showinfo("완료", f"저장 완료:\n{path}")
        except Exception as e:
            messagebox.showerror("저장 실패", f"CSV 저장 중 오류:\n{e}")
            self.log(f"저장 실패: {e}")

    def display_df_popup(self, df: pd.DataFrame, title: str):
        top = tk.Toplevel(self)
        top.title(title)
        top.geometry("1000x550")  # 가로로 좀 더 길게 설정

        # 1. 트리뷰와 스크롤바를 배치할 프레임 생성
        frame = ttk.Frame(top)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        # 2. Treeview 설정 (columns는 데이터프레임의 모든 열 이름)
        tree = ttk.Treeview(frame, show="headings", columns=list(df.columns))

        # 3. 가로 스크롤바 생성 ★
        h_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(xscrollcommand=h_scroll.set)

        # 4. 세로 스크롤바 생성
        v_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=v_scroll.set)

        # 5. Grid 레이아웃으로 배치 (스크롤바 위치를 잡기 위해 grid 권장)
        tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        # 창 크기 조절 시 표가 같이 늘어나도록 설정
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # 6. 컬럼 헤더 설정 및 가로 스크롤 활성화 (stretch=False가 핵심)
        for c in df.columns:
            header = self._display_name_fix(c)
            tree.heading(c, text=header)

            # 기본 너비 설정
            w = 120
            if c in ["평균 상대습도(%)", "평균상대습도(%)"]:
                w = 170

            # stretch=False로 설정해야 각 열이 고유 너비를 유지하여 가로 스크롤이 생깁니다.
            tree.column(c, anchor="center", width=w, stretch=False)

        # 7. 데이터 삽입
        for _, r in df.iterrows():
            # NaN 값은 빈 문자열로 처리하여 가독성 향상
            values = [r[c] if not pd.isna(r[c]) else "" for c in df.columns]
            tree.insert("", "end", values=values)
    # -------------------- 히트맵 --------------------
    def plot_season_heatmaps(self):
        if self.df_current is None:
            messagebox.showwarning("알림", "먼저 CSV를 선택하세요.")
            return

        if "일시" not in self.df_current.columns:
            messagebox.showerror("오류", "‘일시’ 컬럼이 없어 히트맵을 생성할 수 없습니다.")
            return

        try:
            df = self.df_current.copy()
            df["월"] = pd.to_datetime(df["일시"], errors="coerce").dt.month

            def get_season(m):
                if m in (3, 4, 5): return "봄"
                if m in (6, 7, 8): return "여름"
                if m in (9, 10, 11): return "가을"
                return "겨울"

            df["계절"] = df["월"].apply(get_season)

            num_df = df.select_dtypes(include=[np.number]).copy()
            num_df = num_df.drop(columns=["월", "지점"], errors="ignore")

            nonnull_ratio = float(self.nonnull_ratio_var.get())
            k = int(self.k_var.get())
            method = (self.method_var.get().strip() or "pearson")
            min_rows = int(self.min_rows_season_var.get())
            annot_thr = float(self.annot_thr_var.get())

            valid_cols = [
                c for c in num_df.columns
                if num_df[c].notna().sum() >= int(len(num_df) * nonnull_ratio)
            ]
            if len(valid_cols) < 2:
                raise ValueError("유효한 숫자 컬럼이 너무 부족합니다. (유효비율을 낮추거나 k를 줄이기)")

            base_corr = num_df[valid_cols].corr(method=method)
            abs_base = base_corr.abs().where(~np.eye(len(base_corr), dtype=bool), np.nan)
            mean_abs = abs_base.mean(axis=1).sort_values(ascending=False)
            selected_cols = mean_abs.head(min(k, len(mean_abs))).index.tolist()
            selected_cols = [c for c in selected_cols if c not in ["월", "지점"]]

            pretty_labels = [strip_unit(c) for c in selected_cols]

            plot_window = tk.Toplevel(self)
            plot_window.title("계절별 상관 히트맵 상세 분석")
            plot_window.geometry("1100x900")
            plot_window.minsize(900, 700)

            fig, axes = plt.subplots(2, 2, figsize=(12, 10))
            fig.suptitle(
                f"계절별 상관 히트맵 (method={method}, k={len(selected_cols)})",
                fontsize=16,
                fontweight="bold"
            )

            fig.subplots_adjust(left=0.08, right=0.90, top=0.92, bottom=0.10, wspace=0.35, hspace=0.25)

            seasons_pos = {(0, 0): "봄", (0, 1): "여름", (1, 0): "가을", (1, 1): "겨울"}
            last_im = None

            for (r, c), s_name in seasons_pos.items():
                ax = axes[r][c]
                s_data = num_df[df["계절"] == s_name][selected_cols]

                if len(s_data) < min_rows:
                    ax.text(
                        0.5, 0.5,
                        f"{s_name}\n(데이터 부족: n={len(s_data)})",
                        ha="center", va="center", fontsize=12
                    )
                    ax.set_axis_off()
                    continue

                corr_mat = s_data.corr(method=method)
                last_im = ax.imshow(corr_mat.values, vmin=-1, vmax=1, cmap="coolwarm")

                ax.set_title(f"{s_name} (데이터 수: {len(s_data)})", fontsize=12, fontweight="bold")
                ax.set_aspect("auto")
                ax.set_anchor("C")
                ax.margins(0)

                ax.set_xticks(range(len(selected_cols)))
                ax.set_yticks(range(len(selected_cols)))
                ax.set_xticklabels(pretty_labels, rotation=35, ha="right", fontsize=9)
                ax.set_yticklabels(pretty_labels, fontsize=9)

                for i in range(len(selected_cols)):
                    for j in range(len(selected_cols)):
                        val = corr_mat.iloc[i, j]
                        if np.isnan(val):
                            continue
                        if i == j or abs(val) >= annot_thr:
                            ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=8)

            if last_im is not None:
                fig.colorbar(last_im, ax=axes, shrink=0.75)

            canvas = FigureCanvasTkAgg(fig, master=plot_window)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            self.log("히트맵 생성 완료: 별도 창에서 확인 가능")

        except Exception as e:
            messagebox.showerror("히트맵 오류", f"처리 중 오류 발생:\n{e}")
            self.log(f"히트맵 오류: {e}")


#  단독 실행용(필요하면)
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # 뒤에 빈 창 안 보이게
    WeatherGUI(root)
    root.mainloop()
#완성