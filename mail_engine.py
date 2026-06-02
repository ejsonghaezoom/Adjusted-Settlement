import os
import base64
from email.message import EmailMessage
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

class AutomationMailEngine:
    def __init__(self, google_creds):
        self.creds = google_creds
        # Initialize Google APIs (Drive, Gmail)
        self.gmail_service = build('gmail', 'v1', credentials=self.creds)
        self.drive_service = build('drive', 'v3', credentials=self.creds)

    def upload_to_drive(self, file_path, folder_id):
        file_name = os.path.basename(file_path)
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        
        # Determine mimetype based on extension
        mime_type = 'application/pdf' if file_path.endswith('.pdf') else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        
        uploaded_file = self.drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        print(f"[{file_path}] -> Drive Folder[{folder_id}] Uploaded (ID: {uploaded_file.get('id')})")
        return uploaded_file.get('id')

    def send_settlement_email(self, sender, recipient, cc, plant_name, period_str, reason, attachments):
        subject = f"[해줌] {period_str} 전력거래대금 수정정산 안내의 건_{plant_name}"
        body = f"""안녕하십니까,
(주)해줌 VPP운영팀입니다.

[{period_str}] {reason}으로 인한 전력거래대금 수정정산내역서 전달드리오니,
첨부된 파일과 수신받으신 역발행 세금계산서 이메일 확인 후 세금계산서 발행 승인 부탁드립니다.

정발행 진행하시는 경우, 내역에 맞게 세금계산서 발행을 요청 드립니다.

감사합니다.
해줌 드림."""

        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = recipient
        if cc:
            msg['Cc'] = cc

        for filepath in attachments:
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    file_data = f.read()
                    file_name = os.path.basename(filepath)
                # Determine subtype
                subtype = 'pdf' if filepath.endswith('.pdf') else 'vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                msg.add_attachment(file_data, maintype='application', subtype=subtype, filename=file_name)

        # Gmail API Send Logic
        raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        self.gmail_service.users().messages().send(
            userId='me', 
            body={'raw': raw_msg}
        ).execute()
        
        print(f"[{recipient}] 으로 메일 발송 완료")
        return True
