import streamlit as st
import pandas as pd
from auth import authenticate

st.set_page_config(page_title="LMC店舗DB 統合版", layout="wide")

# ==========================================
# アプリ初期化とデータ読み込み
# ==========================================
authenticate()
user_role = st.session_state["user_role"]
user_email = st.session_state["user_email"]

if "all_dfs" not in st.session_state:
    from data_manager import fetch_raw_data
    with st.spinner("データベースから最新情報を取得しています..."):
        all_dfs = fetch_raw_data()
        if not all_dfs:
            st.error("スプレッドシートへの接続に失敗しました。設定を確認してください。")
            st.stop()
        st.session_state["all_dfs"] = all_dfs

all_dfs = st.session_state["all_dfs"]

# データフレームの準備
df = all_dfs.get("店舗", pd.DataFrame())
df_rent = all_dfs.get("家賃条件", pd.DataFrame())
df_history = all_dfs.get("変更履歴", pd.DataFrame(columns=["日時", "操作者", "操作", "対象シート", "店舗コード", "店舗名", "変更内容"]))

# ==========================================
# 共通関数群（旧システムの機能復元）
# ==========================================
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import unicodedata
import re
import streamlit.components.v1 as components
from data_manager import add_history, save_all_data

# 入力項目の右寄せスクリプト
js_code = """<script>
const doc = window.parent.document; doc.documentElement.setAttribute('translate', 'no');
doc.documentElement.className = 'notranslate';
setInterval(function() {
const inputs = doc.querySelectorAll('div[data-testid="stTextInput"]');
inputs.forEach(div => { const label = div.querySelector('label');
if (label && (label.innerText.includes('(円)') || label.innerText.includes('月額') || label.innerText.includes('費用'))) {
const input = div.querySelector('input'); if (input && input.style.textAlign !== 'right') { input.style.textAlign = 'right'; } } }); }, 500);
</script>"""
components.html(js_code, height=0, width=0)

def format_postal_code(val): s = str(val).replace("-", "").replace("ー", "").strip(); return f"{s[:3]}-{s[3:]}" if len(s) == 7 and s.isdigit() else str(val).strip()
def clean_str(val): s = str(val).strip(); return "" if not s or s in ["nan", "NaT", "None"] else (s[:-2] if s.endswith(".0") else s)
def normalize_match_str(val): return clean_str(val).replace(" ", "").replace(" ", "").lower()
def clean_code_7digits(val): return clean_str(val).zfill(7) if clean_str(val) else ""
def clean_code_8digits(val): return clean_str(val).zfill(8) if clean_str(val) else ""

def format_currency(val):
    s = str(val).replace(",", "").strip()
    if not s or s in ["nan", "NaT", "None"]: return ""
    try: return f"{float(s):,.2f}".rstrip('0').rstrip('.') if "." in s else f"{int(s):,}"
    except ValueError: return str(val).strip()

def parse_currency_to_float(val):
    try: return float(str(val).replace(",", "").strip())
    except ValueError: return 0.0

def parse_date(date_str):
    if not date_str or str(date_str).strip() in ["", "nan", "NaT", "None"]: return None
    try: return pd.to_datetime(date_str).date()
    except: return None

def format_date_str(val):
    d = parse_date(val)
    return d.strftime("%Y-%m-%d") if d else ""

def normalize_day(v):
    if pd.isna(v): return ""
    s = str(v).strip()
    if not s or s.lower() in ["nan", "nat", "none", "null"]: return ""
    if s.endswith(".0"): s = s[:-2]
    s = unicodedata.normalize('NFKC', s)
    if any(x in s for x in ["31", "末", "終"]): return "末日"
    nums = re.sub(r"\D", "", s)
    return f"{nums}日" if nums else s

def split_code_label(label): return str(label).split(" : ")[0].strip() if label else ""
def get_master_label(code, default_name, name_dict, cleaner=clean_str, code_only=False):
    c = cleaner(code)
    if not c: return ""
    if code_only: return c
    n = name_dict.get(c, str(default_name).strip())
    return f"{c} : {n}" if n else c

def create_options(df_master, code_col, name_col, formatter=clean_str, code_only=False):
    if df_master.empty or code_col not in df_master.columns: return [""], {}
    codes = [formatter(c) for c in df_master[code_col]]
    names = [str(n).strip() for n in df_master[name_col]] if name_col in df_master.columns else [""] * len(codes)
    mapping, opts_list = {}, [""]
    for c, n in zip(codes, names):
        if not c: continue
        if c not in mapping:
            mapping[c] = n
            opts_list.append(c if code_only else (f"{c} : {n}" if n else c))
    return opts_list, mapping

def get_safe_options(options_list, current_value):
    sl = list(options_list)
    if current_value not in sl: sl.append(current_value)
    return sl

def get_all_acc_emails(acc_dict):
    return [e.strip() for val in acc_dict.values() if isinstance(val, dict) and val.get("email") for e in str(val.get("email")).split(",") if e.strip()]

from auth import send_notification_email

AMOUNT_COLS = ["敷金・保証金", "内装費", "契約期間固定賃料", "契約期間変動賃料", "共益費", "契約期間共益費", "取得資産額", "固定賃料", "最低保証賃料", "基準売上高1", "基準売上高2", "基準売上高3", "店舗に付随する倉庫費用", "駐車場代\n※チケット除く", "変更後_固定賃料", "変更後_最低保証賃料", "変更後_基準売上高1", "変更後_基準売上高2", "変更後_基準売上高3", "基準売上", "最低保証額"]
RENAME_DICT = {k: f"{k}(月額)" for k in ["固定賃料", "最低保証賃料", "基準売上高1", "基準売上高2", "基準売上高3", "共益費", "変更後_固定賃料", "変更後_最低保証賃料", "変更後_基準売上高1", "変更後_基準売上高2", "変更後_基準売上高3", "基準売上", "最低保証額"]}

def display_styled_dataframe(df_target):
    disp_df = df_target.rename(columns={k: v for k, v in RENAME_DICT.items() if k in df_target.columns})
    cols = [RENAME_DICT.get(c, c) for c in AMOUNT_COLS if RENAME_DICT.get(c, c) in disp_df.columns]
    for c in cols: disp_df[c] = pd.to_numeric(disp_df[c].astype(str).str.replace(',', ''), errors='coerce')
    if cols and not disp_df.empty: st.dataframe(disp_df.style.format(formatter="{:,.0f}", na_rep="", subset=cols), use_container_width=True)
    else: st.dataframe(disp_df, use_container_width=True)
    return disp_df

def get_download_df(df_target):
    if df_target is None or df_target.empty: return pd.DataFrame()
    dl_df = df_target.rename(columns={k: v for k, v in RENAME_DICT.items() if k in df_target.columns}).copy()
    cols = [RENAME_DICT.get(c, c) for c in AMOUNT_COLS if RENAME_DICT.get(c, c) in df_target.columns]
    for c in cols:
        if c in dl_df.columns: dl_df[c] = dl_df[c].apply(format_currency)
    return dl_df

STORE_TYPE_OPTIONS = ["", "路面店", "デベロッパー", "アウトレット", "EC", "百貨店", "FC", "催事"]
SALES_TYPE_OPTIONS = ["", "直営", "売仕", "卸売"]
STATUS_OPTIONS = ["OPEN予定", "OPEN", "CLOSED"]
SALESPERSON_OPTIONS = ["", "社員", "販売代行"]
TAX_FREE_OPTIONS = ["", "有", "無"]
RENT_TYPE_OPTIONS = ["", "普通借家契約", "定期借家契約", "その他"]
DAY_OPTIONS_FULL = ["", "5日", "10日", "15日", "20日", "25日", "末日"]
APPLICATION_STATUS_OPTIONS = ["一時保存中", "申請書作成済・出力済"]
MBK_STATUS_OPTIONS = ["未申請", "申請中", "承認済", "否決", "不要"]
BHD_STATUS_OPTIONS = ["未申請", "申請中", "取締役会承認済", "否決", "不要"]

# マスタ辞書の生成
BRAND_OPTIONS, brand_dict = create_options(all_dfs.get("ブランド", pd.DataFrame()), "ブランドコード", "ブランド名", clean_str)
MIROKU_OPTIONS, miroku_dict = create_options(all_dfs.get("ミロク部門", pd.DataFrame()), "コード", "正式名称", clean_code_7digits, code_only=True)
POSCM_OPTIONS, poscm_dict = create_options(all_dfs.get("poscm", pd.DataFrame()), "POSCMレジコード", "POSCM店舗名", clean_code_8digits)
CLIENT_OPTIONS, client_dict = create_options(all_dfs.get("取引先", pd.DataFrame()), "ｺｰﾄﾞ", "正式名称", clean_str)
TOT_CLIENT_OPTIONS, tot_client_dict = create_options(all_dfs.get("合計取引先", pd.DataFrame()), "ｺｰﾄﾞ", "正式名称", clean_str)
AGENCY_OPTIONS, agency_dict = create_options(all_dfs.get("販売代行", pd.DataFrame()), "ｺｰﾄﾞ", "正式名称", clean_str)

acc_df = all_dfs.get("売上管理担当者", pd.DataFrame())
ACC_OPTIONS, acc_dict = [""], {}
if not acc_df.empty:
    names = [str(n).strip() for n in acc_df.get("売上管理担当者名", [])]
    emails = [str(e).strip() for e in acc_df.get("メールアドレス", [""]*len(names))]
    for n, e in zip(names, emails):
        if n:
            if n not in ACC_OPTIONS: ACC_OPTIONS.append(n)
            acc_dict[n] = {"email": e}
            
sales_rep_df = all_dfs.get("営業担当者", pd.DataFrame())
SALES_REP_OPTIONS, sales_rep_email_dict = [], {}
if not sales_rep_df.empty:
    names = [str(n).strip() for n in sales_rep_df.get("営業担当者名", [])]
    emails = [str(e).strip() for e in sales_rep_df.get("メールアドレス", [""]*len(names))]
    for n, e in zip(names, emails):
        if n:
            if n not in SALES_REP_OPTIONS: SALES_REP_OPTIONS.append(n)
            sales_rep_email_dict[n] = e

# ==========================================
# メニューと画面描画
# ==========================================
if "nav_jump" in st.session_state:
    st.session_state["menu_radio"] = st.session_state["nav_jump"]
    del st.session_state["nav_jump"]

st.sidebar.title(f"LMC店舗DB\n(権限: {user_role})")
menu_items = ["🏠 ダッシュボード", "🔍 店舗検索・閲覧", "➕ 新規店舗登録", "✏️ 店舗修正・削除", "🏢 家賃条件DB", "💼 販売手数料DB", "📈 固定資産データ更新", "📄 取引先台帳出力"]
if user_role == "経理":
    menu_items.append("⚙️ マスタ管理")
menu_items.extend(["📅 出退店リスト", "📜 有効契約一覧", "📝 変更履歴ログ", "📖 マニュアル"])
menu = st.sidebar.radio("メニュー", menu_items, key="menu_radio")

