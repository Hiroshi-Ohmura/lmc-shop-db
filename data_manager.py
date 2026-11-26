import streamlit as st
import pandas as pd
import gspread
import os
import glob
from datetime import datetime
import time
from email.message import EmailMessage
import smtplib
import re

try:
    SPREADSHEET_KEY = st.secrets["gsheets"]["spreadsheet_key"]
except (KeyError, FileNotFoundError):
    st.error("設定エラー: secrets.toml にスプレッドシートのID(spreadsheet_key)が設定されていません。")
    st.stop()

TARGET_SHEETS = {"店舗", "家賃条件", "販売手数料条件", "変更履歴", "取引先台帳調整データ", "ブランド", "ミロク部門", "poscm", "取引先", "合計取引先", "販売代行", "売上管理担当者", "営業担当者", "固定資産データ"}

def get_gspread_client():
    if "gcp_service_account" in st.secrets:
        return gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    d = os.path.dirname(os.path.abspath(__file__))
    for p in ["credentials.json", "credentials.json.json"]:
        if os.path.exists(os.path.join(d, p)): return gspread.service_account(filename=os.path.join(d, p))
    j = glob.glob(os.path.join(d, "*.json"))
    if j: return gspread.service_account(filename=j[0])
    raise FileNotFoundError("Google Cloudの認証キーが見つかりません。")

@st.cache_data(ttl=300, show_spinner=False)
def fetch_raw_data():
    gc = get_gspread_client()
    for attempt in range(4):
        try:
            sh = gc.open_by_key(SPREADSHEET_KEY)
            all_dfs = {}
            for ws in sh.worksheets():
                if ws.title not in TARGET_SHEETS: continue  
                records = ws.get_all_values()
                if not records:
                    all_dfs[ws.title] = pd.DataFrame()
                    continue
                headers = [str(h).strip() for h in records[0]]
                data = [r for r in records[1:] if any(str(c).strip() for c in r)]
                if not data:
                    all_dfs[ws.title] = pd.DataFrame(columns=headers)
                    continue
                max_len = len(headers)
                padded_data = [r + [""] * (max_len - len(r)) for r in data]
                padded_data = [r[:max_len] for r in padded_data]
                all_dfs[ws.title] = pd.DataFrame(padded_data, columns=headers).astype(str)
            return all_dfs
        except Exception as e:
            if "429" in str(e) or "Quota exceeded" in str(e):
                time.sleep(10)
            elif attempt < 3:
                time.sleep(3)
            else:
                raise e
    return {}

def save_all_data(all_dfs, target_sheets=None):
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SPREADSHEET_KEY)
        for s_name, d_f in all_dfs.items():
            if target_sheets is not None and s_name not in target_sheets: continue
            if d_f is not None:
                try: ws = sh.worksheet(s_name)
                except gspread.exceptions.WorksheetNotFound: ws = sh.add_worksheet(title=s_name, rows="100", cols="20")
                if d_f.empty:
                    data = [d_f.columns.values.tolist()] if not d_f.columns.empty else [["dummy"]]
                else:
                    d_f = d_f.fillna("").astype(str)
                    data = [d_f.columns.values.tolist()] + d_f.values.tolist()
                
                try: ws.update(values=data, range_name="A1")
                except TypeError:
                    try: ws.update("A1", data)
                    except: ws.update(data)
        st.cache_data.clear()
        st.toast("✅ データを安全に保存しました。")
        return True
    except Exception as e:
        st.error(f"❌ 保存エラー: {e}")
        return False

def add_history(df_history, operation, sheet, code, name, detail):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = st.session_state.get("user_email", "system")
    new_row = pd.DataFrame([{"日時": now, "操作者": user, "操作": operation, "対象シート": sheet, "店舗コード": code, "店舗名": name, "変更内容": detail}])
    return new_row if df_history is None or df_history.empty else pd.concat([new_row, df_history], ignore_index=True)
