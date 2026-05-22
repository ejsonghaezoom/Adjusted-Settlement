import streamlit as st
import os
import json
import traceback
from data_processor import process_settlement_data, get_summary_from_diff
from doc_generator import generate_pdf, generate_excel
from api_services import read_google_sheet, upload_to_drive, generate_email_body, send_email_via_gmail

st.set_page_config(page_title="전력거래대금 수정정산 자동화", page_icon="⚡", layout="centered")

st.title("⚡ 전력거래대금 수정정산 자동화 시스템")
st.markdown("기존 정산 시트와 수정 정산 시트의 데이터를 비교하고 정산 내역서(PDF, Excel)를 자동 생성하여 발송합니다.")

# 입력 폼
with st.form("main_form"):
    st.subheader("1. 구글 시트 URL 입력")
    url_orig = st.text_input("기존 정산 데이터 구글 시트 URL", placeholder="https://docs.google.com/spreadsheets/d/...")
    url_rev = st.text_input("수정 정산 데이터 구글 시트 URL", placeholder="https://docs.google.com/spreadsheets/d/...")
    
    st.subheader("2. 전송 및 저장 설정")
    recipient_email = st.text_input("수신자 이메일 주소", placeholder="vpp.billing@haezoom.com")
    drive_folder_id = st.text_input("업로드할 구글 드라이브 폴더 ID (선택)", help="파일을 저장할 폴더의 ID를 입력하세요. 비워두면 루트에 저장됩니다.")
    
    st.subheader("3. API 인증")
    gemini_api_key = st.text_input("Gemini API Key", type="password", help="메일 본문 자동 생성을 위한 Gemini API Key")
    
    submit_btn = st.form_submit_button("실행", type="primary")

if submit_btn:
    if not url_orig or not url_rev:
        st.error("두 개의 구글 시트 URL을 모두 입력해주세요.")
        st.stop()
    if not gemini_api_key:
        st.error("Gemini API Key를 입력해주세요.")
        st.stop()
    if not recipient_email:
        st.error("수신자 이메일 주소를 입력해주세요.")
        st.stop()
        
    try:
        # Streamlit Secrets에서 Google Credentials 가져오기
        if "google_credentials" not in st.secrets:
            st.error("Streamlit Secrets에 'google_credentials'가 설정되어 있지 않습니다.")
            st.stop()
            
        creds_dict = dict(st.secrets["google_credentials"])
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 1. 데이터 읽기
        status_text.text("구글 시트에서 데이터를 읽어옵니다...")
        df_orig = read_google_sheet(url_orig, creds_dict)
        df_rev = read_google_sheet(url_rev, creds_dict)
        progress_bar.progress(20)
        
        # 2. 데이터 처리 및 차액 계산
        status_text.text("데이터를 병합하고 차액을 계산합니다...")
        df_final = process_settlement_data(df_orig, df_rev)
        summary = get_summary_from_diff(df_final)
        progress_bar.progress(40)
        
        # 3. 문서 생성 (PDF, Excel)
        status_text.text("보고서(PDF) 및 엑셀(Excel) 파일을 생성합니다...")
        os.makedirs("output", exist_ok=True)
        plant_name_safe = summary.get('발전소명', '발전소').replace("/", "_")
        
        pdf_path = f"output/{plant_name_safe}_수정정산내역서.pdf"
        excel_path = f"output/{plant_name_safe}_수정정산데이터.xlsx"
        
        generate_pdf(summary, pdf_path)
        generate_excel(df_final, excel_path)
        progress_bar.progress(60)
        
        # 4. 드라이브 업로드 (옵션)
        if drive_folder_id:
            status_text.text("구글 드라이브에 파일을 업로드합니다...")
            upload_to_drive(pdf_path, drive_folder_id, creds_dict)
            upload_to_drive(excel_path, drive_folder_id, creds_dict)
        progress_bar.progress(70)
        
        # 5. 메일 본문 생성 및 전송
        status_text.text("Gemini AI를 통해 이메일 본문을 생성하고 발송합니다...")
        email_body = generate_email_body(gemini_api_key, summary)
        subject = f"[해줌] {summary.get('발전소명', '발전소')} 전력거래대금 수정 정산 안내"
        
        # 발송자 이메일은 서비스 계정에 연결된 이메일이나 위임된 이메일을 사용
        sender_email = creds_dict.get('client_email') 
        
        send_email_via_gmail(
            sender=sender_email, 
            to=recipient_email, 
            subject=subject, 
            body=email_body, 
            attachments=[pdf_path, excel_path],
            creds_dict=creds_dict
        )
        progress_bar.progress(100)
        status_text.text("모든 작업이 성공적으로 완료되었습니다!")
        st.success("✅ 메일 발송 및 파일 처리가 완료되었습니다.")
        
        # 결과 표시
        with st.expander("생성된 데이터 (미리보기)"):
            st.dataframe(df_final)
            
        with st.expander("생성된 이메일 본문"):
            st.write(email_body)
            
    except Exception as e:
        st.error(f"오류가 발생했습니다: {str(e)}")
        with st.expander("상세 오류 로그"):
            st.code(traceback.format_exc())