st.sidebar.markdown("---")
if st.sidebar.button("🚪 ログアウト", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.step1_passed = False
    st.session_state.user_role = None
    st.session_state.user_email = ""
    if "all_dfs" in st.session_state: del st.session_state["all_dfs"]
    st.rerun()
st.sidebar.markdown("---")
if st.sidebar.button("🔄 最新のデータを再読み込み", use_container_width=True):
    from data_manager import fetch_raw_data
    fetch_raw_data.clear()
    st.cache_data.clear()
    if "all_dfs" in st.session_state: del st.session_state["all_dfs"]
    st.rerun()

st.title("LMC店舗DB ✨最新・統合版")
st.caption("✅ 全機能・分割ファイル安定化版 (完全版コード)")

if menu == "🏠 ダッシュボード":
    st.subheader("🏠 ダッシュボード")
    today_dt = pd.to_datetime(date.today())
    
    st.markdown("### 📌 本日適用の条件変更（予約一覧）")
    df_rent_apply = df_rent.copy() if df_rent is not None and not df_rent.empty else pd.DataFrame()
    df_shops_apply = df.copy() if df is not None and not df.empty else pd.DataFrame()
    
    ready_rent = pd.DataFrame()
    ready_shops = pd.DataFrame()
    
    if not df_rent_apply.empty and '変更予定日' in df_rent_apply.columns:
        df_rent_apply['変更予定日_dt'] = pd.to_datetime(df_rent_apply['変更予定日'], errors='coerce')
        ready_rent = df_rent_apply[df_rent_apply['変更予定日_dt'].notna()]
        if not ready_rent.empty:
            ready_rent = ready_rent[ready_rent['変更予定日_dt'].dt.date <= today_dt.date()]
    
    if not df_shops_apply.empty and '掛率変更予定日' in df_shops_apply.columns:
        df_shops_apply['掛率変更予定日_dt'] = pd.to_datetime(df_shops_apply['掛率変更予定日'], errors='coerce')
        ready_shops = df_shops_apply[df_shops_apply['掛率変更予定日_dt'].notna()]
        if not ready_shops.empty:
            ready_shops = ready_shops[ready_shops['掛率変更予定日_dt'].dt.date <= today_dt.date()]
            
    if (not ready_rent.empty) or (not ready_shops.empty):
        st.error(f"🚨 適用期日が来ている変更予約があります (家賃: {len(ready_rent)}件, 店舗掛率: {len(ready_shops)}件)")
        if not ready_rent.empty:
            st.write("▼ 家賃条件の変更予約")
            st.dataframe(ready_rent[["店舗名", "変更予定日", "変更後_固定賃料", "変更後_最低保証賃料"]])
        if not ready_shops.empty:
            st.write("▼ 店舗掛率の変更予約")
            st.dataframe(ready_shops[["店舗名", "掛率変更予定日", "変更後_Ｐ掛率", "変更後_Ｓ掛率"]])
            
        if user_role == "経理":
            if st.button("⚡ 変更予約をマスタに一括適用して保存", type="primary"):
                with st.spinner("マスタへ適用中..."):
                    if not ready_rent.empty:
                        for idx, row in ready_rent.iterrows():
                            for k, col in [("固定賃料", "変更後_固定賃料"), ("最低保証賃料", "変更後_最低保証賃料"), ("基準売上高1", "変更後_基準売上高1")]:
                                if str(row.get(col, "")).strip():
                                    df_rent.at[idx, k] = format_currency(row.get(col, ""))
                            if str(row.get("変更後_歩合料率1", "")).strip():
                                df_rent.at[idx, "歩合料率1"] = str(row.get("変更後_歩合料率1", "")).strip()
                            df_rent.at[idx, "変更予定日"], df_rent.at[idx, "変更後_固定賃料"], df_rent.at[idx, "変更後_最低保証賃料"], df_rent.at[idx, "変更後_基準売上高1"], df_rent.at[idx, "変更後_歩合料率1"] = "", "", "", "", ""
                        all_dfs["変更履歴"] = add_history(df_history, "予約適用", "家賃条件", "", "複数", f"{len(ready_rent)}件の家賃変更を適用")
                        all_dfs["家賃条件"] = df_rent
                        
                    if not ready_shops.empty:
                        for idx, row in ready_shops.iterrows():
                            if str(row.get("変更後_Ｐ掛率", "")).strip(): df.at[idx, "P掛率"] = str(row.get("変更後_Ｐ掛率", "")).strip()
                            if str(row.get("変更後_Ｓ掛率", "")).strip(): df.at[idx, "S掛率"] = str(row.get("変更後_Ｓ掛率", "")).strip()
                            df.at[idx, "掛率変更予定日"], df.at[idx, "変更後_Ｐ掛率"], df.at[idx, "変更後_Ｓ掛率"] = "", "", ""
                        all_dfs["変更履歴"] = add_history(all_dfs.get("変更履歴", pd.DataFrame()), "予約適用", "店舗", "", "複数", f"{len(ready_shops)}件の掛率変更を適用")
                        all_dfs["店舗"] = df
                    
                    if save_all_data(all_dfs, target_sheets=["店舗", "家賃条件", "変更履歴"]):
                        from data_manager import fetch_raw_data
                        fetch_raw_data.clear()
                        st.cache_data.clear()
                        if "all_dfs" in st.session_state: del st.session_state["all_dfs"]
                        st.success("🎉 変更予約をマスタに適用しました！")
                        st.rerun()
        else:
            st.info("※マスタへの一括適用は経理担当者のみ実行可能です。")
    else:
        st.success("✅ 本日適用する変更予約はありません。")
        
    st.markdown("---")
    
    nm_end = today_dt + pd.offsets.MonthEnd(2)
    lm, nm = today_dt - pd.DateOffset(months=1), today_dt + pd.DateOffset(months=1)
    sml = today_dt + relativedelta(months=6)

    df_s = df.copy()
    df_s['tmp_rate_date'] = pd.to_datetime(df_s['掛率変更予定日'], errors='coerce')
    df_s['tmp_open'] = pd.to_datetime(df_s['開店日'], errors='coerce')
    df_s['tmp_close'] = pd.to_datetime(df_s['閉店日'], errors='coerce')
    df_s['ブランド'] = df_s['ブランドコード'].apply(lambda x: brand_dict.get(clean_str(x), "")) if 'ブランドコード' in df_s.columns else ""

    df_r = df_rent.copy() if df_rent is not None and not df_rent.empty else pd.DataFrame()
    if not df_r.empty: df_r['tmp_rent_date'], df_r['tmp_rent_end'] = pd.to_datetime(df_r['変更予定日'], errors='coerce'), pd.to_datetime(df_r['現契約終了日'], errors='coerce')

    active_df = df_s[df_s['ステータス'].isin(['OPEN', 'OPEN予定'])].copy()
    ledger_df = all_dfs.get("取引先台帳調整データ", pd.DataFrame())
    ledger_status_dict = {clean_str(r.get("U_Retail店舗コード", "")): str(r.get("申請ステータス", "")) for _, r in ledger_df.iterrows() if clean_str(r.get("U_Retail店舗コード", ""))} if not ledger_df.empty and "U_Retail店舗コード" in ledger_df.columns else {}
    
    st.markdown("### 🚀 出店承認パイプライン (OPEN予定の店舗)")
    pipeline_df = active_df[active_df['ステータス'] == 'OPEN予定'].copy()
    if not pipeline_df.empty:
        for c in ['MBK承認ステータス', 'BHD承認ステータス', '開店日']:
            if c not in pipeline_df.columns: pipeline_df[c] = ""
        c_p1, c_p2, c_p3 = st.columns(3)
        with c_p1:
            ps1 = pipeline_df[~pipeline_df['BHD承認ステータス'].isin(['取締役会承認済', '不要'])]
            st.info(f"**📝 親会社 申請/承認待ち ({len(ps1)}件)**")
            if not ps1.empty: st.dataframe(ps1[['店舗名', 'BHD承認ステータス']], use_container_width=True)
        pipeline_df['台帳ステータス'] = pipeline_df['U_Retail店舗コード'].apply(lambda x: ledger_status_dict.get(clean_str(x), "未作成"))
        with c_p2:
            ps2 = pipeline_df[pipeline_df['BHD承認ステータス'].isin(['取締役会承認済', '不要']) & (pipeline_df['台帳ステータス'] != '申請書作成済・出力済')]
            st.warning(f"**🏢 親会社承認済・台帳作成待ち ({len(ps2)}件)**")
            if not ps2.empty: st.dataframe(ps2[['店舗名', 'BHD承認ステータス', '台帳ステータス']], use_container_width=True)
        with c_p3:
            ps3 = pipeline_df[pipeline_df['BHD承認ステータス'].isin(['取締役会承認済', '不要']) & (pipeline_df['台帳ステータス'] == '申請書作成済・出力済')]
            st.success(f"**🎉 出店手続完了・OPEN待ち ({len(ps3)}件)**")
            if not ps3.empty: st.dataframe(ps3[['店舗名', '開店日', '台帳ステータス']], use_container_width=True)
    else: st.write("現在、OPEN予定の店舗はありません。")

    st.markdown("---")
    missing_alert = active_df[active_df['ミロク部門コード'].str.strip() == ""]
    renewal_alert_list = []
    if not df_r.empty:
        for _, r_row in df_r.iterrows():
            end_dt = r_row['tmp_rent_end']
            if pd.notnull(end_dt) and today_dt <= end_dt <= sml:
                dept_code, shop_name = clean_code_7digits(r_row.get('家賃計上部門コード', '')), r_row.get('店舗名', '')
                match_s = df_s[df_s['家賃計上部門コード'].apply(clean_code_7digits) == dept_code]
                if match_s.empty: match_s = df_s[df_s['店舗名'].str.strip() == str(shop_name).strip()]
                if not match_s.empty:
                    s_row = match_s.iloc[0]
                    if s_row.get('ステータス', '').upper() == 'CLOSED': continue
                    status = ledger_status_dict.get(clean_str(s_row.get("U_Retail店舗コード", "")), "未作成")
                    if status != "申請書作成済・出力済":
                        renewal_alert_list.append({'店舗名': shop_name, 'ブランド': s_row.get('ブランド', ''), '現契約終了日': end_dt.strftime('%Y-%m-%d'), '申請ステータス': status, '営業担当者': s_row.get('営業担当者名', '')})
                        
    renewal_alert_df = pd.DataFrame(renewal_alert_list)
    col_alert1, col_alert2 = st.columns(2)
    with col_alert1:
        st.markdown("### 🚨 要マスタ登録リスト (ミロク部門コード未入力)")
        if not missing_alert.empty:
            st.warning(f"**{len(missing_alert)}件**の店舗で、マスタ連携に必要な「ミロク部門コード」が未入力です。")
            st.dataframe(missing_alert[['店舗名', 'ブランド', 'ステータス', 'ミロク部門コード', '家賃計上部門コード', '取引先コード']], use_container_width=True)
        else: st.success("全てのOPEN/OPEN予定店舗でミロク部門コードが入力されています！")
    with col_alert2:
        st.markdown("### ⚠️ 契約満了が近い店舗 (台帳未作成)")
        if not renewal_alert_df.empty:
            st.error(f"**{len(renewal_alert_df)}件**の店舗で、6ヶ月以内に賃貸借契約が満了しますが、更新・退店等の取引先台帳（申請書）が出力されていません。")
            st.dataframe(renewal_alert_df, use_container_width=True)
        else: st.success("6ヶ月以内に契約満了を迎える店舗で、台帳未作成のものはありません！")

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 🔄 来月末までの条件変更予定")
        rate_alert = df_s[(df_s['tmp_rate_date'] > today_dt) & (df_s['tmp_rate_date'] <= nm_end)]
        if not rate_alert.empty:
            st.info(f"**掛率変更**: {len(rate_alert)}件"); st.dataframe(rate_alert[['店舗名', 'ブランド', '掛率変更予定日', '変更後_Ｐ掛率', '変更後_Ｓ掛率', '経理営業連絡メモ']], use_container_width=True)
        else: st.write("掛率の変更予定はありません。")
        if not df_r.empty:
            rent_alert = df_r[(df_r['tmp_rent_date'] > today_dt) & (df_r['tmp_rent_date'] <= nm_end)]
            if not rent_alert.empty:
                st.info(f"**家賃条件変更**: {len(rent_alert)}件"); st.dataframe(rent_alert[['店舗名', '変更予定日', '変更後_固定賃料', '変更後_最低保証賃料', '変更後_基準売上高1', '変更後_歩合料率1']], use_container_width=True)
            else: st.write("家賃の変更予定はありません。")

    with col2:
        st.markdown("### 🎊 直近1ヶ月の OPEN / CLOSE")
        open_alert = df_s[(df_s['tmp_open'] >= lm) & (df_s['tmp_open'] <= nm)].sort_values('tmp_open')
        if not open_alert.empty:
            st.success(f"**OPEN店舗**: {len(open_alert)}件"); st.dataframe(open_alert[['店舗名', 'ブランド', '開店日', '経理営業連絡メモ']], use_container_width=True)
        else: st.write("直近のOPEN予定はありません。")
        close_alert = df_s[(df_s['tmp_close'] >= lm) & (df_s['tmp_close'] <= nm)].sort_values('tmp_close')
        if not close_alert.empty:
            st.error(f"**CLOSE店舗**: {len(close_alert)}件"); st.dataframe(close_alert[['店舗名', 'ブランド', '閉店日', '経理営業連絡メモ']], use_container_width=True)
        else: st.write("直近のCLOSE予定はありません。")
elif menu == "🔍 店舗検索・閲覧":
    st.subheader("店舗の検索")
    col_s1, col_s2 = st.columns([3, 1])
    with col_s1: search_word = st.text_input("店舗名、またはブランドコードを入力してください:")
    with col_s2: show_closed = st.checkbox("退店済み(CLOSED)も表示", value=False)
    disp_df = df[df["店舗名"].str.contains(search_word, na=False, case=False) | df["ブランドコード"].str.contains(search_word, na=False, case=False) | df["U_Retail店舗コード"].str.contains(search_word, na=False, case=False)].copy() if search_word else df.copy()
    if not show_closed and "ステータス" in disp_df.columns: disp_df = disp_df[disp_df["ステータス"].str.upper() != "CLOSED"]
    if 'ブランドコード' in disp_df.columns:
        disp_df['ブランド名'] = disp_df['ブランドコード'].apply(lambda x: brand_dict.get(clean_str(x), ""))
        cols = disp_df.columns.tolist(); cols.remove('ブランド名'); cols.insert(cols.index('ブランドコード') + 1, 'ブランド名')
        disp_df = disp_df[cols]
    st.write(f"検索結果: {len(disp_df)} 件")
    
    st.info("💡 表の中の行（左端のチェックボックス）をクリックして選択すると、その店舗の修正画面へ自動ジャンプします。")
    
    event = st.dataframe(disp_df, use_container_width=True, selection_mode="single-row", on_select="rerun")
    
    selected_rows = []
    if isinstance(event, dict):
        selected_rows = event.get("selection", {}).get("rows", [])
    elif hasattr(event, "selection"):
        selected_rows = getattr(event.selection, "rows", [])
        
    if selected_rows and len(selected_rows) > 0:
        selected_row_pos = selected_rows[0]
        real_idx = disp_df.index[selected_row_pos]
        target_row = disp_df.iloc[selected_row_pos]
        c_code = str(target_row.get("U_Retail店舗コード", ""))
        c_name = str(target_row.get("店舗名", ""))
        jump_val = f"{real_idx} : {c_name} (コード: {c_code.strip() if c_code.strip() else '未定'})"
        st.session_state["jump_target_shop"] = jump_val
        st.session_state["nav_jump"] = "✏️ 店舗修正・削除"
        st.rerun()

elif menu == "➕ 新規店舗登録":
    st.subheader("新規店舗の登録")
    reg_mode = st.radio("登録タイプを選択してください", ["✨ 新規店舗を登録（白紙から入力）", "🔗 既存の複合店舗にブランド追加で登録（情報を引き継ぐ）"], horizontal=True)
    base_row, base_key_suffix = {}, "new"
    
    if reg_mode == "🔗 既存の複合店舗にブランド追加で登録（情報を引き継ぐ）":
        active_shops = df[df["ステータス"].str.upper() != "CLOSED"]
        idxs, names = active_shops.index.tolist(), active_shops["店舗名"].fillna("").astype(str).tolist()
        codes = active_shops.get("U_Retail店舗コード", pd.Series([""]*len(active_shops))).fillna("").astype(str).tolist()
        copy_shop_options = [""] + [f"{i} : {n} (コード: {c.strip() if c.strip() else '未定'})" for i, n, c in zip(idxs, names, codes)]
        selected_base_shop = st.selectbox("ベース店舗 🔍", copy_shop_options)
        if selected_base_shop:
            b_idx = int(selected_base_shop.split(" : ")[0])
            base_row, base_key_suffix = df.loc[b_idx].to_dict(), str(b_idx)
            st.success(f"💡 以下の情報を引き継いで新しい店舗レコードを作成します。\n・取引先: {base_row.get('取引先名', '未設定')}\n・住所: {base_row.get('住所', '未設定')}\n・販売代行: {base_row.get('販売代行名', '未設定')}\n・家賃計上部門コード: {base_row.get('家賃計上部門コード', '未設定')}")
        else: base_key_suffix = "none"
        
    st.markdown("---")
    is_brand_add = (reg_mode == "🔗 既存の複合店舗にブランド追加で登録（情報を引き継ぐ）")
    
    if is_brand_add:
        st.info("💡 既存店舗へのブランド追加の場合、事前出店申請プロセスは「不要」となります。")
        new_mbk_status, new_mbk_date, new_bhd_status, new_bhd_date = "不要", None, "不要", None
    else:
        new_mbk_status, new_mbk_date = "", None
        col_ap1, col_ap2 = st.columns(2)
        with col_ap1:
            def_bhd_status = base_row.get("BHD承認ステータス", "未申請") if base_row else "未申請"
            new_bhd_status = st.selectbox("BHD 承認ステータス", get_safe_options(BHD_STATUS_OPTIONS, def_bhd_status), index=get_safe_options(BHD_STATUS_OPTIONS, def_bhd_status).index(def_bhd_status), key=f"reg_bhd_{base_key_suffix}")
        with col_ap2:
            new_bhd_date = st.date_input("BHD 取締役会承認日", value=parse_date(base_row.get("BHD承認日", "")) if base_row else None, key=f"reg_bhd_dt_{base_key_suffix}")

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        def_name = base_row.get("店舗名", "") if base_row else ""
        new_shop_name = st.text_input("新しい店舗名 (必須)", value=def_name, key=f"reg_name_{base_key_suffix}")
        new_open_date = st.date_input("開店日", value=parse_date(base_row.get("開店日", "")) if base_row else None, key=f"reg_open_{base_key_suffix}")
        def_sales_type = base_row.get("販売形態", "") if base_row else ""
        new_sales_type = st.selectbox("販売形態", get_safe_options(SALES_TYPE_OPTIONS, def_sales_type), index=get_safe_options(SALES_TYPE_OPTIONS, def_sales_type).index(def_sales_type), key=f"reg_sales_{base_key_suffix}")
        def_store_type = base_row.get("店舗形態", "") if base_row else ""
        new_store_type = st.selectbox("店舗形態", get_safe_options(STORE_TYPE_OPTIONS, def_store_type), index=get_safe_options(STORE_TYPE_OPTIONS, def_store_type).index(def_store_type), key=f"reg_store_{base_key_suffix}")
        
    with col2:
        def_brand_code = base_row.get("ブランドコード", "") if base_row else ""
        def_brand_lbl = get_master_label(def_brand_code, "", brand_dict, clean_str)
        new_brand_code = st.selectbox("ブランド 🔍", get_safe_options(BRAND_OPTIONS, def_brand_lbl), index=get_safe_options(BRAND_OPTIONS, def_brand_lbl).index(def_brand_lbl), key=f"reg_brand_{base_key_suffix}")
        selected_b_code = split_code_label(new_brand_code)
        
        def_status = base_row.get("ステータス", "OPEN予定") if base_row else "OPEN予定"
        new_status = st.selectbox("ステータス", get_safe_options(STATUS_OPTIONS, def_status), index=get_safe_options(STATUS_OPTIONS, def_status).index(def_status), key=f"reg_status_{base_key_suffix}")
        
        def_acc_name = base_row.get("売上管理担当者名", "") if base_row else ""
        new_acc_name = st.selectbox("売上管理担当者名 🔍", get_safe_options(ACC_OPTIONS, def_acc_name), index=get_safe_options(ACC_OPTIONS, def_acc_name).index(def_acc_name), key=f"reg_acc_{base_key_suffix}")
        auto_acc_email = acc_dict.get(new_acc_name, {}).get("email", base_row.get("売上管理担当者メールアドレス", "") if new_acc_name == def_acc_name and base_row else "")
        new_acc_email = st.text_input("売上管理担当者メールアドレス (自動連動)", value=auto_acc_email, key=f"reg_acc_email_in_{base_key_suffix}")

        def_rep_raw = base_row.get("営業担当者名", "") if base_row else ""
        def_rep_list = [r.strip() for r in def_rep_raw.split(",") if r.strip()]
        rep_opts = list(SALES_REP_OPTIONS)
        for r in def_rep_list:
            if r not in rep_opts: rep_opts.append(r)
        new_sales_rep_names = st.multiselect("営業担当者名 (複数選択可) 🔍", rep_opts, default=def_rep_list, key=f"reg_sales_rep_names_{base_key_suffix}")
        
        auto_emails = []
        for name in new_sales_rep_names:
            e = sales_rep_email_dict.get(name, "")
            if not e and base_row and name in def_rep_list:
                er = base_row.get("営業担当者メールアドレス", "")
                el = [x.strip() for x in er.split(",") if x.strip()]
                if len(el) == len(def_rep_list): e = el[def_rep_list.index(name)]
            if e: auto_emails.append(e)
        
        new_sales_rep_email_str = ", ".join(auto_emails)
        new_sales_rep_email = st.text_input("営業担当者メールアドレス (自動連動)", value=new_sales_rep_email_str, key=f"reg_sales_rep_email_in_{base_key_suffix}")

    if st.button('💾 登録する', type="primary", key="reg_submit"):
        if not new_shop_name.strip(): st.warning("⚠️ 店舗名は必須項目です！")
        else:
            rnj = ", ".join(new_sales_rep_names)
            if base_row:
                new_row_data = base_row.copy()
                new_row_data.update({
                    "U_Retail店舗コード": "", "店舗名": new_shop_name.strip(), "ブランドコード": split_code_label(new_brand_code),
                    "開店日": new_open_date.strftime("%Y-%m-%d") if new_open_date else "", "販売形態": new_sales_type, "店舗形態": new_store_type,
                    "ステータス": new_status, "MBK承認ステータス": new_mbk_status, "MBK承認日": new_mbk_date.strftime("%Y-%m-%d") if new_mbk_date else "",
                    "BHD承認ステータス": new_bhd_status, "BHD承認日": new_bhd_date.strftime("%Y-%m-%d") if new_bhd_date else "",
                    "売上管理担当者コード": "", "売上管理担当者名": new_acc_name.strip(), "売上管理担当者メールアドレス": new_acc_email.strip(),
                    "営業担当者コード": selected_b_code, "営業担当者名": rnj, "営業担当者メールアドレス": new_sales_rep_email.strip(),
                    "経理営業連絡メモ": "", "経理確認済": ""
                })
                op_detail = "既存店舗の情報を引き継いでブランド追加（新規作成）"
            else:
                new_row_data = {
                    "U_Retail店舗コード": "", "店舗名": new_shop_name.strip(), "ブランドコード": split_code_label(new_brand_code),
                    "郵便番号": "", "住所": "", "電話番号": "", "携帯電話番号": "", "メールアドレス": "",
                    "開店日": new_open_date.strftime("%Y-%m-%d") if new_open_date else "", "閉店日": "",
                    "販売形態": new_sales_type, "店舗形態": new_store_type,
                    "P掛率": "", "S掛率": "", "セレクト_コラボP掛率": "", "セレクト_コラボS掛率": "",
                    "ミロク部門コード": "", "家賃計上部門コード": "", "取引先コード": "", "取引先名": "",
                    "合計取引先コード": "", "合計取引先名": "", "POSCMレジコード": "", "免税対応": "", "販売場識別符号": "",
                    "販売員": "", "販売代行コード": "", "販売代行名": "",
                    "MBK承認ステータス": new_mbk_status, "MBK承認日": new_mbk_date.strftime("%Y-%m-%d") if new_mbk_date else "",
                    "BHD承認ステータス": new_bhd_status, "BHD承認日": new_bhd_date.strftime("%Y-%m-%d") if new_bhd_date else "",
                    "経理確認済": "", "売上管理担当者コード": "", "売上管理担当者名": new_acc_name.strip(),
                    "売上管理担当者メールアドレス": new_acc_email.strip(), "営業担当者コード": selected_b_code, "営業担当者名": rnj, 
                    "営業担当者メールアドレス": new_sales_rep_email.strip(),
                    "締め日1": "", "締め日2": "", "入金日1": "", "入金日2": "", "家賃相殺日": "",
                    "ステータス": new_status, "変更予定日": "", "変更後_Ｐ掛率": "", "変更後_Ｓ掛率": "", "備考": "", "経理営業連絡メモ": ""
                }
                op_detail = "新しい店舗をゼロから登録"

            updated_df = pd.concat([df, pd.DataFrame([new_row_data])], ignore_index=True)
            all_dfs["変更履歴"] = add_history(df_history, "新規登録", "店舗", "", new_shop_name.strip(), op_detail)
            all_dfs["店舗"] = updated_df
            if save_all_data(all_dfs, target_sheets=["店舗", "変更履歴"]):
                send_notification_email(get_all_acc_emails(acc_dict), "【LMC店舗DB】新規店舗登録のお知らせ", "経理担当者様\n\nシステムにて新規店舗が登録されました。\nマスタへの部門コード等の登録をお願いいたします。\n\n※LMC店舗DBより自動送信")
                st.success("🎉 登録完了しました！"); st.rerun()

elif menu == "✏️ 店舗修正・削除":
    st.subheader("店舗データの修正・削除")
    st.info("💡 該当店舗を呼び出して、内容が正しいか確認してください。もし誤った取引先名や住所が入っている場合は、空欄にするか正しい内容に書き直して一番下の「💾 上書き保存」を押してください。")
    edit_search_word = st.text_input("🔍 店舗名やブランドコードで絞り込み:")
    filtered_edit_df = df[df["店舗名"].str.contains(edit_search_word, na=False, case=False) | df["ブランドコード"].str.contains(edit_search_word, na=False, case=False) | df["U_Retail店舗コード"].str.contains(edit_search_word, na=False, case=False)] if edit_search_word else df
    idxs = filtered_edit_df.index.tolist()
    names = filtered_edit_df["店舗名"].fillna("").astype(str).tolist()
    codes = filtered_edit_df.get("U_Retail店舗コード", pd.Series([""]*len(filtered_edit_df))).fillna("").astype(str).tolist()
    shop_options = [""] + [f"{i} : {n} (コード: {c.strip() if c.strip() else '未定'})" for i, n, c in zip(idxs, names, codes)]
    
    default_idx = 0
    if "jump_target_shop" in st.session_state and st.session_state["jump_target_shop"]:
        if st.session_state["jump_target_shop"] in shop_options:
            default_idx = shop_options.index(st.session_state["jump_target_shop"])
        del st.session_state["jump_target_shop"]

    if not shop_options: st.warning("条件に一致する店舗がありません。")
    else:
        selected_shop_str = st.selectbox("修正・削除する店舗:", shop_options, index=default_idx)
        if selected_shop_str:
            target_index = int(selected_shop_str.split(" : ")[0])
            target_row = df.loc[target_index]
            is_locked_in_db = str(target_row.get("経理確認済", "")).strip() == "True"
            is_accounting = (user_role == "経理")
            disable_editing = is_locked_in_db or (not is_accounting)
            
            if not is_accounting:
                st.info("👀 **【閲覧専用モード】** 店舗データの直接修正・削除は経理担当者のみ実行可能です。条件変更や退店の手続きは「📄 取引先台帳出力」から申請してください。")
            elif is_locked_in_db:
                st.error("🔒 **【経理ロック中】** この店舗データは経理部による確認が完了し、ロックされています。データの修正・上書き保存はできません。")
                unlock_pass = st.text_input("🔑 経理ロック解除パスワード", type="password", key=f"unlock_shop_{target_index}")
                expected_pass = str(st.secrets.get("acc_unlock_password", "")).strip()
                if expected_pass and str(unlock_pass).strip() == expected_pass:
                    st.success("🔓 パスワードが確認できました。ロックを解除して編集・保存が可能です。"); disable_editing = False
                elif unlock_pass: st.warning("⚠️ パスワードが違います")
            
            col_lock1, _ = st.columns([1, 2])
            with col_lock1: edit_lock = st.checkbox("☑️ 経理確認済 (データをロックし、編集を防ぐ)", value=is_locked_in_db, disabled=disable_editing)
            st.markdown("---")
            
            edit_mbk_status = target_row.get("MBK承認ステータス", "")
            edit_mbk_date = parse_date(target_row.get("MBK承認日", ""))
            col_ap1, col_ap2 = st.columns(2)
            with col_ap1:
                edit_bhd_status = st.selectbox("BHD 承認ステータス", get_safe_options(BHD_STATUS_OPTIONS, target_row.get("BHD承認ステータス", "未申請")), index=get_safe_options(BHD_STATUS_OPTIONS, target_row.get("BHD承認ステータス", "未申請")).index(target_row.get("BHD承認ステータス", "未申請")), disabled=disable_editing)
            with col_ap2:
                edit_bhd_date = st.date_input("BHD 取締役会承認日", value=parse_date(target_row.get("BHD承認日", "")), disabled=disable_editing)
            
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                edit_shop_code = st.text_input("U_Retail店舗コード", value=target_row.get("U_Retail店舗コード", ""), disabled=disable_editing)
                edit_shop_name = st.text_input("店舗名", value=target_row.get("店舗名", ""), disabled=disable_editing)
                edit_status = st.selectbox("ステータス", get_safe_options(STATUS_OPTIONS, target_row.get("ステータス", "OPEN予定")), index=get_safe_options(STATUS_OPTIONS, target_row.get("ステータス", "OPEN予定")).index(target_row.get("ステータス", "OPEN予定")), disabled=disable_editing)
                edit_sales_type = st.selectbox("販売形態", get_safe_options(SALES_TYPE_OPTIONS, target_row.get("販売形態", "")), index=get_safe_options(SALES_TYPE_OPTIONS, target_row.get("販売形態", "")).index(target_row.get("販売形態", "")), disabled=disable_editing)
                edit_store_type = st.selectbox("店舗形態", get_safe_options(STORE_TYPE_OPTIONS, target_row.get("店舗形態", "")), index=get_safe_options(STORE_TYPE_OPTIONS, target_row.get("店舗形態", "")).index(target_row.get("店舗形態", "")), disabled=disable_editing)
                edit_postal = st.text_input("郵便番号", value=target_row.get("郵便番号", ""), disabled=disable_editing)
                edit_address = st.text_input("住所", value=target_row.get("住所", ""), disabled=disable_editing)
                edit_phone = st.text_input("電話番号", value=target_row.get("電話番号", ""), disabled=disable_editing)
                edit_mobile = st.text_input("携帯電話番号", value=target_row.get("携帯電話番号", ""), disabled=disable_editing)
                edit_email = st.text_input("店舗メールアドレス", value=target_row.get("メールアドレス", ""), disabled=disable_editing)
                edit_open_date = st.date_input("開店日", value=parse_date(target_row.get("開店日", "")), disabled=disable_editing)
                edit_close_date = st.date_input("閉店日", value=parse_date(target_row.get("閉店日", "")), disabled=disable_editing)
                edit_tax_free = st.selectbox("免税対応", get_safe_options(TAX_FREE_OPTIONS, target_row.get("免税対応", "")), index=get_safe_options(TAX_FREE_OPTIONS, target_row.get("免税対応", "")).index(target_row.get("免税対応", "")), disabled=disable_editing)
                edit_sales_place_id = st.text_input("販売場識別符号", value=target_row.get("販売場識別符号", ""), disabled=disable_editing)
                
                st.write("📅 **スケジュール情報**")
                col_s_a, col_s_b = st.columns(2)
                with col_s_a:
                    edit_shime1 = st.selectbox("締め日1", get_safe_options(DAY_OPTIONS_FULL, normalize_day(target_row.get("締め日1", ""))), index=get_safe_options(DAY_OPTIONS_FULL, normalize_day(target_row.get("締め日1", ""))).index(normalize_day(target_row.get("締め日1", ""))), disabled=disable_editing)
                    edit_nyukin1 = st.selectbox("入金日1", get_safe_options(DAY_OPTIONS_FULL, normalize_day(target_row.get("入金日1", ""))), index=get_safe_options(DAY_OPTIONS_FULL, normalize_day(target_row.get("入金日1", ""))).index(normalize_day(target_row.get("入金日1", ""))), disabled=disable_editing)
                with col_s_b:
                    edit_shime2 = st.selectbox("締め日2", get_safe_options(DAY_OPTIONS_FULL, normalize_day(target_row.get("締め日2", ""))), index=get_safe_options(DAY_OPTIONS_FULL, normalize_day(target_row.get("締め日2", ""))).index(normalize_day(target_row.get("締め日2", ""))), disabled=disable_editing)
                    edit_nyukin2 = st.selectbox("入金日2", get_safe_options(DAY_OPTIONS_FULL, normalize_day(target_row.get("入金日2", ""))), index=get_safe_options(DAY_OPTIONS_FULL, normalize_day(target_row.get("入金日2", ""))).index(normalize_day(target_row.get("入金日2", ""))), disabled=disable_editing)
                edit_yachin_sosai = st.text_input("家賃相殺日", value=normalize_day(target_row.get("家賃相殺日", "")), disabled=disable_editing)
                edit_biko = st.text_area("備考", value=target_row.get("備考", ""), disabled=disable_editing)
                edit_keiri_memo = st.text_area("経理⇄営業 連絡メモ", value=target_row.get("経理営業連絡メモ", ""), disabled=disable_editing)

            with col2:
                edit_brand = st.selectbox("ブランド 🔍", get_safe_options(BRAND_OPTIONS, get_master_label(target_row.get("ブランドコード", ""), "", brand_dict, clean_str)), index=get_safe_options(BRAND_OPTIONS, get_master_label(target_row.get("ブランドコード", ""), "", brand_dict, clean_str)).index(get_master_label(target_row.get("ブランドコード", ""), "", brand_dict, clean_str)), disabled=disable_editing)
                selected_edit_b_code = split_code_label(edit_brand)
                edit_rent_dept = st.selectbox("家賃計上部門（共通部門） 🔍", get_safe_options(MIROKU_OPTIONS, get_master_label(target_row.get("家賃計上部門コード", ""), "", miroku_dict, clean_code_7digits, code_only=True)), index=get_safe_options(MIROKU_OPTIONS, get_master_label(target_row.get("家賃計上部門コード", ""), "", miroku_dict, clean_code_7digits, code_only=True)).index(get_master_label(target_row.get("家賃計上部門コード", ""), "", miroku_dict, clean_code_7digits, code_only=True)), disabled=disable_editing)
                edit_miroku = st.selectbox("ミロク部門 🔍", get_safe_options(MIROKU_OPTIONS, get_master_label(target_row.get("ミロク部門コード", ""), "", miroku_dict, clean_code_7digits, code_only=True)), index=get_safe_options(MIROKU_OPTIONS, get_master_label(target_row.get("ミロク部門コード", ""), "", miroku_dict, clean_code_7digits, code_only=True)).index(get_master_label(target_row.get("ミロク部門コード", ""), "", miroku_dict, clean_code_7digits, code_only=True)), disabled=disable_editing)
                edit_client = st.selectbox("取引先 🔍", get_safe_options(CLIENT_OPTIONS, get_master_label(target_row.get("取引先コード", ""), target_row.get("取引先名", ""), client_dict, clean_str)), index=get_safe_options(CLIENT_OPTIONS, get_master_label(target_row.get("取引先コード", ""), target_row.get("取引先名", ""), client_dict, clean_str)).index(get_master_label(target_row.get("取引先コード", ""), target_row.get("取引先名", ""), client_dict, clean_str)), disabled=disable_editing)
                edit_tot_client = st.selectbox("合計取引先 🔍", get_safe_options(TOT_CLIENT_OPTIONS, get_master_label(target_row.get("合計取引先コード", ""), target_row.get("合計取引先名", ""), tot_client_dict, clean_str)), index=get_safe_options(TOT_CLIENT_OPTIONS, get_master_label(target_row.get("合計取引先コード", ""), target_row.get("合計取引先名", ""), tot_client_dict, clean_str)).index(get_master_label(target_row.get("合計取引先コード", ""), target_row.get("合計取引先名", ""), tot_client_dict, clean_str)), disabled=disable_editing)
                edit_poscm = st.selectbox("POSCMレジコード 🔍", get_safe_options(POSCM_OPTIONS, get_master_label(target_row.get("POSCMレジコード", ""), "", poscm_dict, clean_code_8digits)), index=get_safe_options(POSCM_OPTIONS, get_master_label(target_row.get("POSCMレジコード", ""), "", poscm_dict, clean_code_8digits)).index(get_master_label(target_row.get("POSCMレジコード", ""), "", poscm_dict, clean_code_8digits)), disabled=disable_editing)
                edit_salesperson = st.selectbox("販売員", get_safe_options(SALESPERSON_OPTIONS, target_row.get("販売員", "")), index=get_safe_options(SALESPERSON_OPTIONS, target_row.get("販売員", "")).index(target_row.get("販売員", "")), disabled=disable_editing)
                edit_agency = st.selectbox("販売代行 🔍", get_safe_options(AGENCY_OPTIONS, get_master_label(target_row.get("販売代行コード", ""), target_row.get("販売代行名", ""), agency_dict, clean_str)), index=get_safe_options(AGENCY_OPTIONS, get_master_label(target_row.get("販売代行コード", ""), target_row.get("販売代行名", ""), agency_dict, clean_str)).index(get_master_label(target_row.get("販売代行コード", ""), target_row.get("販売代行名", ""), agency_dict, clean_str)), disabled=disable_editing)
                
                cur_rep_list = [r.strip() for r in target_row.get("営業担当者名", "").split(",") if r.strip()]
                rep_opts = list(SALES_REP_OPTIONS)
                for r in cur_rep_list:
                    if r not in rep_opts: rep_opts.append(r)
                edit_sales_rep_names = st.multiselect("営業担当者名 (複数選択可) 🔍", rep_opts, default=cur_rep_list, disabled=disable_editing)
                
                auto_emails = []
                for name in edit_sales_rep_names:
                    e = sales_rep_email_dict.get(name, "")
                    if not e and name in cur_rep_list:
                        e_list = [x.strip() for x in target_row.get("営業担当者メールアドレス", "").split(",") if x.strip()]
                        if len(e_list) == len(cur_rep_list): e = e_list[cur_rep_list.index(name)]
                    if e: auto_emails.append(e)
                edit_sales_rep_email = st.text_input("営業担当者メールアドレス (自動連動)", value=", ".join(auto_emails), disabled=disable_editing)
                
                can = target_row.get("売上管理担当者名", "")
                ean = st.selectbox("売上管理担当者名 🔍", get_safe_options(ACC_OPTIONS, can), index=get_safe_options(ACC_OPTIONS, can).index(can), disabled=disable_editing)
                eae = st.text_input("売上管理担当者メールアドレス (自動連動)", value=acc_dict.get(ean, {}).get("email", target_row.get("売上管理担当者メールアドレス", "")) if ean == can else acc_dict.get(ean, {}).get("email", ""), disabled=disable_editing)
                
                st.write("📊 **掛率情報**")
                cr1, cr2 = st.columns(2)
                with cr1:
                    edit_reg_p_rate = st.text_input("レギュラーP掛率", value=target_row.get("P掛率", ""), disabled=disable_editing)
                    edit_sel_p_rate = st.text_input("セレクト・コラボP掛率", value=target_row.get("セレクト_コラボP掛率", ""), disabled=disable_editing)
                with cr2:
                    edit_reg_s_rate = st.text_input("レギュラーS掛率", value=target_row.get("S掛率", ""), disabled=disable_editing)
                    edit_sel_s_rate = st.text_input("セレクト・コラボS掛率", value=target_row.get("セレクト_コラボS掛率", ""), disabled=disable_editing)
                edit_rate_change_date = st.date_input("掛率変更予定日", value=parse_date(target_row.get("掛率変更予定日", "")), disabled=disable_editing)
                cn1, cn2 = st.columns(2)
                with cn1: edit_next_p_rate = st.text_input("変更後_Ｐ掛率", value=target_row.get("変更後_Ｐ掛率", ""), disabled=disable_editing)
                with cn2: edit_next_s_rate = st.text_input("変更後_Ｓ掛率", value=target_row.get("変更後_Ｓ掛率", ""), disabled=disable_editing)

            st.markdown("---")
            st.write("📊 **保有固定資産一覧**")
            search_codes = [c for c in [clean_code_7digits(target_row.get("ミロク部門コード", "")), clean_code_7digits(target_row.get("家賃計上部門コード", ""))] if c]
            if search_codes:
                df_assets = all_dfs.get("固定資産データ", pd.DataFrame())
                if not df_assets.empty and "部門コード" in df_assets.columns:
                    df_assets["クリーン部門コード"] = df_assets["部門コード"].apply(lambda x: clean_code_7digits(str(x).split(".")[0]))
                    matched_assets = df_assets[df_assets["クリーン部門コード"].isin(search_codes)].copy()
                    if not matched_assets.empty:
                        if "資産種類名称" in matched_assets.columns: matched_assets = matched_assets[matched_assets["資産種類名称"].isin(["造作設備(定額)", "器具及び備品"])]
                        if "取得価額" in matched_assets.columns:
                            matched_assets["取得価額_num"] = pd.to_numeric(matched_assets["取得価額"], errors='coerce').fillna(0)
                            matched_assets["期末帳簿価額_num"] = pd.to_numeric(matched_assets.get("期末帳簿価額", 0), errors='coerce').fillna(0)
                            filter_price = st.session_state.get("filter_price", 100000)
                            filter_book = st.session_state.get("filter_book", 200000)
                            matched_assets = matched_assets[(matched_assets["取得価額_num"] >= filter_price) & (matched_assets["期末帳簿価額_num"] >= filter_book)]
                        
                    if not matched_assets.empty:
                        num_cols = ["取得価額", "期首帳簿価額", "当期償却額", "期末帳簿価額"]
                        active_num_cols = [c for c in num_cols if c in matched_assets.columns]
                        for c in active_num_cols: matched_assets[c] = pd.to_numeric(matched_assets[c], errors='coerce').fillna(0)
                        
                        st.markdown("##### 📌 科目別 小計")
                        subtotal_df = matched_assets.groupby("資産種類名称")[active_num_cols].sum().reset_index()
                        total_row = pd.DataFrame([{"資産種類名称": "【店舗合計】"}])
                        for c in active_num_cols: total_row[c] = subtotal_df[c].sum()
                        st.dataframe(pd.concat([subtotal_df, total_row], ignore_index=True).style.format(formatter="{:,.0f}", na_rep="", subset=active_num_cols), use_container_width=True)
                        
                        st.markdown("##### 📋 物件明細")
                        disp_cols = ["部門コード", "部門名称", "資産種類名称", "物件名称", "取得年月", "取得価額", "期首帳簿価額", "当期償却額", "期末帳簿価額", "備考"]
                        exist_cols = [c for c in disp_cols if c in matched_assets.columns]
                        st.dataframe(matched_assets[exist_cols].style.format(formatter="{:,.0f}", na_rep="", subset=active_num_cols), use_container_width=True)
                    else: st.write("該当する固定資産データはありません。")
                else: st.warning("※固定資産データが登録されていません。左メニューの「📈 固定資産データ更新」からCSVをアップロードしてください。")
            else: st.warning("※「ミロク部門コード」または「家賃計上部門」が未登録のため検索できません。")

            st.write("")
            col_btn1, col_btn2 = st.columns(2)
            if col_btn1.button('💾 上書き保存する', disabled=disable_editing):
                if not edit_shop_name.strip(): st.warning("⚠️ 店舗名は必須です！")
                else:
                    orw = df.loc[target_index].copy()
                    df.at[target_index, "U_Retail店舗コード"] = edit_shop_code.strip()
                    df.at[target_index, "店舗名"] = edit_shop_name.strip()
                    df.at[target_index, "ステータス"] = edit_status
                    df.at[target_index, "販売形態"] = edit_sales_type
                    df.at[target_index, "店舗形態"] = edit_store_type
                    df.at[target_index, "郵便番号"] = format_postal_code(edit_postal)
                    df.at[target_index, "住所"] = unicodedata.normalize('NFKC', edit_address.strip())
                    df.at[target_index, "電話番号"] = edit_phone.strip()
                    df.at[target_index, "携帯電話番号"] = edit_mobile.strip()
                    df.at[target_index, "メールアドレス"] = edit_email.strip()
                    df.at[target_index, "開店日"] = edit_open_date.strftime("%Y-%m-%d") if edit_open_date else ""
                    df.at[target_index, "閉店日"] = edit_close_date.strftime("%Y-%m-%d") if edit_close_date else ""
                    df.at[target_index, "免税対応"] = edit_tax_free.strip()
                    df.at[target_index, "販売場識別符号"] = edit_sales_place_id.strip()
                    df.at[target_index, "締め日1"] = normalize_day(edit_shime1)
                    df.at[target_index, "締め日2"] = normalize_day(edit_shime2)
                    df.at[target_index, "入金日1"] = normalize_day(edit_nyukin1)
                    df.at[target_index, "入金日2"] = normalize_day(edit_nyukin2)
                    df.at[target_index, "家賃相殺日"] = normalize_day(edit_yachin_sosai)
                    df.at[target_index, "備考"] = edit_biko.strip()
                    df.at[target_index, "経理営業連絡メモ"] = edit_keiri_memo.strip()
                    df.at[target_index, "ブランドコード"] = selected_edit_b_code
                    df.at[target_index, "家賃計上部門コード"] = clean_code_7digits(split_code_label(edit_rent_dept))
                    df.at[target_index, "ミロク部門コード"] = clean_code_7digits(split_code_label(edit_miroku))
                    df.at[target_index, "MBK承認ステータス"] = edit_mbk_status
                    df.at[target_index, "MBK承認日"] = edit_mbk_date.strftime("%Y-%m-%d") if edit_mbk_date else ""
                    df.at[target_index, "BHD承認ステータス"] = edit_bhd_status
                    df.at[target_index, "BHD承認日"] = edit_bhd_date.strftime("%Y-%m-%d") if edit_bhd_date else ""
                    df.at[target_index, "経理確認済"] = str(edit_lock)
                    df.at[target_index, "取引先コード"] = split_code_label(edit_client)
                    df.at[target_index, "取引先名"] = client_dict.get(split_code_label(edit_client), "") if split_code_label(edit_client) else ""
                    df.at[target_index, "合計取引先コード"] = split_code_label(edit_tot_client)
                    df.at[target_index, "合計取引先名"] = tot_client_dict.get(split_code_label(edit_tot_client), "") if split_code_label(edit_tot_client) else ""
                    df.at[target_index, "POSCMレジコード"] = clean_code_8digits(split_code_label(edit_poscm))
                    df.at[target_index, "販売員"] = edit_salesperson
                    df.at[target_index, "販売代行コード"] = split_code_label(edit_agency)
                    df.at[target_index, "販売代行名"] = agency_dict.get(split_code_label(edit_agency), "") if split_code_label(edit_agency) else ""
                    df.at[target_index, "営業担当者コード"] = selected_edit_b_code
                    df.at[target_index, "営業担当者名"] = ", ".join(edit_sales_rep_names)
                    df.at[target_index, "営業担当者メールアドレス"] = edit_sales_rep_email.strip()
                    df.at[target_index, "売上管理担当者コード"] = ""
                    df.at[target_index, "売上管理担当者名"] = ean.strip()
                    df.at[target_index, "売上管理担当者メールアドレス"] = eae.strip()
                    df.at[target_index, "P掛率"] = edit_reg_p_rate.strip()
                    df.at[target_index, "S掛率"] = edit_reg_s_rate.strip()
                    df.at[target_index, "セレクト_コラボP掛率"] = edit_sel_p_rate.strip()
                    df.at[target_index, "セレクト_コラボS掛率"] = edit_sel_s_rate.strip()
                    df.at[target_index, "掛率変更予定日"] = edit_rate_change_date.strftime("%Y-%m-%d") if edit_rate_change_date else ""
                    df.at[target_index, "変更後_Ｐ掛率"] = edit_next_p_rate.strip()
                    df.at[target_index, "変更後_Ｓ掛率"] = edit_next_s_rate.strip()
                    
                    chg = [f"[{c}] '{orw[c]}'→'{df.at[target_index, c]}'" for c in orw.index if str(orw[c]).strip() != str(df.at[target_index, c]).strip()]
                    
                    chg_str = "\n".join(chg) if chg else "変更なし"
                    all_dfs["店舗"] = df
                    if save_all_data(all_dfs, target_sheets=["店舗", "変更履歴"]):
                        if chg:
                            te = eae.strip() if eae.strip() else get_all_acc_emails(acc_dict)
                            mail_text = f"経理担当者様\n\nシステムにて店舗「{edit_shop_name.strip()}」の情報が変更されました。\n\n【変更内容】\n{chg_str}\n\nシステムより内容をご確認ください。\n\n※店舗DBシステムより自動送信"
                            send_notification_email(te, "【店舗DB】店舗情報変更のお知らせ", mail_text)
                        from data_manager import fetch_raw_data
                        fetch_raw_data.clear()
                        if "all_dfs" in st.session_state: del st.session_state["all_dfs"]
                        st.success("🎉 上書き保存完了！"); st.rerun()

            if col_btn2.button('🗑️ この店舗を削除する', disabled=disable_editing):
                st.session_state['deleted_row'] = target_row.to_dict()
                udf = df.drop(target_index)
                all_dfs["変更履歴"] = add_history(df_history, "削除", "店舗", target_row.get("U_Retail店舗コード",""), target_row.get("店舗名",""), "店舗データを削除")
                all_dfs["店舗"] = udf
                if save_all_data(all_dfs, target_sheets=["店舗", "変更履歴"]):
                    from data_manager import fetch_raw_data
                    fetch_raw_data.clear()
                    if "all_dfs" in st.session_state: del st.session_state["all_dfs"]
                    st.rerun()

elif menu == "🏢 家賃条件DB":
    st.subheader("🏢 家賃条件データベース管理")
    scr = st.checkbox("退店済み(CLOSED)も表示", value=False)
    t1, t2 = st.tabs(["📋 家賃条件一覧", "✏️ 条件の登録・更新"])
    vs = df[(df["家賃計上部門コード"].str.strip() != "") | (df["販売形態"].str.strip().isin(["直営", "卸売"]))].copy()
    if not scr and "ステータス" in vs.columns: vs = vs[vs["ステータス"].str.upper() != "CLOSED"]
    with t1:
        drc = vs["家賃計上部門コード"].str.strip().unique()
        display_styled_dataframe(df_rent[df_rent["家賃計上部門コード"].str.strip().isin(drc)] if not scr else df_rent)
    with t2:
        ssl = list(dict.fromkeys([f"{c.strip() if c.strip() else '部門コード未設定'} : {n}" for c, n in zip(vs.get("家賃計上部門コード", pd.Series([""]*len(vs))).fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7).tolist(), vs["店舗名"].fillna("").astype(str).tolist())]))
        if ssl:
            srs = st.selectbox("対象の店舗を選んでください:", ssl)
            trc = clean_code_7digits(srs.split(" : ")[0]) if srs.split(" : ")[0] != "部門コード未設定" else ""
            tdn = srs.split(" : ")[1]
            smi = df[df["店舗名"] == tdn]
            sir = smi.iloc[0] if not smi.empty else {}
            
            lsr = {}
            sld = all_dfs.get("取引先台帳調整データ", pd.DataFrame())
            if not sld.empty and "U_Retail店舗コード" in sld.columns:
                ml = sld[sld["U_Retail店舗コード"] == sir.get("U_Retail店舗コード", "")]
                if not ml.empty: lsr = ml.iloc[0].to_dict()

            er = df_rent[df_rent["店舗名"] == tdn] if not trc else df_rent[df_rent["家賃計上部門コード"].apply(clean_code_7digits) == trc]
            rr = er.iloc[0] if not er.empty else {}
            
            ilr = str(rr.get("経理確認済", "")).strip() == "True"
            der = ilr
            if ilr:
                st.error("🔒 **【経理ロック中】** この家賃条件データは経理部による確認が完了し、ロックされています。データの修正・上書き保存はできません。")
                upr = st.text_input("🔑 経理ロック解除パスワードを入力", type="password", key=f"unlock_rent_{trc}")
                expected_rent_pass = str(st.secrets.get("acc_unlock_password", "")).strip()
                if expected_rent_pass and str(upr).strip() == expected_rent_pass:
                    st.success("🔓 パスワードが確認できました。ロックを解除して編集・保存が可能です。"); der = False
                elif upr: st.warning("⚠️ パスワードが違います")

            with st.columns([1, 2])[0]: erl = st.checkbox("☑️ 経理確認済 (データをロックし、編集を防ぐ)", value=ilr, disabled=der)

            with st.form(key='rent_form'):
                c1, c2 = st.columns(2)
                with c1:
                    st.text_input("家賃計上部門コード", value=trc if trc else "未設定", disabled=True)
                    st.text_input("対象店舗名", value=tdn, disabled=True)
                    rad = st.text_input("住所 (自動引き継ぎ)", value=rr.get("住所", sir.get("住所", "")), disabled=der)
                    rar = st.text_input("面積(㎡)", value=rr.get("面積", lsr.get("面積", "")), disabled=der)
                    rty = st.selectbox("契約種類", get_safe_options(RENT_TYPE_OPTIONS, str(rr.get("契約種類", ""))), index=get_safe_options(RENT_TYPE_OPTIONS, str(rr.get("契約種類", ""))).index(str(rr.get("契約種類", ""))), disabled=der)
                    rco = st.selectbox("契約先 🔍", get_safe_options(CLIENT_OPTIONS, rr.get("契約先", sir.get("取引先名", ""))), index=get_safe_options(CLIENT_OPTIONS, rr.get("契約先", sir.get("取引先名", ""))).index(rr.get("契約先", sir.get("取引先名", ""))), disabled=der)
                    rfx = st.text_input("固定賃料 (月額/円)", value=format_currency(rr.get("固定賃料", lsr.get("固定賃料", ""))), disabled=der)
                    rmg = st.text_input("最低保証賃料 (月額/円)", value=format_currency(rr.get("最低保証賃料", lsr.get("最低保証賃料", ""))), disabled=der)
                    
                    st.markdown("##### 📊 歩合条件")
                    rbs = st.text_input("基準売上高1 (月額/円)", value=format_currency(rr.get("基準売上高1", lsr.get("基準売上高", ""))), disabled=der)
                    rr1 = st.text_input("歩合料率1", value=rr.get("歩合料率1", lsr.get("歩合料率", "")), disabled=der)
                    rbs2 = st.text_input("基準売上高2 (月額/円)", value=format_currency(rr.get("基準売上高2", "")), disabled=der)
                    rr2 = st.text_input("歩合料率2", value=rr.get("歩合料率2", ""), disabled=der)
                    
                with c2:
                    rst = st.date_input("原契約開始日 (開店日/台帳連動)", value=parse_date(rr.get("原契約開始日", lsr.get("賃貸借契約開始日", sir.get("開店日", "")))), disabled=der)
                    rcs = st.date_input("現契約開始日", value=parse_date(rr.get("現契約開始日", "")), disabled=der)
                    ren = st.date_input("現契約終了日 (閉店日/台帳連動)", value=parse_date(rr.get("現契約終了日", lsr.get("賃貸借契約終了日", sir.get("閉店日", "")))), disabled=der)
                    st.text_input("現契約期間 (年)", value=str(rr.get("現契約期間", "")), disabled=True)
                    rdp = st.text_input("敷金・保証金 (円)", value=format_currency(rr.get("敷金・保証金", lsr.get("敷金_保証金", ""))), disabled=der)
                    rin = st.text_input("内装費 (円)", value=format_currency(rr.get("内装費", "")), disabled=der)
                    st.text_input("契約期間固定賃料 (円)", value=format_currency(rr.get("契約期間固定賃料", "")), disabled=True)
                    rcv = st.text_input("契約期間変動賃料 (円)", value=format_currency(rr.get("契約期間変動賃料", "")), disabled=der)
                    rcf = st.text_input("共益費(月額/円)", value=format_currency(rr.get("共益費", "")), disabled=der)
                    st.text_input("契約期間共益費 (円)", value=format_currency(rr.get("契約期間共益費", "")), disabled=True)
                    st.text_input("取得資産額 (円)", value=format_currency(rr.get("取得資産額", "")), disabled=True)
                    rop = st.text_input("契約延長・解約オプション", value=rr.get("契約延長・解約ｵﾌﾟｼｮﾝ", ""), disabled=der)
                    rwh = st.text_input("倉庫費用 (月額/円)", value=format_currency(rr.get("店舗に付随する倉庫費用", "")), disabled=der)
                    rpk = st.text_input("駐車場代\n※チケット除く", value=format_currency(rr.get("駐車場代\n※チケット除く", "")), disabled=der)
                
                c3, c4 = st.columns(2)
                with c3:
                    rcd = st.date_input("変更予定日", value=parse_date(rr.get("変更予定日", "")), disabled=der)
                    rnf = st.text_input("変更後_固定賃料 (月額/円)", value=format_currency(rr.get("変更後_固定賃料", "")), disabled=der)
                    rnm = st.text_input("変更後_最低保証賃料 (月額/円)", value=format_currency(rr.get("変更後_最低保証賃料", "")), disabled=der)
                with c4:
                    rnb = st.text_input("変更後_基準売上高1 (月額/円)", value=format_currency(rr.get("変更後_基準売上高1", "")), disabled=der)
                    rnr = st.text_input("変更後_歩合料率1", value=format_currency(rr.get("変更後_歩合料率1", "")), disabled=der)
                
                if st.form_submit_button('💾 家賃条件を保存する', disabled=der):
                    yrs = (ren - rcs).days / 365.25 if rcs and ren and (ren - rcs).days > 0 else 0.0
                    cf, cc = parse_currency_to_float(rfx) * (yrs * 12), parse_currency_to_float(rcf) * (yrs * 12)
                    cas = cf + parse_currency_to_float(rcv) + cc + parse_currency_to_float(rdp) + parse_currency_to_float(rin)
                    
                    nr = {
                        "家賃計上部門コード": trc, "店舗名": tdn, "住所": rad.strip(), "面積": rar.strip(), "契約種類": rty.strip(), "契約先": split_code_label(rco), 
                        "原契約開始日": rst.strftime("%Y-%m-%d") if rst else "", "現契約開始日": rcs.strftime("%Y-%m-%d") if rcs else "", "現契約終了日": ren.strftime("%Y-%m-%d") if ren else "", 
                        "現契約期間": f"{yrs:.1f}" if yrs else "", "敷金・保証金": format_currency(rdp), "内装費": format_currency(rin), 
                        "契約期間固定賃料": format_currency(f"{cf:.0f}" if cf else ""), "契約期間変動賃料": format_currency(rcv), "共益費": format_currency(rcf), "契約期間共益費": format_currency(f"{cc:.0f}" if cc else ""),
                        "取得資産額": format_currency(f"{cas:.0f}" if cas else ""), "固定賃料": format_currency(rfx), "最低保証賃料": format_currency(rmg), 
                        "基準売上高1": format_currency(rbs), "歩合料率1": rr1.strip(), 
                        "基準売上高2": format_currency(rbs2), "歩合料率2": rr2.strip(), 
                        "契約延長・解約ｵﾌﾟｼｮﾝ": rop.strip(), "店舗に付随する倉庫費用": format_currency(rwh), "駐車場代\n※チケット除く": format_currency(rpk), 
                        "変更予定日": rcd.strftime("%Y-%m-%d") if rcd else "", "変更後_固定賃料": format_currency(rnf), "変更後_最低保証賃料": format_currency(rnm), 
                        "変更後_基準売上高1": format_currency(rnb), "変更後_歩合料率1": rnr.strip(), "経理確認済": str(erl)
                    }
                    
                    irc = True if er.empty else any(str(er.iloc[0].get(k, "")).strip() != str(v).strip() for k, v in nr.items() if k != "更新日時")
                    chg_rent = [f"[{k}] '{er.iloc[0].get(k, '')}'→'{v}'" for k, v in nr.items() if str(er.iloc[0].get(k, "")).strip() != str(v).strip()] if not er.empty else ["新規作成"]
                    
                    if not er.empty:
                        for k, v in nr.items(): df_rent.at[er.index[0], k] = v
                    else: df_rent = pd.concat([df_rent, pd.DataFrame([nr])], ignore_index=True)
                    
                    chg_rent_str = "\n".join(chg_rent) if chg_rent else "変更なし"
                    all_dfs["変更履歴"] = add_history(df_history, "修正", "家賃条件", trc if trc else "未設定", tdn, " / ".join(chg_rent) if chg_rent else "条件更新")
                    all_dfs["家賃条件"] = df_rent
                    if save_all_data(all_dfs, target_sheets=["家賃条件", "変更履歴"]):
                        if irc:
                            te = smi.iloc[0].get("売上管理担当者メールアドレス", "").strip() if not smi.empty else ""
                            mail_text = f"経理担当者様\n\nシステムにて店舗「{tdn}」の「家賃条件」または「契約期間」に関する情報が変更されました。\n\n【変更内容】\n{chg_rent_str}\n\nシステムより内容をご確認ください。\n\n※店舗DBシステムより自動送信"
                            send_notification_email(te if te else get_all_acc_emails(acc_dict), "【店舗DB】家賃・契約条件変更のお知らせ", mail_text)
                        st.success("🎉 保存完了！"); st.rerun()

