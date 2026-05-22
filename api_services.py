import os
import base64
import json
from email.message import EmailMessage
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import google.generativeai as genai

# OAuth2 Scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/gmail.send'
]

def get_google_credentials(creds_dict: dict):
    """
    Streamlit secrets에서 가져온 dict 형태의 인증 정보로 Credentials 객체 생성
    """
    return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)

def read_google_sheet(url: str, creds_dict: dict, tab_name: str = '고객정산금(일별)') -> pd.DataFrame:
    """
    주어진 구글 시트 URL에서 특정 탭의 데이터를 읽어옵니다.
    """
    creds = get_google_credentials(creds_dict)
    client = gspread.authorize(creds)
    
    # URL에서 스프레드시트 열기
    sheet = client.open_by_url(url)
    worksheet = sheet.worksheet(tab_name)
    
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

def upload_to_drive(file_path: str, folder_id: str, creds_dict: dict) -> str:
    """
    파일을 Google Drive의 특정 폴더에 업로드하고 파일 ID 반환
    """
    creds = get_google_credentials(creds_dict)
    drive_service = build('drive', 'v3', credentials=creds)
    
    file_name = os.path.basename(file_path)
    file_metadata = {
        'name': file_name,
        'parents': [folder_id] if folder_id else []
    }
    
    media = MediaFileUpload(file_path, resumable=True)
    
    uploaded_file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    
    return uploaded_file.get('id')

def generate_email_body(api_key: str, summary: dict) -> str:
    """
    Gemini API를 사용하여 정중한 이메일 본문을 생성합니다.
    """
    genai.configure(api_key=api_key)
    # gemini-3-flash-preview 모델 명시
    model = genai.GenerativeModel('gemini-3-flash-preview')
    
    prompt = f"""
    당신은 전력 중개 사업자 '주식회사 해줌'의 정산 담당자입니다.
    고객사인 '{summary.get('발전소명', '발전소')}'에게 전력거래대금 수정 정산이 발생하였음을 안내하는 정중한 비즈니스 이메일 본문을 작성해주세요.
    
    [정산 요약 정보]
    - 변경 대상 기간: {summary.get('시작일', '-')} ~ {summary.get('종료일', '-')}
    - 총 변경 금액(차액 합계): {summary.get('총_차액', 0):,} 원
    - 공급가액 차액: {summary.get('공급가액', 0):,} 원
    - 부가세 차액: {summary.get('VAT', 0):,} 원
    
    상세 내역은 첨부된 PDF와 Excel 파일을 확인해 달라는 멘트를 포함해주세요.
    제목은 포함하지 말고 본문 내용만 작성해주세요.
    """
    
    response = model.generate_content(prompt)
    return response.text

def send_email_via_gmail(sender: str, to: str, subject: str, body: str, attachments: list, creds_dict: dict):
    """
    Gmail API를 통해 이메일을 발송합니다.
    """
    # 서비스 계정에 Domain-Wide Delegation이 설정되어 있고 subject(sender)를 지정하는 것이 원칙이나,
    # 여기서는 간단히 인증된 계정 자신(me)을 발송자로 사용합니다.
    creds = get_google_credentials(creds_dict)
    service = build('gmail', 'v1', credentials=creds)
    
    message = EmailMessage()
    message.set_content(body)
    message['To'] = to
    message['From'] = sender
    message['Subject'] = subject
    
    # 첨부 파일 추가
    for filepath in attachments:
        if os.path.exists(filepath):
            import mimetypes
            ctype, encoding = mimetypes.guess_type(filepath)
            if ctype is None or encoding is not None:
                ctype = 'application/octet-stream'
            maintype, subtype = ctype.split('/', 1)
            
            with open(filepath, 'rb') as f:
                message.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=os.path.basename(filepath))

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    send_request = {'raw': raw_message}
    
    try:
        sent_message = service.users().messages().send(userId='me', body=send_request).execute()
        return sent_message['id']
    except Exception as e:
        print(f"Error sending email: {e}")
        raise e
