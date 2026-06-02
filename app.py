import streamlit as st
import os
import traceback
import base64
import json
from calc_engine import SettlementCalcEngine
from doc_engine import DocumentGenerator
from mail_engine import AutomationMailEngine
from streamlit_oauth import OAuth2Component
from google.oauth2.credentials import Credentials

def apply_haezoom_theme():
    st.markdown("""
        <style>
        :root {
            --primary-orange: #FF6B00;
            --bg-light: #F8F9FA;
        }
        .stButton>button {
            background-color: var(--primary-orange);
            color: white;
            border-radius: 6px;
            border: none;
            font-weight: bold;
            transition: all 0.3s ease;
        }
        .stButton>button:hover {
            background-color: #E56000;
            color: white;
        }
        /* 💡 입력창과 텍스트 영역의 글자 색상을 어두운 색(#212529)으로 강제 지정 */
        .stTextInput>div>div>input, .stTextArea>div>div>textarea {
            background-color: var(--bg-light);
            border: 1px solid #E0E0E0;
            color: #212529 !important; 
        }
        </style>
    """, unsafe_allow_html=True)

def decode_id_token(id_token):
    try:
        parts = id_token.split('.')
        if len(parts) != 3:
            return None
        payload = parts[1]
        padded = payload + '=' * (4 - len(payload) % 4)
        decoded = base64.b64decode(padded).decode('utf-8')
        return json.loads(decoded).get('email')
    except Exception:
        return None

def verify_google_auth():
    # Load secrets
    try:
        client_id = st.secrets["google_credentials"]["client_id"]
        client_secret = st.secrets["google_credentials"]["client_secret"]
        redirect_uri = st.secrets["google_credentials"]["redirect_uri"]
    except KeyError:
        st.error("⚠️ `.streamlit/secrets.toml`에 Google OAuth 자격 증명이 설정되지 않았습니다.")
        st.stop()

    AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    REVOKE_URL = "https://oauth2.googleapis.com/revoke"

    # Initialize OAuth2 component
    oauth2 = OAuth2Component(client_id, client_secret, AUTHORIZE_URL, TOKEN_URL, TOKEN_URL, REVOKE_URL)

    if "token" not in st.session_state:
        st.warning("Google Workspace 로그인이 필요합니다.")
        result = oauth2.authorize_button(
            name="Google 계정으로 로그인",
            icon="https://www.google.com/favicon.ico",
            redirect_uri=redirect_uri,
            scope="openid email profile https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/gmail.send",
            key="google_oauth",
            use_container_width=True
        )

        if result and "token" in result:
            st.session_state["token"] = result["token"]
            st.rerun()
        st.stop()
    
    # Retrieve email from ID token
    token = st.session_state["token"]
    user_email = decode_id_token(token.get("id_token", ""))
    
    if not user_email:
        st.error("로그인 정보를 파악할 수 없습니다. 다시 로그인해주세요.")
        del st.session_state["token"]
        st.stop()
        
    if not user_email.endswith("@haezoom.com"):
        st.error(f"🚨 접근 거부: 해줌 사내 계정(@haezoom.com)만 접근 가능합니다. (현재 계정: {user_email})")
        del st.session_state["token"]
        st.stop()
        
    # Generate Google Credentials object
    creds = Credentials(
        token=token["access_token"],
        refresh_token=token.get("refresh_token"),
        token_uri=TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret
    )
    
    return user_email, creds

