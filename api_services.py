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

def read_google_sheet(url: str, creds_dict: dict, tab_name: str = '고객 정산금(일별)') -> pd.DataFrame:
    """
    주어진 구글 시트 URL에서 특정 탭의 데이터를 읽어옵니다.
    (사용자 요청에 따라 3번째 행부터 컬럼 제목으로 인식하고, 4번째 행부터 데이터를 읽어옵니다.)
    """
    creds = get_google_credentials(creds_dict)
    client = gspread.authorize(creds)
    
    # URL에서 스프레드시트 열기
    sheet = client.open_by_url(url)
    
    try:
        worksheet = sheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        try:
            alt_name = '고객정산금(일별)' if tab_name == '고객 정산금(일별)' else '고객 정산금(일별)'
            worksheet = sheet.worksheet(alt_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet.get_worksheet(0)
    
    # 전체 데이터를 리스트 형식으로 가져옵니다.
    all_values = worksheet.get_all_values()
    
    # 안전장치: 데이터가 3줄보다 적으면 빈 데이터프레임 반환
    if len(all_values) < 3:
        return pd.DataFrame()
        
    # [핵심 수정] 3번째 행(파이썬 인덱스 기준 2)을 컬럼 제목(헤더)으로 지정합니다.
    raw_headers = all_values[2]
    processed_headers = []
    
    for i, h in enumerate(raw_headers):
        h_str = str(h).strip()
        if not h_str:
            processed_headers.append(f"빈컬럼_{i}")
        else:
            processed_headers.append(h_str)
            
    # 제목 중복 방지 로직
    final_headers = []
    seen_counts = {}
    for h in processed_headers:
        if h in seen_counts:
            seen_counts[h] += 1
            final_headers.append(f"{h}_{seen_counts[h]}")
        else:
            seen_counts[h] = 0
            final_headers.append(h)
            
    # [핵심 수정] 실제 데이터는 4번째 행(파이썬 인덱스 기준 3)부터 끝까지 가져옵니다.
    df = pd.DataFrame(all_values[3:], columns=final_headers)
    return df
    
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