elif menu == "💼 販売手数料DB":
    st.subheader("💼 販売手数料条件データベース管理")
    df_fee = all_dfs.get("販売手数料条件", pd.DataFrame())
    
    tab_list, tab_edit = st.tabs(["📋 一覧・CSV出力", "✏️ 条件の登録・更新"])
    
    with tab_list:
        st.info("💡 予算作成アプリ等にアップロードするための「販売手数料条件」の全件データをCSVで出力できます。")
        if not df_fee.empty:
            st.dataframe(df_fee, use_container_width=True)
            csv_data = get_download_df(df_fee).to_csv(index=False).encode('utf_8_sig')
            dl_name = f"販売手数料条件データ_{datetime.now().strftime('%Y%m%d')}.csv"
            st.download_button("📥 全件データをCSVでダウンロード", data=csv_data, file_name=dl_name, mime="text/csv", type="primary")
        else:
            st.write("データがありません。")

    with tab_edit:
        if not df_fee.empty:
            df_fee["代行表示名"] = df_fee.apply(lambda r: f"{clean_str(r.get('ミロク取引先コード',''))} : {clean_str(r.get('販売代行名',''))}" if clean_str(r.get('販売代行名','')) else "", axis=1)
            df_fee["表示用グループ名"] = df_fee.apply(lambda r: clean_str(r.get("共通部門名","")) if clean_str(r.get("共通部門名","")) else clean_str(r.get("部門名","")), axis=1)
            sel_daiko = st.selectbox("👤 販売代行名:", [""] + sorted([x for x in df_fee["代行表示名"].unique() if x]))
            if sel_daiko:
                sel_grp = st.selectbox("🏢 店舗:", [""] + sorted([str(x) for x in df_fee[df_fee["代行表示名"] == sel_daiko]["表示用グループ名"].unique() if str(x).strip() != ""]))
                if sel_grp:
                    t_df = df_fee[(df_fee["代行表示名"] == sel_daiko) & (df_fee["表示用グループ名"] == sel_grp)]
                    f_row = t_df.iloc[0]
                    with st.form(key='fee_form'):
                        in_base = st.text_input("基準売上高 (月額/円)", value=format_currency(f_row.get("基準売上", "")))
                        in_guar = st.text_input("最低保証額 (月額/円)", value=format_currency(f_row.get("最低保証額", "")))
                        up_fees = {}
                        for idx, row in t_df.iterrows():
                            st.write(f"**{row.get('部門名','')}** (コード: {row.get('部門コード','')})")
                            c1, c2, c3 = st.columns(3)
                            up_fees[idx] = {"P": c1.text_input("P手数料率", value=str(row.get("P手数料率", "")).replace("nan", ""), key=f"p_{idx}").strip(), "S": c2.text_input("S手数料率", value=str(row.get("S手数料率", "")).replace("nan", ""), key=f"s_{idx}").strip(), "F2": c3.text_input("手数料率_2", value=str(row.get("手数料率_2", "")).replace("nan", ""), key=f"f2_{idx}").strip()}
                        if st.form_submit_button("💾 一括保存する", type="primary"):
                            for idx, vals in up_fees.items():
                                df_fee.at[idx, "基準売上"], df_fee.at[idx, "最低保証額"], df_fee.at[idx, "P手数料率"], df_fee.at[idx, "S手数料率"], df_fee.at[idx, "手数料率_2"] = format_currency(in_base), format_currency(in_guar), vals["P"], vals["S"], vals["F2"]
                            all_dfs["販売手数料条件"] = df_fee.drop(columns=["代行表示名", "表示用グループ名"])
                            all_dfs["変更履歴"] = add_history(df_history, "修正", "販売手数料", sel_grp, sel_daiko.split(" : ")[-1], "手数料更新")
                            if save_all_data(all_dfs, target_sheets=["販売手数料条件", "変更履歴"]): st.success("🎉 保存完了！"); st.rerun()

