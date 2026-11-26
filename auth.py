import streamlit as st
import random
import string
import smtplib
import re
from email.message import EmailMessage

def get_smtp_config():
    raw_user = st.secrets.get("smtp", {}).get("user", "")
    user = re.sub(r'[^a-zA-Z0-9_.+-@]', '', raw_user)
    raw_pass = st.secrets.get("smtp", {}).get("password", "")
    pwd = re.sub(r'[^a-zA-Z0-9]', '', raw_pass)
    return user, pwd

def send_otp_email(to_addr, otp_code):
    user, pwd = get_smtp_config()
    if not user or not pwd: return False
    msg = EmailMessage()
    msg['From'] = user
    msg['To'] = re.sub(r'[^a-zA-Z0-9_.+-@]', '', to_addr)
    msg['Subject'] = "【LMC店舗DB】2段階認証コードのご案内"
    msg.set_content(f"LMC店舗DB 2段階認証コードのご案内\n\n以下のワンタイム認証コードを画面に入力してください。\n\n■ 認証コード： {otp_code}\n\n※身に覚えのない場合は、本メールを破棄してください。")
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.ehlo(); server.starttls(); server.ehlo()
        server.login(user, pwd)
        server.send_message(msg); server.quit()
        return True
    except: return False

def authenticate():
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    if "step1_passed" not in st.session_state: st.session_state.step1_passed = False
    if "generated_otp" not in st.session_state: st.session_state.generated_otp = None
    if "user_email" not in st.session_state: st.session_state.user_email = ""
    if "user_role" not in st.session_state: st.session_state.user_role = None

    if not st.session_state.logged_in:
        st.markdown("## 🔐 LMC店舗DB ログイン")
        c1, _ = st.columns([1, 1])
        with c1:
            if not st.session_state.step1_passed:
                ie = st.text_input("メールアドレス")
                ip = st.text_input("パスワード", type="password")
                if st.button("次へ (認証コード送信)", type="primary", use_container_width=True):
                    ta = ie.strip()
                    users = st.secrets.get("users", {})
                    
                    if not users and ta == "admin@lmc.co.jp" and ip == "admin":
                        users = {ta: {"password": "admin", "role": "経理"}}
                        
                    if ta in users and str(users[ta].get("password", "")) == ip.strip():
                        st.session_state.user_role = users[ta].get("role", "閲覧")
                        st.session_state.user_email = ta
                        otp = ''.join(random.choices(string.digits, k=6))
                        with st.spinner("認証コードを送信中..."):
                            if send_otp_email(ta, otp) or not st.secrets.get("smtp"):
                                st.session_state.generated_otp = otp
                                st.session_state.step1_passed = True
                                st.rerun()
                            else:
                                st.error("OTPメールの送信に失敗しました。SMTP設定をご確認ください。")
                    else: st.error("⚠️ メールアドレスまたはパスワードが違います")
            else:
                io_code = st.text_input("6桁の認証コード", max_chars=6)
                cb1, cb2 = st.columns(2)
                if cb1.button("ログイン", type="primary", use_container_width=True):
                    if io_code.strip() == st.session_state.generated_otp:
                        st.session_state.logged_in = True
                        st.session_state.step1_passed = False
                        st.session_state.generated_otp = None
                        st.rerun()
                    else: st.error("⚠️ 認証コードが正しくありません")
                if cb2.button("戻る", use_container_width=True):
                    st.session_state.step1_passed = False
                    st.session_state.generated_otp = None
                    st.rerun()
        st.stop()

def send_notification_email(to_addrs, subject, body):
    user, pwd = get_smtp_config()

    if not user or not pwd: return False
    if isinstance(to_addrs, str):
        addr_list = [x.strip() for x in to_addrs.split(',')]
    else:
        addr_list = to_addrs
    clean_addrs = [re.sub(r'[^a-zA-Z0-9_.+-@]', '', e) for e in addr_list if e.strip()]
    t_addr = ",".join(clean_addrs)
    
    if not t_addr: return False
    msg = EmailMessage()
    msg['From'] = user
    msg['To'] = t_addr
    msg['Subject'] = subject
    msg.set_content(body)
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.ehlo(); server.starttls(); server.ehlo()
        server.login(user, pwd)
        server.send_message(msg); server.quit()
        return True
    except: return False