def main():
    st.set_page_config(page_title="해줌 수정정산 관리", page_icon="⚡", layout="wide")
    apply_haezoom_theme()
    
    user_email, google_creds = verify_google_auth()
    
    st.title("⚡ 해줌 전력거래대금 수정정산 관리")
    st.caption(f"인증된 사용자: {user_email}")
    
    with st.sidebar:
        st.subheader("📁 양식 다운로드")
        if not os.path.exists("수정정산_양식.xlsx"):
            import pandas as pd
            with pd.ExcelWriter("수정정산_양식.xlsx") as writer:
                pd.DataFrame({"발전소명":[], "사업자번호":[], "메일 주소":[]}).to_excel(writer, sheet_name="사업자정보", index=False)
                pd.DataFrame(columns=["년", "월", "발전소명", "계량발전량\\n(kW)", "제어량\\n(kW)", "전력량정산금", "해줌보상금", "추가지급금\\n(예측제도인센)", "전력거래 \\n수수료", "정산금 합산\\n(공급가액)", "부가세", "정산금 총액"]).to_excel(writer, sheet_name="기존_월별", index=False)
                pd.DataFrame(columns=["년", "월", "발전소명", "계량발전량\\n(kW)", "제어량\\n(kW)", "전력량정산금", "해줌보상금", "추가지급금\\n(예측제도인센)", "전력거래 \\n수수료", "정산금 합산\\n(공급가액)", "부가세", "정산금 총액"]).to_excel(writer, sheet_name="수정_월별", index=False)
                pd.DataFrame(columns=["일시", "발전소명", "계량발전량\\n(kWh)", "감발량\\n(kWh)", "감발량정산금(a)\\n(원)", "전력량정산금", "추가지급금\\n(예측인센티브)", "고객정산금"]).to_excel(writer, sheet_name="기존_일별", index=False)
                pd.DataFrame(columns=["일시", "발전소명", "계량발전량\\n(kWh)", "감발량\\n(kWh)", "감발량정산금(a)\\n(원)", "전력량정산금", "추가지급금\\n(예측인센티브)", "고객정산금"]).to_excel(writer, sheet_name="수정_일별", index=False)

        with open("수정정산_양식.xlsx", "rb") as f:
            st.download_button("📥 기본 양식 다운로드", data=f, file_name="수정정산_양식.xlsx")

        if st.button("로그아웃"):
            del st.session_state["token"]
            st.rerun()

    with st.form("settlement_form"):
        st.subheader("1. 정산 기본 정보")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("정산 시작일")
        with col2:
            end_date = st.date_input("정산 종료일")
            
        settlement_date = st.text_input("수정정산일 (yymmdd)", placeholder="예: 240501", max_chars=6)
        uploaded_file = st.file_uploader("수정정산 데이터 업로드 (Excel)", type=['xlsx'])
        
        st.subheader("2. API 및 전송 설정")
        drive_path = st.text_input("구글 드라이브 폴더 ID (필수)", placeholder="산출물이 저장될 폴더 ID")
        
        col_mail1, col_mail2 = st.columns(2)
        with col_mail1:
            sender_email = st.text_input("발신자 메일 주소", value=user_email)
        with col_mail2:
            cc_email = st.text_input("참조자 메일 주소 (선택)", placeholder="cc@haezoom.com")
            
        reason = st.text_area("수정 사유 (필수)", placeholder="예: 계량기 통신 오류로 인한 발전량 누락분 반영")
        
        submitted = st.form_submit_button("로직 실행 및 발송 🚀")
        
    if submitted:
        if not uploaded_file or not drive_path or not reason or not settlement_date:
            st.error("⚠️ 필수 항목(엑셀 파일, 드라이브 경로, 수정 사유, 수정정산일)을 모두 기입해주세요.")
            st.stop()
            
        progress = st.progress(0)
        status = st.empty()
        
        try:
            status.text("데이터 파싱 및 차액 계산 중...")
            calc_engine = SettlementCalcEngine(uploaded_file)
            email_mapping, monthly_diff, daily_diff_dataset = calc_engine.execute_pipeline()
            progress.progress(30)
            
            status.text("PDF 및 Excel 산출물 생성 중...")
            doc_engine = DocumentGenerator()
            period_str = f"{start_date.year}년 {start_date.month}월"
            
            # Use real Google Credentials injected from OAuth
            mail_engine = AutomationMailEngine(google_creds)
            
            total_plants = len(email_mapping)
            for i, (plant_name, recipient) in enumerate(email_mapping.items()):
                if plant_name not in monthly_diff:
                    continue
                    
                monthly_data = monthly_diff[plant_name]
                
                # 1. 파일 생성
                pdf_path = doc_engine.generate_pdf(plant_name, period_str, monthly_data)
                excel_path = doc_engine.generate_excel(plant_name, period_str, daily_diff_dataset)
                attachments = [pdf_path, excel_path]
                
                # 2. 드라이브 업로드 (실제 API)
                status.text(f"[{plant_name}] 구글 드라이브 업로드 중...")
                mail_engine.upload_to_drive(pdf_path, drive_path)
                mail_engine.upload_to_drive(excel_path, drive_path)
                
                # 3. 메일 발송 (실제 API)
                status.text(f"[{plant_name}] Gmail 전송 중...")
                mail_engine.send_settlement_email(
                    sender=sender_email,
                    recipient=recipient,
                    cc=cc_email,
                    plant_name=plant_name,
                    period_str=period_str,
                    reason=reason,
                    attachments=attachments
                )
                
                progress.progress(30 + int(70 * (i + 1) / total_plants))
                
            status.text("✅ 모든 작업이 완료되었습니다!")
            st.success("모든 발전소에 대한 산출물 생성, 업로드 및 메일 발송을 완료했습니다.")
            
        except Exception as e:
            st.error(f"❌ 작업 중 에러 발생: {str(e)}")
            with st.expander("에러 상세 로그 확인"):
                st.code(traceback.format_exc())

if __name__ == "__main__":
    main()