elif menu == "📈 固定資産データ更新":
    st.subheader("📈 固定資産データの手動更新")
    st.info("💡 毎月の「資産別固定資産減価償却内訳表.csv」をここにアップロードしてください。データはスプレッドシートに保存され、全ユーザーに共有されます。")
    uploaded_file = st.file_uploader("CSVファイルを選択してアップロード", type=["csv"])
    if uploaded_file is not None:
        try: df_assets_new = pd.read_csv(uploaded_file, encoding='cp932')
        except: uploaded_file.seek(0); df_assets_new = pd.read_csv(uploaded_file, encoding='utf-8')
        st.success(f"✅ ファイルを読み込みました（データ件数: {len(df_assets_new)} 件）。")
        st.dataframe(df_assets_new.head(), use_container_width=True)
        if st.button("💾 このデータでシステム（スプレッドシート）を更新する", type="primary", use_container_width=True):
            with st.spinner("スプレッドシートへ保存中...（データが多い場合は数十秒かかります）"):
                all_dfs["固定資産データ"] = df_assets_new.astype(str)
                all_dfs["変更履歴"] = add_history(df_history, "更新", "固定資産データ", "", "システム全体", "固定資産データのCSV手動アップロード更新")
                if save_all_data(all_dfs, target_sheets=["固定資産データ", "変更履歴"]):
                    from data_manager import fetch_raw_data
                    fetch_raw_data.clear()
                    if "all_dfs" in st.session_state: del st.session_state["all_dfs"]
                    st.success("🎉 固定資産データの更新が完了しました！"); time.sleep(2); st.rerun()

elif menu == "📄 取引先台帳出力":
    st.subheader("📄 取引先台帳（出退店申請書）出力")
    st.info("💡 店舗を検索して選択するには、文字入力後にEnterキーを押すかリストからクリックしてください。")
    
    TRADING_TYPE_OPTIONS = ["売仕", "卸売", "直営_デベロッパー", "直営_路面店"]
    STORE_FORMAT_OPTIONS = ["実店舗", "EC", "催事"]
    APPLICATION_TYPE_OPTIONS = ["新規出店", "更新・条件変更あり", "更新・条件変更なし", "退店", "ブランド追加"]
    INTERIOR_OPTIONS = ["無", "有"]
    AGENCY_TYPE_OPTIONS = ["販売代行", "社員", "その他"]
    DAY_OPTIONS = ["末日", "5日", "10日", "15日", "20日", "25日"]

    def on_ledger_shop_change():
        st.session_state["form_reset_token"] = st.session_state.get("form_reset_token", 0) + 1
        keys_to_delete = []
        for k in st.session_state.keys():
            if any(k.startswith(p) for p in ["in_", "sel_", "chk_"]):
                if k != "sel_target_shop_main":
                    keys_to_delete.append(k)
        for k in keys_to_delete:
            del st.session_state[k]

    saved_ledger_df = all_dfs.get("取引先台帳調整データ", pd.DataFrame())
    fee_df = all_dfs.get("販売手数料条件", pd.DataFrame())
    fee_dict = {}
    if not fee_df.empty:
        for d in fee_df.to_dict(orient='records'):
            fc = clean_str(d.get("部門コード", ""))
            if fc: fee_dict[fc] = d

    client_df = all_dfs.get("取引先", pd.DataFrame())
    c_addr_dict, c_tel_dict, c_zip_dict = {}, {}, {}
    if not client_df.empty:
        for _, r in client_df.iterrows():
            c = clean_str(r.get("ｺｰﾄﾞ", ""))
            a = clean_str(r.get("住所", r.get("所在地", "")))
            t = clean_str(r.get("TEL", r.get("電話番号", "")))
            z = format_postal_code(clean_str(r.get("郵便番号", r.get("〒", ""))))
            if c: c_addr_dict[c], c_tel_dict[c], c_zip_dict[c] = a, t, z

    rent_dict, rent_name_dict = {}, {}
    if df_rent is not None and not df_rent.empty:
        for d in df_rent.to_dict(orient='records'):
            rc = clean_code_7digits(d.get("家賃計上部門コード", ""))
            rn = clean_str(d.get("店舗名", ""))
            if rc: rent_dict[rc] = d
            if rn: rent_name_dict[rn] = d

    def get_val(saved_dict, key, fallback):
        v = str(saved_dict.get(key, "")).strip() if saved_dict else ""
        if v and v not in ["nan", "None", "NaT"]: return v
        return fallback

    def fetch_single_ledger_row(shop_row):
        sc = clean_str(shop_row.get("U_Retail店舗コード", ""))
        rc = clean_code_7digits(shop_row.get("家賃計上部門コード", ""))
        cc = clean_str(shop_row.get("取引先コード", ""))
        s_name_clean = clean_str(shop_row.get("店舗名", ""))
        
        rd = rent_dict.get(rc) or rent_name_dict.get(s_name_clean) or {}
        fd = fee_dict.get(sc, {})
        stype = clean_str(shop_row.get("販売形態", ""))
        storetype = clean_str(shop_row.get("店舗形態", ""))
        
        if stype == "売仕": d_trading = "売仕"
        elif stype == "卸売": d_trading = "卸売"
        elif "直営" in stype: d_trading = "直営_デベロッパー" if "デベロッパー" in storetype else "直営_路面店"
        else: d_trading = "売仕"

        if storetype == "催事": d_store_format = "催事"
        elif storetype == "EC": d_store_format = "EC"
        else: d_store_format = "実店舗"

        dcode = clean_str(shop_row.get("販売代行コード", ""))
        dname_raw = clean_str(shop_row.get("販売代行名", ""))
        dname = agency_dict.get(dcode, dname_raw) if dcode else dname_raw
        
        saved_row = {}
        if not saved_ledger_df.empty:
            sc_n = normalize_match_str(sc)
            sn_n = normalize_match_str(s_name_clean)
            for d in saved_ledger_df.to_dict(orient='records'):
                c_n = normalize_match_str(d.get("U_Retail店舗コード", ""))
                n_n = normalize_match_str(d.get("店舗名", ""))
                if (sc_n and c_n == sc_n) or (sn_n and n_n == sn_n):
                    saved_row = d
                    break

        raw_add_brands = saved_row.get("その他取扱ブランド", "")
        if isinstance(raw_add_brands, str): add_brand_list = [b.strip() for b in raw_add_brands.split(",") if b.strip()]
        elif isinstance(raw_add_brands, list): add_brand_list = raw_add_brands
        else: add_brand_list = []

        init_s = get_val(saved_row, "締日", shop_row.get("締め日1", "末日"))
        init_n = get_val(saved_row, "入金日", shop_row.get("入金日1", "末日"))
        init_shime = normalize_day(init_s)
        init_nyukin = normalize_day(init_n)

        def_cur_s = clean_str(rd.get("現契約開始日", rd.get("原契約開始日", shop_row.get("開店日", ""))))
        def_cur_e = clean_str(rd.get("現契約終了日", shop_row.get("閉店日", "")))
        
        default_app_type = "新規出店"
        default_parent_shop_name = ""
        
        my_addr = clean_str(shop_row.get("住所", ""))
        my_client = clean_str(shop_row.get("取引先コード", ""))

        if my_client and 'df' in globals() and df is not None and not df.empty:
            other_df = df[df.index != shop_row.name]
            s_c_df = other_df[other_df["取引先コード"].fillna("").astype(str).apply(clean_str) == my_client]
            if not s_c_df.empty:
                if my_addr:
                    m_addr = s_c_df[s_c_df["住所"].fillna("").astype(str).apply(clean_str) == my_addr]
                    if not m_addr.empty:
                        default_app_type = "ブランド追加"
                        default_parent_shop_name = clean_str(m_addr.iloc[0]["店舗名"])
                if default_app_type == "新規出店":
                    for _, r in s_c_df.iterrows():
                        opt_name = clean_str(r.get("店舗名", ""))
                        if opt_name and (opt_name in s_name_clean or s_name_clean in opt_name):
                            default_app_type = "ブランド追加"
                            default_parent_shop_name = opt_name
                            break

        shop_open_date = clean_str(shop_row.get("開店日", ""))
        shop_close_date = clean_str(shop_row.get("閉店日", ""))

        r_app_type = get_val(saved_row, "申請種別", default_app_type)
        raw_app_type_val = "更新・条件変更あり" if r_app_type == "条件変更" else r_app_type

        b_code = shop_row.get("ブランドコード", "")
        dept_name = get_master_label(b_code, "", brand_dict, clean_str) + "事業部"
        brand_name = get_master_label(b_code, "", brand_dict, clean_str)

        s_name = clean_str(shop_row.get("営業担当者名", ""))
        sales_p = get_val(saved_row, "所属長承認", s_name)
        담당 = get_val(saved_row, "担当者承認", s_name)

        if dname: agt_type = "販売代行"
        elif clean_str(shop_row.get("販売員", "")) == "社員": agt_type = "社員"
        else: agt_type = "その他"

        f_c = format_currency
        
        return {
            "U_Retail店舗コード": sc, "店舗名": s_name_clean, "販売形態": get_val(saved_row, "販売形態", d_trading),
            "店舗形態区分": get_val(saved_row, "店舗形態区分", d_store_format), "申請種別": raw_app_type_val,
            "申請ステータス": get_val(saved_row, "申請ステータス", "一時保存中"), "追加元店舗": get_val(saved_row, "追加元店舗", default_parent_shop_name),
            "部署名": dept_name, "申請日": datetime.now().strftime("令和 %Y年 %m月 %d日").replace("令和 2026年", "令和 8年"),
            "所属長承認": sales_p, "担当者承認": 담당, "取引会社コード": cc, "取引会社名": get_val(saved_row, "取引会社名", ""),
            "取引会社郵便番号": get_val(saved_row, "取引会社郵便番号", ""), "取引会社所在地": get_val(saved_row, "取引会社所在地", ""),
            "取引会社TEL": get_val(saved_row, "取引会社TEL", ""), "請求書送付先メールアドレス": get_val(saved_row, "請求書送付先メールアドレス", ""),
            "ブランド": brand_name, "その他取扱ブランド": add_brand_list, "店舗郵便番号": get_val(saved_row, "店舗郵便番号", clean_str(shop_row.get("郵便番号", ""))),
            "店舗所在地": get_val(saved_row, "店舗所在地", clean_str(shop_row.get("住所", ""))), "店舗TEL/FAX": get_val(saved_row, "店舗TEL/FAX", clean_str(shop_row.get("電話番号", ""))), 
            "出退店・変更理由": get_val(saved_row, "出退店・変更理由", clean_str(shop_row.get("備考", ""))), "開店日": get_val(saved_row, "開店日", shop_open_date),
            "閉店日": get_val(saved_row, "閉店日", shop_close_date), "原契約開始日": clean_str(rd.get("原契約開始日", "")), "現契約終了日": clean_str(rd.get("現契約終了日", "")),
            "締日": init_shime if init_shime else "末日", "入金日": init_nyukin if init_nyukin else "末日", 
            "初回納品日": get_val(saved_row, "初回納品日", shop_open_date), "初回納品額": get_val(saved_row, "初回納品額", ""),
            "賃貸借契約開始日": get_val(saved_row, "賃貸借契約開始日", def_cur_s), "賃貸借契約終了日": get_val(saved_row, "賃貸借契約終了日", def_cur_e),
            "変更後_賃貸借契約開始日": get_val(saved_row, "変更後_賃貸借契約開始日", ""), "変更後_賃貸借契約終了日": get_val(saved_row, "変更後_賃貸借契約終了日", ""),
            "面積": get_val(saved_row, "面積", clean_str(rd.get("面積", ""))), "レギュラーP掛率": clean_str(shop_row.get("P掛率", "")),
            "レギュラーS掛率": clean_str(shop_row.get("S掛率", "")), "セレクト/コラボP掛率": clean_str(shop_row.get("セレクト_コラボP掛率", fd.get("P手数料率", ""))),
            "セレクト/コラボS掛率": clean_str(shop_row.get("セレクト_コラボS掛率", fd.get("S手数料率", ""))),
            "変更後_レギュラーP掛率": get_val(saved_row, "変更後_レギュラーP掛率", clean_str(shop_row.get("変更後_Ｐ掛率", ""))),
            "変更後_レギュラーS掛率": get_val(saved_row, "変更後_レギュラーS掛率", clean_str(shop_row.get("変更後_Ｓ掛率", ""))),
            "変更後_セレクト/コラボP掛率": get_val(saved_row, "変更後_セレクト/コラボP掛率", ""), "変更後_セレクト/コラボS掛率": get_val(saved_row, "変更後_セレクト/コラボS掛率", ""),
            "固定賃料": get_val(saved_row, "固定賃料", f_c(rd.get("固定賃料", ""))), "最低保証賃料": get_val(saved_row, "最低保証賃料", f_c(rd.get("最低保証賃料", ""))),
            "基準売上高": get_val(saved_row, "基準売上高", f_c(rd.get("基準売上高1", ""))), "歩合料率": get_val(saved_row, "歩合料率", clean_str(rd.get("歩合料率1", ""))), 
            "変更後_固定賃料": get_val(saved_row, "変更後_固定賃料", f_c(rd.get("変更後_固定賃料", ""))), "変更後_最低保証賃料": get_val(saved_row, "変更後_最低保証賃料", f_c(rd.get("変更後_最低保証賃料", ""))),
            "変更後_基準売上高": get_val(saved_row, "変更後_基準売上高", f_c(rd.get("基準売上高1", ""))), "変更後_歩合料率": get_val(saved_row, "変更後_歩合料率", clean_str(rd.get("歩合料率1", ""))),
            "敷金_保証金": get_val(saved_row, "敷金_保証金", f_c(rd.get("敷金_保証金", ""))), "内装造作": get_val(saved_row, "内装造作", "有" if clean_str(rd.get("内装費", "")) else "無"),
            "販売代行先タイプ": get_val(saved_row, "販売代行先タイプ", agt_type), "販売代行コード": dcode, "販売代行名": get_val(saved_row, "販売代行名", agency_dict.get(dcode, "") if dcode else ""),
            "代行その他補足": get_val(saved_row, "代行その他補足", ""), "提出必要書類": get_val(saved_row, "提出必要書類", "・契約書 ・現在事項全部証明書(謄本) ・印鑑証明 ・図面 ・定款 ・口座申請書"),
            "備考/ユニケージコード": f"ユニケージ店舗コード: {sc}", "原状回復費用": get_val(saved_row, "原状回復費用", "")
        }

    tab_s, tab_b = st.tabs(["📄 単独店舗 台帳プレビュー＆出力", "📊 全店舗 台帳データ一括ダウンロード"])
    
    with tab_s:
        if df is not None and not df.empty:
            shop_list_display, shop_options_map = [""], {}
            for idx, r in df.iterrows():
                c = clean_str(r.get("U_Retail店舗コード", ""))
                n = clean_str(r.get("店舗名", ""))
                cp = c[:-2] if c.endswith('.0') else c
                label = f"{idx} : {cp} : {n}" if cp else f"{idx} : {n}"
                shop_list_display.append(label)
                shop_options_map[label] = idx

            sel_shop = st.selectbox("出力対象の店舗:", shop_list_display, key="sel_target_shop_main", on_change=on_ledger_shop_change)
            if sel_shop:
                target_idx_pos = shop_options_map[sel_shop]
                target_shop_row = df.loc[target_idx_pos]
                target_ledger = fetch_single_ledger_row(target_shop_row)
                
                s_code_val = clean_str(target_shop_row.get("U_Retail店舗コード", ""))
                s_name_val = clean_str(target_shop_row.get("店舗名", ""))
                target_code = f"CODE_{s_code_val}" if s_code_val else f"NAME_{target_idx_pos}_{s_name_val}"
                
                if "current_ledger_code" not in st.session_state or st.session_state["current_ledger_code"] != target_code:
                    st.session_state["current_ledger_code"] = target_code
                    st.session_state["form_reset_token"] = st.session_state.get("form_reset_token", 0) + 1
                    keys_to_delete = []
                    for k in st.session_state.keys():
                        if any(k.startswith(p) for p in ["in_", "sel_", "chk_"]) and k != "sel_target_shop_main":
                            keys_to_delete.append(k)
                    for k in keys_to_delete:
                        del st.session_state[k]
                    st.rerun()

                reset_token = st.session_state.get("form_reset_token", 0)
                col_top_btn, _ = st.columns([1, 2])
                
                if col_top_btn.button("🗑️ この店舗の一時保存をクリアして最新情報に戻す", key=f"clear_btn_{target_code}_{reset_token}"):
                    with st.spinner("強制リセットを実行しています..."):
                        try:
                            from data_manager import get_gspread_client
                            import gspread
                            from auth import SPREADSHEET_KEY
                            gc = get_gspread_client()
                            ws = gc.open_by_key(SPREADSHEET_KEY).worksheet("取引先台帳調整データ")
                            records = ws.get_all_values()
                            if len(records) > 1:
                                headers = records[0]
                                rows = records[1:]
                                c_del = normalize_match_str(s_code_val)
                                n_del = normalize_match_str(s_name_val)
                                new_rows = []
                                for r_data in rows:
                                    rd = dict(zip(headers, r_data))
                                    c_v = normalize_match_str(str(rd.get("U_Retail店舗コード", "")))
                                    n_v = normalize_match_str(str(rd.get("店舗名", "")))
                                    if (c_del and c_v == c_del) or (n_del and n_v == n_del):
                                        continue
                                    new_rows.append(r_data)
                                ws.clear()
                                if new_rows:
                                    ws.update([headers] + new_rows, "A1")
                                else:
                                    ws.update([headers], "A1")
                            from data_manager import fetch_raw_data
                            fetch_raw_data.clear()
                            st.cache_data.clear()
                            st.session_state["form_reset_token"] = reset_token + 1
                            keys_to_delete = []
                            for k in st.session_state.keys():
                                if any(k.startswith(p) for p in ["in_", "sel_", "chk_"]) and k != "sel_target_shop_main":
                                    keys_to_delete.append(k)
                            for k in keys_to_delete:
                                del st.session_state[k]
                            st.success("✨ ゴミデータを完全に削除し、マスタの情報でリセットしました！")
                            time.sleep(1.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ リセット処理に失敗しました: {e}")

                c_f1, c_f2, c_f3 = st.columns(3)
                with c_f1:
                    def_trad = target_ledger['販売形態']
                    idx_trad = TRADING_TYPE_OPTIONS.index(def_trad) if def_trad in TRADING_TYPE_OPTIONS else 0
                    sel_trading = st.selectbox("販売形態", TRADING_TYPE_OPTIONS, index=idx_trad, key=f"sel_trading_{target_code}_{reset_token}")
                    
                    def_sf = target_ledger.get('店舗形態区分', '実店舗')
                    idx_sf = STORE_FORMAT_OPTIONS.index(def_sf) if def_sf in STORE_FORMAT_OPTIONS else 0
                    sel_store_format = st.selectbox("店舗形態", STORE_FORMAT_OPTIONS, index=idx_sf, key=f"sel_store_format_{target_code}_{reset_token}")
                    
                    def_at = target_ledger['申請種別']
                    idx_at = APPLICATION_TYPE_OPTIONS.index(def_at) if def_at in APPLICATION_TYPE_OPTIONS else 0
                    sel_app_type = st.selectbox("申請種別", APPLICATION_TYPE_OPTIONS, index=idx_at, key=f"sel_app_type_{target_code}_{reset_token}")
                    
                    is_locked = False
                    if sel_app_type == "新規出店" and target_shop_row.get("BHD承認ステータス", "") not in ["取締役会承認済", "不要"]:
                        is_locked = True
                        st.error("🔒 **【内部統制ロック】** 親会社(BHD)の取締役会承認が完了していないため、新規出店に伴う台帳の作成・保存はできません。")
                    
                    sel_parent_shop, parent_ledger_info = "", {}
                    if sel_app_type == "ブランド追加":
                        other_shop_opts = [""] + [s for s in shop_list_display if s != sel_shop]
                        cur_p_shop = target_ledger.get("追加元店舗", "")
                        selected_opt = ""
                        if cur_p_shop:
                            for opt in other_shop_opts:
                                if opt.split(" : ")[-1].strip() == cur_p_shop:
                                    selected_opt = opt
                                    break
                            if not selected_opt:
                                for opt in other_shop_opts:
                                    if cur_p_shop in opt:
                                        selected_opt = opt
                                        break
                        idx_ps = other_shop_opts.index(selected_opt) if selected_opt in other_shop_opts else 0
                        sel_parent_shop = st.selectbox("追加元の既存店舗", other_shop_opts, index=idx_ps, key=f"sel_parent_shop_{target_code}_{reset_token}", disabled=is_locked)
                        if sel_parent_shop:
                            p_idx = shop_options_map[sel_parent_shop]
                            parent_ledger_info = fetch_single_ledger_row(df.loc[p_idx])

                    all_brand_opts = [b for b in BRAND_OPTIONS if b]
                    cur_add_b = parent_ledger_info.get("その他取扱ブランド", target_ledger.get("その他取扱ブランド", []))
                    val_add_b = [b for b in cur_add_b if b in all_brand_opts]
                    sel_add_brands = st.multiselect("その他取扱ブランド", all_brand_opts, default=val_add_b, key=f"sel_add_brands_{target_code}_{reset_token}", disabled=is_locked)

                    if sel_app_type == "新規出店":
                        def_int = parent_ledger_info.get("内装造作", target_ledger['内装造作'])
                        curr_int = def_int.replace("(※店舗内装造作届要添付)", "").strip()
                        if curr_int not in INTERIOR_OPTIONS: curr_int = INTERIOR_OPTIONS[0]
                        idx_int = INTERIOR_OPTIONS.index(curr_int)
                        sel_interior = st.selectbox("内装造作", INTERIOR_OPTIONS, index=idx_int, key=f"sel_int_{target_code}_{reset_token}", disabled=is_locked)
                    else:
                        sel_interior = ""
                    
                    v_cn = target_ledger.get('取引会社名', '')
                    in_client_name = st.text_input("取引会社名", value=v_cn, key=f"in_cn_{target_code}_{reset_token}", disabled=is_locked)
                    
                    v_cz = target_ledger.get('取引会社郵便番号', '')
                    in_client_zip = st.text_input("取引会社 郵便番号", value=v_cz, key=f"in_cz_{target_code}_{reset_token}", disabled=is_locked)
                    
                    v_ca = target_ledger.get('取引会社所在地', '')
                    in_client_addr = st.text_input("取引会社所在地", value=v_ca, key=f"in_ca_{target_code}_{reset_token}", disabled=is_locked)
                    
                    v_ct = target_ledger.get('取引会社TEL', '')
                    in_client_tel = st.text_input("取引会社TEL", value=v_ct, key=f"in_ct_{target_code}_{reset_token}", disabled=is_locked)
                    
                    v_ce = parent_ledger_info.get('請求書送付先メールアドレス', target_ledger.get('請求書送付先メールアドレス', ''))
                    in_invoice_email = st.text_input("請求書メール", value=v_ce, key=f"in_ce_{target_code}_{reset_token}", disabled=is_locked)
                    
                    v_sn = target_ledger['店舗名']
                    in_shop_name = st.text_input("店舗名", value=v_sn, key=f"in_sn_{target_code}_{reset_token}", disabled=is_locked)
                    
                    v_sz = target_ledger.get('店舗郵便番号', '')
                    in_shop_zip = st.text_input("店舗郵便番号", value=v_sz, key=f"in_sz_{target_code}_{reset_token}", disabled=is_locked)
                    
                    v_sa = target_ledger.get('店舗所在地', '')
                    in_shop_addr = st.text_input("店舗所在地", value=v_sa, key=f"in_sa_{target_code}_{reset_token}", disabled=is_locked)
                    
                    v_st = target_ledger.get('店舗TEL/FAX', '')
                    in_shop_tel = st.text_input("店舗TEL", value=v_st, key=f"in_st_{target_code}_{reset_token}", disabled=is_locked)

                    v_ar = parent_ledger_info.get('面積', target_ledger.get('面積', ''))
                    in_area = st.text_input("面積(㎡)", value=v_ar, key=f"in_ar_{target_code}_{reset_token}", disabled=is_locked)
                    
                    v_rs = target_ledger['出退店・変更理由']
                    in_reason = st.text_area("出退店理由", value=v_rs, height=80, key=f"in_rs_{target_code}_{reset_token}", disabled=is_locked)
                
                with c_f2:
                    def_agy = parent_ledger_info.get('販売代行先タイプ', target_ledger['販売代行先タイプ'])
                    idx_agy = AGENCY_TYPE_OPTIONS.index(def_agy) if def_agy in AGENCY_TYPE_OPTIONS else 1
                    sel_agency_type = st.selectbox("代行先区分", AGENCY_TYPE_OPTIONS, index=idx_agy, key=f"sel_agy_{target_code}_{reset_token}", disabled=is_locked)
                    
                    sel_daiko_name, in_agency_other_comment = "", ""
                    if sel_agency_type == "販売代行":
                        cur_d = get_master_label(parent_ledger_info.get('販売代行コード', target_ledger['販売代行コード']), parent_ledger_info.get('販売代行名', target_ledger['販売代行名']), agency_dict, clean_str)
                        safe_agy_opts = get_safe_options(AGENCY_OPTIONS, cur_d)
                        idx_s_d = safe_agy_opts.index(cur_d) if cur_d in safe_agy_opts else 0
                        s_daiko = st.selectbox("販売代行名 🔍", safe_agy_opts, index=idx_s_d, key=f"s_daiko_{target_code}_{reset_token}", disabled=is_locked)
                        sel_daiko_name = agency_dict.get(split_code_label(s_daiko), parent_ledger_info.get('販売代行名', target_ledger['販売代行名']))
                    elif sel_agency_type == "その他":
                        v_oc = parent_ledger_info.get('代行その他補足', target_ledger.get('代行その他補足', ''))
                        in_agency_other_comment = st.text_input("代行補足", value=v_oc, key=f"in_oc_{target_code}_{reset_token}", disabled=is_locked)
                    
                    raw_sm = parent_ledger_info.get('締日', target_ledger['締日'])
                    raw_nk = parent_ledger_info.get('入金日', target_ledger['入金日'])
                    def_sm = normalize_day(raw_sm) if normalize_day(raw_sm) in DAY_OPTIONS_FULL else "末日"
                    def_nk = normalize_day(raw_nk) if normalize_day(raw_nk) in DAY_OPTIONS_FULL else "末日"
                    
                    sel_shime = st.selectbox("締め日", DAY_OPTIONS_FULL, index=DAY_OPTIONS_FULL.index(def_sm), key=f"sel_sm_{target_code}_{reset_token}", disabled=is_locked)
                    sel_nyukin = st.selectbox("入金日", DAY_OPTIONS_FULL, index=DAY_OPTIONS_FULL.index(def_nk), key=f"sel_nk_{target_code}_{reset_token}", disabled=is_locked)
                    
                    if sel_app_type in ["新規出店", "ブランド追加"]:
                        v_od = parse_date(target_ledger.get('開店日', ''))
                        in_open_date = st.date_input("開店日", value=v_od, key=f"in_od_{target_code}_{reset_token}", disabled=is_locked)
                    else:
                        in_open_date = None
                        
                    if sel_app_type == "退店":
                        v_cd = parse_date(target_ledger.get('閉店日', ''))
                        in_close_date = st.date_input("閉店日", value=v_cd, key=f"in_cd_{target_code}_{reset_token}", disabled=is_locked)
                    else:
                        in_close_date = None

                    if sel_trading == "卸売" and sel_app_type in ["新規出店", "ブランド追加"]:
                        v_fd = parse_date(target_ledger.get('初回納品日', ''))
                        in_first_del = st.date_input("初回納品日", value=v_fd, key=f"in_fd_{target_code}_{reset_token}", disabled=is_locked)
                        v_fda = format_currency(target_ledger.get('初回納品額', ''))
                        in_first_del_amount = st.text_input("初回納品額(円)", value=v_fda, key=f"in_fda_{target_code}_{reset_token}", disabled=is_locked)
                    else:
                        in_first_del, in_first_del_amount = None, ""
                        
                    if sel_app_type == "退店":
                        v_rc = format_currency(target_ledger.get('原状回復費用', ''))
                        in_restoration_cost = st.text_input("回復費用(円)", value=v_rc, key=f"in_rc_{target_code}_{reset_token}", disabled=is_locked)
                    else:
                        in_restoration_cost = ""

                    v_rs = parse_date(parent_ledger_info.get('賃貸借契約開始日', target_ledger['賃貸借契約開始日']))
                    v_re = parse_date(parent_ledger_info.get('賃貸借契約終了日', target_ledger['賃貸借契約終了日']))
                    in_rent_start = st.date_input("契約開始日", value=v_rs, key=f"in_rs_dt_{target_code}_{reset_token}", disabled=is_locked)
                    in_rent_end = st.date_input("契約終了日", value=v_re, key=f"in_re_dt_{target_code}_{reset_token}", disabled=is_locked)

                    if sel_app_type in ["更新・条件変更あり", "更新・条件変更なし"]:
                        st.write("🔄 **変更後（更新後）の契約期間**")
                        lbl_s = "変更適用日" if sel_app_type == "更新・条件変更あり" else "更新後 契約開始日"
                        v_nrs = parse_date(target_ledger.get('変更後_賃貸借契約開始日', ''))
                        v_nre = parse_date(target_ledger.get('変更後_賃貸借契約終了日', ''))
                        in_next_rent_start = st.date_input(lbl_s, value=v_nrs, key=f"in_nrs_{target_code}_{reset_token}", disabled=is_locked)
                        in_next_rent_end = st.date_input("更新後 契約終了日", value=v_nre, key=f"in_nre_{target_code}_{reset_token}", disabled=is_locked)
                    else:
                        in_next_rent_start, in_next_rent_end = None, None

                    if sel_app_type == "更新・条件変更あり":
                        st.write("🔄 **変更後の掛率情報**")
                        v_nrp = target_ledger.get('変更後_レギュラーP掛率', '')
                        v_nrs_r = target_ledger.get('変更後_レギュラーS掛率', '')
                        v_nsp = target_ledger.get('変更後_セレクト/コラボP掛率', '')
                        v_nss = target_ledger.get('変更後_セレクト/コラボS掛率', '')
                        in_next_reg_p = st.text_input("変更後 レギュラーP", value=v_nrp, key=f"in_nrp_{target_code}_{reset_token}", disabled=is_locked)
                        in_next_reg_s = st.text_input("変更後 レギュラーS", value=v_nrs_r, key=f"in_nrs_r_{target_code}_{reset_token}", disabled=is_locked)
                        in_next_sel_p = st.text_input("変更後 セレクトP", value=v_nsp, key=f"in_nsp_{target_code}_{reset_token}", disabled=is_locked)
                        in_next_sel_s = st.text_input("変更後 セレクトS", value=v_nss, key=f"in_nss_{target_code}_{reset_token}", disabled=is_locked)
                    else:
                        in_next_reg_p, in_next_reg_s, in_next_sel_p, in_next_sel_s = "", "", "", ""

                    if "直営" in sel_trading:
                        st.write("🏢 **賃借条件＆敷金保証金入力**")
                        v_fr = format_currency(parent_ledger_info.get('固定賃料', target_ledger.get('固定賃料', '')))
                        v_mg = format_currency(parent_ledger_info.get('最低保証賃料', target_ledger.get('最低保証賃料', '')))
                        v_bs = format_currency(parent_ledger_info.get('基準売上高', target_ledger.get('基準売上高', '')))
                        v_tr = parent_ledger_info.get('歩合料率', target_ledger.get('歩合料率', ''))
                        v_dp = format_currency(parent_ledger_info.get('敷金_保証金', target_ledger.get('敷金_保証金', '')))
                        
                        in_fixed_rent = st.text_input("固定賃料(円)", value=v_fr, key=f"in_fr_{target_code}_{reset_token}", disabled=is_locked)
                        in_min_guarantee = st.text_input("最低保証賃料(円)", value=v_mg, key=f"in_mg_{target_code}_{reset_token}", disabled=is_locked)
                        in_base_sales = st.text_input("基準売上高(円)", value=v_bs, key=f"in_bs_{target_code}_{reset_token}", disabled=is_locked)
                        in_turnover_rate = st.text_input("歩合料率", value=v_tr, key=f"in_tr_{target_code}_{reset_token}", disabled=is_locked)
                        in_deposit_val = st.text_input("敷金・保証金(円)", value=v_dp, key=f"in_dp_{target_code}_{reset_token}", disabled=is_locked)
                        
                        if sel_app_type == "更新・条件変更あり":
                            st.write("🔄 **変更後の賃借条件**")
                            v_nfr = format_currency(target_ledger.get('変更後_固定賃料', ''))
                            v_nmg = format_currency(target_ledger.get('変更後_最低保証賃料', ''))
                            v_nbs = format_currency(target_ledger.get('変更後_基準売上高', ''))
                            v_ntr = target_ledger.get('変更後_歩合料率', '')
                            
                            in_next_fixed_rent = st.text_input("変更後 固定賃料", value=v_nfr, key=f"in_nfr_{target_code}_{reset_token}", disabled=is_locked)
                            in_next_min_guarantee = st.text_input("変更後 最低保証賃料", value=v_nmg, key=f"in_nmg_{target_code}_{reset_token}", disabled=is_locked)
                            in_next_base_sales = st.text_input("変更後 基準売上高", value=v_nbs, key=f"in_nbs_{target_code}_{reset_token}", disabled=is_locked)
                            in_next_turnover_rate = st.text_input("変更後 歩合料率", value=v_ntr, key=f"in_ntr_{target_code}_{reset_token}", disabled=is_locked)
                        else:
                            in_next_fixed_rent, in_next_min_guarantee, in_next_base_sales, in_next_turnover_rate = "", "", "", ""
                    else:
                        in_fixed_rent, in_min_guarantee, in_base_sales, in_turnover_rate, in_deposit_val = "", "", "", "", ""
                        in_next_fixed_rent, in_next_min_guarantee, in_next_base_sales, in_next_turnover_rate = "", "", "", ""

                with c_f3:
                    st.write("📋 **申請ステータス**")
                    default_status = target_ledger.get('申請ステータス', '一時保存中')
                    if default_status not in APPLICATION_STATUS_OPTIONS:
                        default_status = '一時保存中'
                    idx_stat = APPLICATION_STATUS_OPTIONS.index(default_status)
                    sel_app_status = st.selectbox("ステータス", APPLICATION_STATUS_OPTIONS, index=idx_stat, key=f"sel_stat_{target_code}_{reset_token}", disabled=is_locked)
                    
                    st.markdown("---")
                    if sel_app_type == "新規出店":
                        st.write("📋 **提出必要書類**")
                        curr_docs = parent_ledger_info.get('提出必要書類', target_ledger['提出必要書類'])
                        chk_c = st.checkbox("契約書", value="契約書" in curr_docs, key=f"chk_c_{target_code}_{reset_token}", disabled=is_locked)
                        chk_co = st.checkbox("現在事項全部証明書", value="現在事項全部証明書" in curr_docs, key=f"chk_co_{target_code}_{reset_token}", disabled=is_locked)
                        chk_s = st.checkbox("印鑑証明", value="印鑑証明" in curr_docs, key=f"chk_s_{target_code}_{reset_token}", disabled=is_locked)
                        chk_d = st.checkbox("図面", value="図面" in curr_docs, key=f"chk_d_{target_code}_{reset_token}", disabled=is_locked)
                        chk_a = st.checkbox("定款", value="定款" in curr_docs, key=f"chk_a_{target_code}_{reset_token}", disabled=is_locked)
                        chk_b = st.checkbox("口座申請書", value="口座申請書" in curr_docs, key=f"chk_b_{target_code}_{reset_token}", disabled=is_locked)
                        
                        s_docs = []
                        if chk_c: s_docs.append("・契約書")
                        if chk_co: s_docs.append("・現在事項全部証明書(謄本)")
                        if chk_s: s_docs.append("・印鑑証明")
                        if chk_d: s_docs.append("・図面")
                        if chk_a: s_docs.append("・定款")
                        if chk_b: s_docs.append("・口座申請書")
                        docs_text = " ".join(s_docs)
                    else:
                        docs_text = ""

                if not is_locked:
                    col_save, _ = st.columns([1, 1])
                    with col_save:
                        btn_label = "💾 台帳調整内容を保存 ＆ マスタに変更予定を自動連動させる" if sel_app_type == "更新・条件変更あり" else "💾 台帳調整内容を保存する"
                        if st.button(btn_label, type="primary", use_container_width=True, key=f"btn_save_{target_code}_{reset_token}"):
                            new_save_row = {
                                "U_Retail店舗コード": target_ledger['U_Retail店舗コード'],
                                "店舗名": in_shop_name.strip() if in_shop_name.strip() else target_ledger['店舗名'],
                                "店舗郵便番号": format_postal_code(in_shop_zip.strip()) if in_shop_zip.strip() else target_ledger.get('店舗郵便番号', ''),
                                "店舗所在地": in_shop_addr.strip() if in_shop_addr.strip() else target_ledger.get('店舗所在地', ''),
                                "店舗TEL/FAX": in_shop_tel.strip() if in_shop_tel.strip() else target_ledger.get('店舗TEL/FAX', ''),
                                "販売形態": sel_trading,
                                "店舗形態区分": sel_store_format,
                                "申請種別": sel_app_type,
                                "申請ステータス": sel_app_status,
                                "追加元店舗": sel_parent_shop,
                                "その他取扱ブランド": ",".join(sel_add_brands),
                                "取引会社名": in_client_name,
                                "取引会社郵便番号": format_postal_code(in_client_zip),
                                "取引会社所在地": in_client_addr,
                                "取引会社TEL": in_client_tel,
                                "請求書送付先メールアドレス": in_invoice_email,
                                "出退店・変更理由": in_reason,
                                "開店日": in_open_date.strftime("%Y-%m-%d") if in_open_date else "",
                                "閉店日": in_close_date.strftime("%Y-%m-%d") if in_close_date else "",
                                "締日": sel_shime,
                                "入金日": sel_nyukin,
                                "初回納品日": in_first_del.strftime("%Y-%m-%d") if in_first_del else "",
                                "初回納品額": format_currency(in_first_del_amount),
                                "原状回復費用": format_currency(in_restoration_cost) if sel_app_type == "退店" else "",
                                "賃貸借契約開始日": in_rent_start.strftime("%Y-%m-%d") if in_rent_start else "",
                                "賃貸借契約終了日": in_rent_end.strftime("%Y-%m-%d") if in_rent_end else "",
                                "変更後_賃貸借契約開始日": in_next_rent_start.strftime("%Y-%m-%d") if in_next_rent_start else "",
                                "変更後_賃貸借契約終了日": in_next_rent_end.strftime("%Y-%m-%d") if in_next_rent_end else "",
                                "変更後_レギュラーP掛率": in_next_reg_p,
                                "変更後_レギュラーS掛率": in_next_reg_s,
                                "変更後_セレクト/コラボP掛率": in_next_sel_p,
                                "変更後_セレクト/コラボS掛率": in_next_sel_s,
                                "面積": in_area if sel_trading != "卸売" else "",
                                "固定賃料": format_currency(in_fixed_rent),
                                "最低保証賃料": format_currency(in_min_guarantee),
                                "基準売上高": format_currency(in_base_sales),
                                "歩合料率": in_turnover_rate,
                                "変更後_固定賃料": format_currency(in_next_fixed_rent),
                                "変更後_最低保証賃料": format_currency(in_next_min_guarantee),
                                "変更後_基準売上高": format_currency(in_next_base_sales),
                                "変更後_歩合料率": in_next_turnover_rate,
                                "敷金_保証金": format_currency(in_deposit_val),
                                "内装造作": str(sel_interior) + (" (※店舗内装造作届要添付)" if sel_interior == "有" else "") if sel_interior else "",
                                "販売代行先タイプ": sel_agency_type,
                                "販売代行名": sel_daiko_name,
                                "代行その他補足": in_agency_other_comment,
                                "提出必要書類": docs_text,
                                "更新日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            
                            s_ledger_df = all_dfs.get("取引先台帳調整データ", pd.DataFrame())
                            if s_ledger_df.empty:
                                s_ledger_df = pd.DataFrame([new_save_row])
                            else:
                                c_del = normalize_match_str(new_save_row['U_Retail店舗コード'])
                                n_del = normalize_match_str(new_save_row['店舗名'])
                                
                                def should_keep_save(r):
                                    c = normalize_match_str(str(r.get("U_Retail店舗コード", "")))
                                    n = normalize_match_str(str(r.get("店舗名", "")))
                                    if (c_del and c == c_del) or (n_del and n == n_del):
                                        return False
                                    return True
                                
                                kept_records = [r for r in s_ledger_df.to_dict(orient="records") if should_keep_save(r)]
                                kept_records.append(new_save_row)
                                s_ledger_df = pd.DataFrame(kept_records)
                            
                            save_targets = ["取引先台帳調整データ"]
                            
                            if sel_app_type == "更新・条件変更あり":
                                df.at[target_idx_pos, "掛率変更予定日"] = in_next_rent_start.strftime("%Y-%m-%d") if in_next_rent_start else ""
                                df.at[target_idx_pos, "変更後_Ｐ掛率"] = in_next_reg_p.strip()
                                df.at[target_idx_pos, "変更後_Ｓ掛率"] = in_next_reg_s.strip()
                                save_targets.append("店舗")
                                df_history = add_history(df_history, "自動連動", "店舗", target_ledger['U_Retail店舗コード'], disp_shop_name, "台帳画面から条件変更予定を自動予約")
                                
                                r_code = clean_code_7digits(target_shop_row.get("家賃計上部門コード", ""))
                                if r_code and df_rent is not None and not df_rent.empty:
                                    r_match = df_rent[df_rent["家賃計上部門コード"].apply(clean_code_7digits) == r_code]
                                    if not r_match.empty:
                                        r_idx = r_match.index[0]
                                        df_rent.at[r_idx, "変更予定日"] = in_next_rent_start.strftime("%Y-%m-%d") if in_next_rent_start else ""
                                        df_rent.at[r_idx, "変更後_固定賃料"] = format_currency(in_next_fixed_rent)
                                        df_rent.at[r_idx, "変更後_最低保証賃料"] = format_currency(in_next_min_guarantee)
                                        df_rent.at[r_idx, "変更後_基準売上高1"] = format_currency(in_next_base_sales)
                                        df_rent.at[r_idx, "変更後_歩合料率1"] = in_next_turnover_rate.strip()
                                        save_targets.append("家賃条件")
                                        df_history = add_history(df_history, "自動連動", "家賃条件", r_code, disp_shop_name, "台帳画面から条件変更予定を自動予約")
                                
                                all_dfs["変更履歴"] = df_history
                                save_targets.append("変更履歴")

                            all_dfs["取引先台帳調整データ"] = s_ledger_df
                            if save_all_data(all_dfs, target_sheets=save_targets):
                                if sel_app_type == "新規出店":
                                    to_email = get_all_acc_emails(acc_dict)
                                else:
                                    to_email = target_shop_row.get("売上管理担当者メールアドレス", "").strip()
                                    if not to_email:
                                        to_email = get_all_acc_emails(acc_dict)
                                        
                                mail_body = "経理担当者様\n\nシステムにて取引先台帳（申請書）のデータが作成・更新されました。\n内容をご確認ください。\n\n※LMC店舗DBより自動送信"
                                send_notification_email(to_email, "【LMC店舗DB】取引先台帳申請データ作成・更新のお知らせ", mail_body)
                                st.success("✨ 台帳入力内容とマスタ連動設定を保存しました！")
                                st.rerun()

                    if sel_agency_type == "販売代行" and sel_daiko_name:
                        agency_disp_text = "販売代行 (代行名: " + str(sel_daiko_name) + ")"
                    elif sel_agency_type == "その他" and in_agency_other_comment:
                        agency_disp_text = "その他 (" + str(in_agency_other_comment) + ")"
                    else:
                        agency_disp_text = sel_agency_type

                    disp_open_date = in_open_date.strftime("%Y-%m-%d") if in_open_date else ""
                    disp_close_date = in_close_date.strftime("%Y-%m-%d") if in_close_date else ""
                    disp_shop_name = in_shop_name.strip() if in_shop_name.strip() else target_ledger['店舗名']
                    disp_shop_zip = format_postal_code(in_shop_zip.strip()) if in_shop_zip.strip() else target_ledger.get('店舗郵便番号', '')
                    disp_shop_addr = in_shop_addr.strip() if in_shop_addr.strip() else target_ledger.get('店舗所在地', '')
                    disp_shop_tel = in_shop_tel.strip() if in_shop_tel.strip() else target_ledger.get('店舗TEL/FAX', '')

                    main_brand_str = target_ledger['ブランド']
                    add_brands_str = ""
                    if sel_add_brands:
                        br_list = "<br>".join(["・" + str(b) for b in sel_add_brands])
                        add_brands_str = f"<br><div style='font-size: 11.5px; color: #333; background-color: #f0f4f8; padding: 4px 8px; border-radius: 4px; margin-top: 4px;'><b>他取扱ブランド:</b><br>{br_list}</div>"
                    
                    disp_brand_full = f"<b>{main_brand_str}</b>{add_brands_str}"

                    trading_items = []
                    for t_opt in ["売仕", "卸売", "直営"]:
                        if (t_opt == "売仕" and sel_trading == "売仕") or (t_opt == "卸売" and sel_trading == "卸売") or (t_opt == "直営" and "直営" in sel_trading):
                            trading_items.append(f"<span style='background-color: #ffebee; border: 1.5px solid #c62828; padding: 1px 4px; border-radius: 3px; color: #c62828; font-weight: bold;'>✓ {t_opt}</span>")
                        else:
                            trading_items.append(f"<span style='color: #a0a0a0;'>{t_opt}</span>")
                    
                    st_m = "1. デベロッパー" if sel_trading == "直営_デベロッパー" else ("2. 路面店" if sel_trading == "直営_路面店" else "")
                    st_m_html = f" <span style='font-size: 11px; color: #c62828; font-weight: bold;'>({st_m})</span>" if st_m else ""
                    trading_fmt = f"[{' '.join(trading_items)}{st_m_html}]"

                    store_format_items = []
                    for sf_opt in ["実店舗", "EC", "催事"]:
                        if sf_opt == sel_store_format:
                            store_format_items.append(f"<span style='background-color: #e8f5e9; border: 1.5px solid #2e7d32; padding: 1px 4px; border-radius: 3px; color: #2e7d32; font-weight: bold;'>✓ {sf_opt}</span>")
                        else:
                            store_format_items.append(f"<span style='color: #a0a0a0;'>{sf_opt}</span>")
                    store_format_fmt = f"[{' '.join(store_format_items)}]"

                    app_items = []
                    for a_opt in ["新規出店", "更新・条件変更あり", "更新・条件変更なし", "退店", "ブランド追加"]:
                        if a_opt == sel_app_type:
                            app_items.append(f"<span style='background-color: #e3f2fd; border: 1.5px solid #1565c0; padding: 1px 4px; border-radius: 3px; color: #1565c0; font-weight: bold;'>✓ {a_opt}</span>")
                        else:
                            app_items.append(f"<span style='color: #a0a0a0;'>{a_opt}</span>")
                    
                    p_shop_html = f"<br><span style='font-size: 11px; color: #1565c0; font-weight: bold;'>(追加元店舗: {sel_parent_shop})</span>" if sel_app_type == "ブランド追加" and sel_parent_shop else ""
                    app_fmt = f"[{' '.join(app_items)}{p_shop_html}]"

                    s_fd = in_first_del.strftime("%Y-%m-%d") if in_first_del else ""
                    s_rs = in_rent_start.strftime("%Y-%m-%d") if in_rent_start else ""
                    s_re = in_rent_end.strftime("%Y-%m-%d") if in_rent_end else ""
                    s_next_rs = in_next_rent_start.strftime("%Y-%m-%d") if in_next_rent_start else ""
                    s_next_re = in_next_rent_end.strftime("%Y-%m-%d") if in_next_rent_end else ""

                    period_label_name = "賃貸借契約期間" if "直営" in sel_trading else "契約期間"
                    shime_disp = str(sel_shime).replace("日", "日締") if sel_shime and "締" not in str(sel_shime) else str(sel_shime) if sel_shime else ""
                    nyukin_disp = ("翌月" + str(sel_nyukin) + "入金") if sel_nyukin else ""
                    shime_nyukin_str = (shime_disp + " / " + nyukin_disp).strip(" /")
                    
                    oc_cells = []
                    if sel_app_type in ["新規出店", "ブランド追加"]:
                        oc_cells.append(f"<th style='width: 15%;'>開店日</th><td>{disp_open_date}</td>")
                    elif sel_app_type == "退店":
                        oc_cells.append(f"<th style='width: 15%;'>閉店日</th><td>{disp_close_date}</td>")
                    oc_cells.append("<th style='width: 15%;'>締日/入金日</th>")
                    if len(oc_cells) == 2:
                        oc_cells.append(f"<td>{shime_nyukin_str}</td>")
                    elif len(oc_cells) == 1:
                        oc_cells.append(f"<td colspan='3'>{shime_nyukin_str}</td>")
                    else:
                        oc_cells.append(f"<td colspan='5'>{shime_nyukin_str}</td>")

                    open_close_row_html = f"<tr>{''.join(oc_cells)}</tr>"
                    
                    first_del_row_html = ""
                    if sel_trading == "卸売" and sel_app_type in ["新規出店", "ブランド追加"]:
                        first_del_row_html = f"<tr><th>初回納品日 / 初回納品額</th><td colspan='5'>{s_fd} &nbsp;&nbsp;&nbsp;&nbsp; <b>【初回納品額】</b> {format_currency(in_first_del_amount)} 円</td></tr>"
                        
                    restoration_cost_row_html = ""
                    if sel_app_type == "退店":
                        restoration_cost_row_html = f"<tr><th>原状回復費用</th><td colspan='5'>{format_currency(in_restoration_cost)} 円</td></tr>"
                        
                    interior_row_html = ""
                    if sel_app_type == "新規出店":
                        int_note = "<span style='color: red; font-weight: bold; font-size: 11px;'>※「店舗内装造作届」を一緒に提出して下さい。</span>" if sel_interior == "有" else ""
                        interior_row_html = f"<tr><th>内装造作</th><td colspan='5'>1.有 &nbsp;&nbsp; 2.無 &nbsp;&nbsp;&nbsp;&nbsp; <b>【選択: {sel_interior}】</b> &nbsp;&nbsp; {int_note}</td></tr>"
                        
                    docs_html = ""
                    if sel_app_type == "新規出店":
                        docs_html = f"<p style='font-size: 11.5px; margin: 5px 0;'><b>■ 提出必要書類：</b> {docs_text}</p>"
                    
                    rent_period_row_html = ""
                    if sel_app_type in ["更新・条件変更あり", "更新・条件変更なし"] and (s_next_rs or s_next_re):
                        label_update = "【変更後】" if sel_app_type == "更新・条件変更あり" else "【更新後】"
                        rent_period_row_html = (
                            f"<tr><th>{period_label_name}</th><td colspan='5'><b>【変更前】</b> {s_rs} 〜 {s_re} "
                            f"&nbsp;&nbsp;&nbsp; ➔ &nbsp;&nbsp;&nbsp;<b style='color: #c62828;'>{label_update}</b> "
                            f"<span style='color: #c62828; font-weight: bold;'>{s_next_rs} 〜 {s_next_re}</span></td></tr>"
                        )
                    else:
                        if (s_rs or s_re): rent_period_row_html = f"<tr><th>{period_label_name}</th><td colspan='5'>{s_rs} &nbsp;〜&nbsp; {s_re}</td></tr>"

                    rates_row_html = ""
                    if sel_app_type == "更新・条件変更あり" and (in_next_reg_p or in_next_reg_s or in_next_sel_p or in_next_sel_s):
                        rates_row_html = (
                            f"<tr><th>レギュラーP掛率</th><td><b>[前]</b> {target_ledger['レギュラーP掛率']}% &nbsp;➔&nbsp; <b style='color: #c62828;'>[後] {in_next_reg_p}%</b></td>"
                            f"<th>レギュラーS掛率</th><td colspan='3'><b>[前]</b> {target_ledger['レギュラーS掛率']}% &nbsp;➔&nbsp; <b style='color: #c62828;'>[後] {in_next_reg_s}%</b></td></tr>"
                            f"<tr><th>セレクト/コラボP掛率</th><td><b>[前]</b> {target_ledger['セレクト/コラボP掛率']}% &nbsp;➔&nbsp; <b style='color: #c62828;'>[後] {in_next_sel_p}%</b></td>"
                            f"<th>セレクト/コラボS掛率</th><td colspan='3'><b>[前]</b> {target_ledger['セレクト/コラボS掛率']}% &nbsp;➔&nbsp; <b style='color: #c62828;'>[後] {in_next_sel_s}%</b></td></tr>"
                        )
                    else:
                        rates_row_html = (
                            f"<tr><th>レギュラーP掛率</th><td>{target_ledger['レギュラーP掛率']} %</td><th>レギュラーS掛率</th><td colspan='3'>{target_ledger['レギュラーS掛率']} %</td></tr>"
                            f"<tr><th>セレクト/コラボP掛率</th><td>{target_ledger['セレクト/コラボP掛率']} %</td><th>セレクト/コラボS掛率</th><td colspan='3'>{target_ledger['セレクト/コラボS掛率']} %</td></tr>"
                        )

                    rent_conditions_row_html, deposit_row_html = "", ""
                    if "直営" in sel_trading:
                        if sel_app_type == "更新・条件変更あり" and (in_next_fixed_rent or in_next_min_guarantee or in_next_base_sales or in_next_turnover_rate):
                            rent_conditions_row_html = (
                                f"<tr><th rowspan='2' style='vertical-align: middle; text-align: center;'>賃借条件<br><span style='font-size:10px; color:red;'>(対比表示)</span></th>"
                                f"<th>固定賃料(月額)</th><td><b>[前]</b> {format_currency(in_fixed_rent)}円<br><b style='color:red;'>[後] {format_currency(in_next_fixed_rent)}円</b></td>"
                                f"<th>最低保証賃料(月額)</th><td colspan='2'><b>[前]</b> {format_currency(in_min_guarantee)}円<br><b style='color:red;'>[後] {format_currency(in_next_min_guarantee)}円</b></td></tr>"
                                f"<tr><th>基準売上高(月額)</th><td><b>[前]</b> {format_currency(in_base_sales)}円<br><b style='color:red;'>[後] {format_currency(in_next_base_sales)}円</b></td>"
                                f"<th>歩合料率</th><td colspan='2'><b>[前]</b> {in_turnover_rate}<br><b style='color:red;'>[後] {in_next_turnover_rate}</b></td></tr>"
                            )
                        else:
                            rent_conditions_row_html = (
                                f"<tr><th rowspan='2' style='vertical-align: middle; text-align: center;'>賃借条件</th>"
                                f"<th>固定賃料(月額)</th><td>{format_currency(in_fixed_rent)} 円</td>"
                                f"<th>最低保証賃料(月額)</th><td colspan='2'>{format_currency(in_min_guarantee)} 円</td></tr>"
                                f"<tr><th>基準売上高(月額)</th><td>{format_currency(in_base_sales)} 円</td>"
                                f"<th>歩合料率</th><td colspan='2'>{in_turnover_rate}</td></tr>"
                            )
                        deposit_row_html = f"<tr><th>敷金・保証金</th><td>{format_currency(in_deposit_val)} 円</td><th>面積</th><td colspan='3'>{in_area + ' ㎡' if in_area else ''}</td></tr>"
                    elif sel_trading == "卸売":
                        pass
                    else:
                        deposit_row_html = f"<tr><th>面積</th><td colspan='5'>{in_area + ' ㎡' if in_area else ''}</td></tr>"

                    html_template_text = """
                    <!DOCTYPE html><html><head><meta charset='utf-8'>
                    <style>
                    body { font-family: 'Hiragino Kaku Gothic ProN', sans-serif; background-color: #f8f9fa; padding: 10px; margin: 0; color: #000; }
                    .ledger-box { border: 2px solid #333; padding: 20px 22px; background-color: #fff; border-radius: 4px; max-width: 820px; margin: 0 auto; box-sizing: border-box; }
                    table { width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 13.5px; line-height: 1.4; table-layout: fixed; }
                    th, td { border: 1px solid #333; padding: 6px 8px; text-align: left; word-break: break-all; }
                    th { background-color: #f2f2f2; font-weight: bold; white-space: nowrap; }
                    .header-info-table { width: 100%; margin-bottom: 10px; border: none; font-size: 12.5px; }
                    .header-info-table td { border: none; padding: 3px 0; }
                    .seal-box { display: inline-block; width: 72px; height: 72px; border: 1.5px solid #333; vertical-align: middle; text-align: center; line-height: 72px; font-size: 9.5px; color: #888; margin-left: 2px; }
                    .btn-print { background-color: #4CAF50; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%; margin-top: 15px; }
                    </style>
                    <script>
                    function printLedger() {
                      var content = document.getElementById('print-target').innerHTML;
                      var win = window.open('', '_blank', 'width=900,height=950');
                      win.document.write('<html><head><title>取引先台帳印刷</title><style>@page { size: A4 portrait; margin: 10mm 8mm; } body { font-family: sans-serif; margin: 0; padding: 0; background-color: #fff; } .ledger-box { border: 1.5px solid #000 !important; padding: 10px !important; width: 100% !important; max-width: 100% !important; box-sizing: border-box !important; } table { width: 100% !important; border-collapse: collapse; margin-bottom: 10px; font-size: 11.5px; line-height: 1.3; table-layout: fixed; } th, td { border: 1px solid #000; padding: 5px 6px; word-break: break-all; } th { background-color: #f2f2f2; font-weight: bold; } .header-info-table { width: 100%; margin-bottom: 6px; border: none !important; font-size: 11.5px; } .header-info-table td { border: none !important; padding: 2px 0; } .seal-box { display: inline-block; width: 66px; height: 66px; border: 1.5px solid #000; text-align: center; line-height: 66px; font-size: 10px; color: #888; margin-left: 2px; }</style></head><body>' + content + '</body></html>');
                      win.document.close(); win.focus();
                      setTimeout(function() { win.print(); win.close(); }, 300);
                    }
                    </script>
                    </head><body>
                    <div class='ledger-box'><div id='print-target'><div class='ledger-box' style='border: none; padding: 0;'>
                    <h2 style='text-align: center; margin-top: 0; margin-bottom: 14px; font-size: 20px; text-decoration: underline;'>取 引 先 台 帳 (出退店申請書)</h2>
                    <table class='header-info-table'>
                    <tr><td style='text-align: left;' colspan='2'>販売形態： __TRADING__</td></tr>
                    <tr><td style='text-align: left;' colspan='2'>店舗形態： __STORE_FORMAT__</td></tr>
                    <tr><td style='text-align: left; width: 78%;'>申請種別： __APP_TYPE__</td><td style='text-align: right; width: 22%;'>申請日： __APP_DATE__</td></tr>
                    <tr><td colspan='2' style='text-align: left; padding-top: 4px;'>部署名： <b>__DEPT__</b></td></tr>
                    </table>
                    <table><tr><th style='width: 12%; text-align: center;'>承認欄</th><td style='padding: 6px 8px; vertical-align: middle;'>
                    <b>社長</b> <div class='seal-box'>印</div> &nbsp;&nbsp;&nbsp;&nbsp;
                    <b>所属長</b> <div class='seal-box'>__BOSS__</div> &nbsp;&nbsp;&nbsp;&nbsp;
                    <b>担当者</b> <div class='seal-box'>__STF__</div> &nbsp;&nbsp;&nbsp;&nbsp;
                    <b>経理</b> <div class='seal-box'>印</div></td></tr></table>
                    <table>
                    <tr><th style='width: 18%;'>取引会社名</th><td>__C_NAME__</td><th style='width: 12%;'>取引先TEL</th><td style='width: 25%;'>__C_TEL__</td></tr>
                    <tr><th>取引会社郵便番号</th><td colspan='3'>__C_ZIP__</td></tr>
                    <tr><th>取引会社所在地</th><td colspan='3'>__C_ADDR__</td></tr>
                    <tr><th>請求書送付先メール</th><td colspan='3'>__C_MAIL__</td></tr>
                    <tr><th>店舗名</th><td>__S_NAME__</td><th>ブランド</th><td>__BRAND_FULL__</td></tr>
                    <tr><th>店舗郵便番号</th><td colspan='3'>__S_ZIP__</td></tr>
                    <tr><th>店舗所在地</th><td>__S_ADDR__</td><th>店舗TEL</th><td>__S_TEL__</td></tr>
                    <tr><th>出退店・変更理由</th><td colspan='3'>__REASON__</td></tr>
                    </table>
                    <table>
                    __OPEN_CLOSE_ROW__
                    __RENT_PERIOD_ROW__
                    __FIRST_DEL_ROW__
                    __RATES_ROW__
                    __RENT_CONDITIONS_ROW__
                    __DEPOSIT_ROW__
                    __RESTORATION_COST_ROW__
                    __INTERIOR_ROW__
                    <tr><th>販売代行先</th><td colspan='5'>__AGENCY__</td></tr>
                    </table>
                    __DOCS_HTML__
                    <p style='font-size: 11.5px; margin: 5px 0;'><b>■ 備考：</b> __NOTE__</p>
                    </div></div>
                    <button class='btn-print' onclick='printLedger()'>🖨️ この台帳だけをPDF出力（印刷）</button>
                    </div></body></html>
                    """

                    html_final = html_template_text.replace("__TRADING__", trading_fmt)
                    html_final = html_final.replace("__STORE_FORMAT__", store_format_fmt)
                    html_final = html_final.replace("__APP_TYPE__", app_fmt)
                    html_final = html_final.replace("__APP_DATE__", target_ledger['申請日'])
                    html_final = html_final.replace("__DEPT__", target_ledger['部署名'])
                    html_final = html_final.replace("__BOSS__", target_ledger['所属長承認'] if target_ledger['所属長承認'] else '印')
                    html_final = html_final.replace("__STF__", target_ledger['担当者承認'] if target_ledger['担当者承認'] else '印')
                    html_final = html_final.replace("__C_NAME__", in_client_name)
                    html_final = html_final.replace("__C_TEL__", in_client_tel)
                    html_final = html_final.replace("__C_ZIP__", ('〒 ' + format_postal_code(in_client_zip)) if in_client_zip else '')
                    html_final = html_final.replace("__C_ADDR__", in_client_addr)
                    html_final = html_final.replace("__C_MAIL__", in_invoice_email)
                    html_final = html_final.replace("__S_NAME__", disp_shop_name)
                    html_final = html_final.replace("__BRAND_FULL__", disp_brand_full)
                    html_final = html_final.replace("__S_ZIP__", ('〒 ' + disp_shop_zip) if disp_shop_zip else '')
                    html_final = html_final.replace("__S_ADDR__", disp_shop_addr)
                    html_final = html_final.replace("__S_TEL__", disp_shop_tel)
                    html_final = html_final.replace("__REASON__", in_reason)
                    html_final = html_final.replace("__OPEN_CLOSE_ROW__", open_close_row_html)
                    html_final = html_final.replace("__RENT_PERIOD_ROW__", rent_period_row_html)
                    html_final = html_final.replace("__FIRST_DEL_ROW__", first_del_row_html)
                    html_final = html_final.replace("__RATES_ROW__", rates_row_html)
                    html_final = html_final.replace("__RENT_CONDITIONS_ROW__", rent_conditions_row_html)
                    html_final = html_final.replace("__DEPOSIT_ROW__", deposit_row_html)
                    html_final = html_final.replace("__RESTORATION_COST_ROW__", restoration_cost_row_html)
                    html_final = html_final.replace("__INTERIOR_ROW__", interior_row_html)
                    html_final = html_final.replace("__AGENCY__", agency_disp_text)
                    html_final = html_final.replace("__DOCS_HTML__", docs_html)
                    html_final = html_final.replace("__NOTE__", target_ledger['備考/ユニケージコード'])
                    
                    components.html(html_final, height=830, scrolling=True)

                    export_ledger = target_ledger.copy()
                    export_ledger.update({
                        "店舗名": disp_shop_name,
                        "店舗郵便番号": disp_shop_zip,
                        "店舗所在地": disp_shop_addr,
                        "店舗TEL/FAX": disp_shop_tel,
                        "販売形態": trading_fmt.replace("<span style='background-color: #ffebee; border: 1.5px solid #c62828; padding: 1px 4px; border-radius: 3px; color: #c62828; font-weight: bold;'>✓ ", "").replace("</span>", "").replace("<span style='color: #a0a0a0;'>", "").replace(" <span style='font-size: 11px; color: #c62828; font-weight: bold;'>(", " (").replace(")", ")").replace("[", "").replace("]", ""),
                        "店舗形態区分": sel_store_format,
                        "申請種別": sel_app_type, 
                        "申請ステータス": sel_app_status,
                        "追加元店舗": sel_parent_shop,
                        "その他取扱ブランド": ",".join(sel_add_brands),
                        "取引会社名": in_client_name,
                        "取引会社郵便番号": format_postal_code(in_client_zip),
                        "取引会社所在地": in_client_addr,
                        "取引会社TEL": in_client_tel,
                        "請求書送付先メールアドレス": in_invoice_email,
                        "出退店・変更理由": in_reason, 
                        "開店日": disp_open_date,
                        "閉店日": disp_close_date,
                        "締日": sel_shime,
                        "入金日": sel_nyukin,
                        "初回納品日": in_first_del.strftime("%Y-%m-%d") if in_first_del else "",
                        "初回納品額": format_currency(in_first_del_amount),
                        "原状回復費用": format_currency(in_restoration_cost),
                        "賃貸借契約開始日": in_rent_start.strftime("%Y-%m-%d") if in_rent_start else "",
                        "賃貸借契約終了日": in_rent_end.strftime("%Y-%m-%d") if in_rent_end else "",
                        "変更後_賃貸借契約開始日": in_next_rent_start.strftime("%Y-%m-%d") if in_next_rent_start else "",
                        "変更後_賃貸借契約終了日": in_next_rent_end.strftime("%Y-%m-%d") if in_next_rent_end else "",
                        "変更後_レギュラーP掛率": in_next_reg_p,
                        "変更後_レギュラーS掛率": in_next_reg_s,
                        "変更後_セレクト/コラボP掛率": in_next_sel_p,
                        "変更後_セレクト/コラボS掛率": in_next_sel_s,
                        "面積": in_area if sel_trading != "卸売" else "",
                        "固定賃料": format_currency(in_fixed_rent),
                        "最低保証賃料": format_currency(in_min_guarantee),
                        "基準売上高": format_currency(in_base_sales),
                        "歩合料率": in_turnover_rate,
                        "変更後_固定賃料": format_currency(in_next_fixed_rent),
                        "変更後_最低保証賃料": format_currency(in_next_min_guarantee),
                        "変更後_基準売上高": format_currency(in_next_base_sales),
                        "変更後_歩合料率": in_next_turnover_rate,
                        "敷金_保証金": format_currency(in_deposit_val),
                        "内装造作": str(sel_interior) + (" (※店舗内装造作届要添付)" if sel_interior == "有" else "") if sel_interior else "",
                        "販売代行先タイプ": sel_agency_type,
                        "販売代行名": sel_daiko_name,
                        "代行その他補足": in_agency_other_comment,
                        "提出必要書類": docs_text
                    })
                    
                    dl_btn_label = f"📥 「{disp_shop_name}」の台帳CSVを出力"
                    dl_file_name = f"取引先台帳_{target_ledger['U_Retail店舗コード']}_{disp_shop_name}.csv"
                    st.download_button(
                        label=dl_btn_label,
                        data=get_download_df(pd.DataFrame([export_ledger])).to_csv(index=False).encode('utf_8_sig'),
                        file_name=dl_file_name,
                        mime="text/csv",
                        type="primary",
                        use_container_width=True
                    )

    with tab_b:
        if df is not None and not df.empty:
            st.info("💡 データ量が多いため、ボタンを押した時にだけ全店舗のデータを一括生成します。")
            if st.button("🔄 全店舗の台帳データを生成して表示", key="btn_generate_all"):
                with st.spinner("全店舗のデータを生成しています..."):
                    full_export_rows = [fetch_single_ledger_row(df.loc[idx]) for idx in df.index]
                    st.session_state["cached_export_df"] = pd.DataFrame(full_export_rows)
            
            if "cached_export_df" in st.session_state:
                export_df = st.session_state["cached_export_df"]
                st.dataframe(export_df, use_container_width=True)
                dl_all_name = f"取引先台帳全店舗一覧_{datetime.now().strftime('%Y%m%d')}.csv"
                st.download_button(
                    label="📥 全店舗の取引先台帳データを一括CSVダウンロード",
                    data=get_download_df(export_df).to_csv(index=False).encode('utf_8_sig'),
                    file_name=dl_all_name,
                    mime="text/csv"
                )

elif menu == "⚙️ マスタ管理":
    if user_role != "経理":
        st.error("⚠️ マスタ管理は経理担当者専用メニューです。")
        st.stop()
    st.subheader("⚙️ マスタデータの管理")
    master_targets = ["販売代行", "ブランド", "取引先", "合計取引先", "売上管理担当者", "営業担当者"]
    selected_master = st.selectbox("追加したいマスタ:", master_targets)
    df_target_master = all_dfs.get(selected_master, pd.DataFrame())
    st.dataframe(df_target_master, use_container_width=True)
    with st.form(key=f"master_form_{selected_master}"):
        c1, c2 = st.columns(2)
        if selected_master == "販売代行":
            new_code, new_name = c1.text_input("ミロク取引先コード"), c2.text_input("正式名称")
            new_row_dict = {"ｺｰﾄﾞ": new_code.strip(), "正式名称": new_name.strip()}
        elif selected_master == "ブランド":
            new_code, new_name = c1.text_input("ブランドコード"), c2.text_input("ブランド名")
            new_row_dict = {"ブランドコード": new_code.strip(), "ブランド名": new_name.strip()}
        elif selected_master in ["取引先", "合計取引先"]:
            new_code, new_name = c1.text_input("ｺｰﾄﾞ"), c2.text_input("正式名称")
            new_row_dict = {"ｺｰﾄﾞ": new_code.strip(), "正式名称": new_name.strip()}
        elif selected_master == "売上管理担当者":
            new_name, new_email = c1.text_input("売上管理担当者名"), c2.text_input("メールアドレス")
            new_row_dict = {"売上管理担当者ID": "", "売上管理担当者名": new_name.strip(), "メールアドレス": new_email.strip()}
        elif selected_master == "営業担当者":
            new_name, new_email = c1.text_input("営業担当者名"), c2.text_input("メールアドレス")
            new_row_dict = {"ブランドコード": "", "営業担当者名": new_name.strip(), "メールアドレス": new_email.strip()}
        
        if st.form_submit_button("💾 追加する", type="primary"):
            is_valid = False
            if selected_master not in ["売上管理担当者", "営業担当者"] and new_code.strip() and new_name.strip():
                is_valid = True
            elif selected_master in ["売上管理担当者", "営業担当者"] and new_name.strip():
                is_valid = True
                
            if is_valid:
                all_dfs[selected_master] = pd.concat([df_target_master, pd.DataFrame([new_row_dict])], ignore_index=True)
                op_cd = new_code if selected_master not in ["売上管理担当者", "営業担当者"] else ""
                all_dfs["変更履歴"] = add_history(df_history, "マスタ追加", selected_master, op_cd, new_name, "新しいマスタを追加")
                if save_all_data(all_dfs, target_sheets=[selected_master, "変更履歴"]):
                    st.success("🎉 追加完了！")
                    st.rerun()

elif menu == "📅 出退店リスト":
    st.subheader("📅 出店・退店レポート")
    c_d1, c_d2 = st.columns(2)
    start_date = c_d1.date_input("開始日", value=date(date.today().year - 1, 1, 1))
    end_date = c_d2.date_input("終了日", value=date.today())
    if start_date <= end_date:
        df_m = pd.merge(df, df_rent.drop_duplicates(subset=["家賃計上部門コード"]), on="家賃計上部門コード", how="left").fillna("") if df_rent is not None and not df_rent.empty else df.copy()
        df_m["_OPEN_dt"] = df_m["開店日"].apply(parse_date)
        df_m["_CLOSE_dt"] = df_m["閉店日"].apply(parse_date)
        df_o = df_m[(df_m["_OPEN_dt"].notnull()) & (df_m["_OPEN_dt"] >= start_date) & (df_m["_OPEN_dt"] <= end_date)].drop(columns=["_OPEN_dt", "_CLOSE_dt"])
        df_c = df_m[(df_m["_CLOSE_dt"].notnull()) & (df_m["_CLOSE_dt"] >= start_date) & (df_m["_CLOSE_dt"] <= end_date)].drop(columns=["_OPEN_dt", "_CLOSE_dt"])
        t_o, t_c = st.tabs([f"🎉 出店リスト ({len(df_o)}件)", f"🚪 退店リスト ({len(df_c)}件)"])
        with t_o:
            display_styled_dataframe(df_o)
            st.download_button("📥 CSV出力", get_download_df(df_o).to_csv(index=False).encode('utf_8_sig'), f"出店リスト_{start_date}_{end_date}.csv")
        with t_c:
            display_styled_dataframe(df_c)
            st.download_button("📥 CSV出力", get_download_df(df_c).to_csv(index=False).encode('utf_8_sig'), f"退店リスト_{start_date}_{end_date}.csv")

elif menu == "📜 有効契約一覧":
    st.subheader("📜 有効家賃契約一覧")
    target_base_date = st.date_input("基準日を選択:", value=date.today())
    if df_rent is not None and not df_rent.empty:
        df_m = pd.merge(df_rent, df.drop_duplicates(subset=["家賃計上部門コード"]), on="家賃計上部門コード", how="left").fillna("")
        def is_active(r, b):
            rs = parse_date(r.get("原契約開始日", ""))
            re_ = parse_date(r.get("現契約終了日", ""))
            if (rs and rs > b) or (re_ and re_ < b): return False
            od = parse_date(r.get("開店日", ""))
            cd = parse_date(r.get("閉店日", ""))
            if (od and od > b) or (cd and cd < b): return False
            return True
        df_act = df_m[df_m.apply(lambda r: is_active(r, target_base_date), axis=1)].copy()
        
        if 'ブランドコード' in df_act.columns:
            df_act['ブランド名'] = df_act['ブランドコード'].apply(lambda x: brand_dict.get(clean_str(x), ""))
            cols = df_act.columns.tolist()
            cols.remove('ブランド名')
            cols.insert(cols.index('ブランドコード') + 1, 'ブランド名')
            df_act = df_act[cols]
        
        st.write(f"### 基準日: {target_base_date} 時点の有効件数 : **{len(df_act)} 件**")
        display_styled_dataframe(df_act)
        st.download_button("📥 CSV出力", get_download_df(df_act).to_csv(index=False).encode('utf_8_sig'), f"有効家賃契約_{target_base_date}.csv")

elif menu == "📝 変更履歴ログ":
    st.subheader("📝 変更履歴ログ")
    if df_history is not None and not df_history.empty:
        st.dataframe(df_history)
        st.download_button("📥 CSVダウンロード", df_history.to_csv(index=False).encode('utf_8_sig'), "変更履歴ログ.csv")

elif menu == "📖 マニュアル":
    st.subheader("📖 システムマニュアル")
    st.info("📌 **LMC店舗DB とは**\n\n本システムは、店舗の基本情報、家賃条件、販売代行手数料、出退店に伴う取引先台帳の申請データなどを一元管理・出力するためのデータベースです。")
    m_lines = [
        "---",
        "### ✨ 新機能・重要機能の紹介（J-SOX・業務効率化対応）",
        "#### 🔒 1. 経理確認済データの「ロック機能」と解除パスワード",
        "*   **概要:** 「✏️ 店舗修正・削除」および「🏢 家賃条件DB」画面において、経理担当者が処理を完了したデータに **「☑️ 経理確認済」** のチェックを入れることで、そのデータをロックできます。",
        "*   **メリット:** ロックされたデータは、誤操作や不正による上書き保存・削除ができなくなります。過去の確定データが不用意に書き換えられることを防ぐ、強力な内部統制（J-SOX）機能です。",
        "*   **ロックの解除方法:** ロックされたデータを開くと、パスワードの入力欄が表示されます。ここに経理部専用のロック解除パスワードを入力するとロックが解除され、再び編集と保存が可能になります。",
        "",
        "#### 🚀 2. 出店承認パイプラインと「内部統制ロック」",
        "*   **概要:** 新規出店の際、BHD（親会社）の承認進捗をステータス管理できるようになりました。ダッシュボード上で、承認待ちや手続待ちの店舗が「パイプライン」として一覧表示されます。",
        "*   **メリット:** 承認の遅れを早期発見できます。また、**BHDの「取締役会承認済」にならない限り、取引先台帳（申請書）の入力・保存ができないロック機構**を備えており、親会社未承認のまま現場が勝手に手続きを進めるリスクをシステム的に防止します。",
        "",
        "#### ⚠️ 3. 契約更新アラート ＆ 申請ステータス連動",
        "*   **概要:** 「🏢 家賃条件DB」に登録されている「現契約終了日」から逆算し、**満了まで6ヶ月を切った店舗**がダッシュボードに警告表示されます。",
        "*   **メリット:** 単なる期限通知だけでなく、取引先台帳の **「申請ステータス」が『申請書作成済・出力済』に変更されるまで警告が出続ける** ため、更新や退店の手続き漏れ（自動更新リスク）を確実に防ぐタスク管理ツールとして機能します。",
        "",
        "#### 📊 4. 保有固定資産の表示と更新",
        "*   **概要:** 「✏ 店舗修正・削除」画面の下部で、該当店舗が保有している固定資産一覧とその金額（取得価額や帳簿価額）を確認できます。",
        "*   **メリット:** 監査や棚卸しの際に、店舗ごとの資産状況を一目で把握できます。データは「固定資産データ更新」メニューから最新のCSVをアップロードするだけで一括更新されます。",
        "",
        "---",
        "### 🤝 営業・経理の連携ルール（役割分担）",
        "- **【営業】の役割:** 新規店舗の基本情報入力、出店承認プロセスの進捗入力、および条件変更・退店に伴う「取引先台帳（申請書）」の作成・出力。（※店舗修正・削除画面は閲覧専用となり、マスタ管理メニューは経理専用です）",
        "- **【経理】の役割:** 店舗データの直接修正・削除、ミロク部門コード・家賃計上部門コード・POSCMレジコード等の専用コード入力、マスタ管理・追加、および確定データの「経理ロック」。",
        "",
        "---",
        "### 🔄 店舗ライフサイクルに沿ったワークフロー",
        "",
        "#### 1. 新規出店（新規店舗登録・ブランド追加）",
        "1.  **【営業】** 「➕ 新規店舗登録」から、店舗の基本情報を登録し、BHDの承認ステータスを管理します。既存店舗へのブランド追加時はBHD申請をスキップ可能です。",
        "2.  **【営業】** BHDの承認が下りたら、「📄 取引先台帳出力」を開き、詳細条件を入力します。申請種別を「新規出店」とし、PDFを出力して経営層へ出店申請（稟議）を行います。出力後、「申請ステータス」を『申請書作成済・出力済』に変更して保存します。",
        "3.  **【経理】** 決裁が下り実際の出店が決まったら、「✏️ 店舗修正・削除」から該当店舗を呼び出し、ミロク部門コードなど経理システム連携に必要な専用コードを追記して「経理確認済」ロックをかけます。",
        "",
        "#### 2. 契約更新・条件変更（掛率や家賃の変更）",
        "1.  **【営業】** 「📄 取引先台帳出力」を開き、対象店舗を呼び出します。申請種別を「更新・条件変更あり」または「更新・条件変更なし」にして変更内容を入力し、PDFを出力して社内申請を行います。",
        "2.  **【超便利機能・自動連動】** 台帳出力画面で「更新・条件変更あり」の申請書を作成し、「💾 台帳調整内容を保存 ＆ マスタに変更予定を自動連動させる」ボタンを押すと、店舗DB・家賃条件DBの「変更予定枠」に変更後の数字と適用予定日が自動で予約入力されます。",
        "3.  **【システム】** 適用予定日になると、システムがダッシュボード上で変更予約一覧として表示し、経理担当者が一括適用ボタンを押すことで安全にマスタを更新できます。",
        "",
        "#### 3. 退店（全ブランド撤退・一部ブランド撤退）",
        "1.  **【営業】** 「📄 取引先台帳出力」を開き、申請種別を「退店」にして閉店日などを入力し、PDFを出力して退店申請を行います。",
        "2.  **【営業】** 閉店日が確定・到来したら、「✏️ 店舗修正・削除」から該当店舗のステータスを「CLOSED」に変更して保存します。",
        "",
        "---",
        "### 🔍 各メニューの使いかた",
        "#### 🏠 ダッシュボード（トップ画面）",
        "- 出店承認パイプライン、要マスタ登録リスト、契約満了アラート、条件変更予定、直近のOPEN/CLOSE店舗など、**「次に誰が何をすべきか（Next Action）」**を一覧表示します。",
        "#### 🔍 店舗検索・閲覧",
        "- 登録されている全店舗の一覧を確認・検索・ダウンロードできます。",
        "#### ➕ 新規店舗登録",
        "- 新しい店舗を白紙から、または既存店舗の情報を引き継いで登録します。",
        "#### ✏ 店舗修正・削除",
        "- 店舗情報の修正や削除が行えます。",
        "#### 🏢 家賃条件DB / 💼 販売手数料DB",
        "- 店舗ごとの家賃、敷金・保証金、販売代行手数料率などを一元管理します。",
        "#### 📈 固定資産データ更新",
        "- 毎月出力される「資産別固定資産減価償却内訳表.csv」を読み込ませ、システム全体へ共有します。",
        "#### 📄 取引先台帳出力",
        "- 出退店や条件変更時の「取引先台帳（申請書）」を作成し、PDFやCSVで出力します。出力完了後は「申請ステータス」を「申請書作成済・出力済」に変更して保存してください。",
        "#### ⚙️ マスタ管理",
        "- 各画面のドロップダウンに表示される「販売代行名」「ブランド」「取引先」「売上管理担当者」「営業担当者」などを追加・登録します。"
    ]
    for line in m_lines:
        st.markdown(line)
