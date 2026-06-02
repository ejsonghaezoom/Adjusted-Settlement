import pandas as pd

class SettlementCalcEngine:
    def __init__(self, excel_file):
        self.excel_file = excel_file
        
    def execute_pipeline(self):
        # 1. 수신처 이메일 매핑
        df_biz = pd.read_excel(self.excel_file, sheet_name="사업자정보")
        email_mapping = dict(zip(df_biz['발전소명'], df_biz['메일 주소']))
        
        # 2. 월별 변경 내역 계산
        df_monthly_orig = pd.read_excel(self.excel_file, sheet_name="기존_월별")
        df_monthly_rev = pd.read_excel(self.excel_file, sheet_name="수정_월별")
        monthly_diff = self._calculate_monthly_diff(df_monthly_orig, df_monthly_rev)
        
        # 3. 일별 변경 내역 계산 및 정렬
        df_daily_orig = pd.read_excel(self.excel_file, sheet_name="기존_일별")
        df_daily_rev = pd.read_excel(self.excel_file, sheet_name="수정_일별")
        daily_diff_dataset = self._calculate_daily_diff(df_daily_orig, df_daily_rev)
        
        return email_mapping, monthly_diff, daily_diff_dataset

    def _calculate_monthly_diff(self, orig, rev):
        merged = pd.merge(orig, rev, on=["년", "월", "발전소명"], suffixes=('_기존', '_수정'))
        diff_results = {}
        for _, row in merged.iterrows():
            plant = row["발전소명"]
            diff_results[plant] = {
                "전력량정산금_차이": row.get("전력량정산금_수정", 0) - row.get("전력량정산금_기존", 0),
                "해줌보상금_차이": row.get("해줌보상금_수정", 0) - row.get("해줌보상금_기존", 0),
                "추가지급금_차이": row.get("추가지급금\\n(예측제도인센)_수정", 0) - row.get("추가지급금\\n(예측제도인센)_기존", 0),
                "전력거래수수료_차이": row.get("전력거래 \\n수수료_수정", 0) - row.get("전력거래 \\n수수료_기존", 0)
            }
        return diff_results

    def _calculate_daily_diff(self, orig, rev):
        orig['구분'] = '기존'
        rev['구분'] = '수정'
        
        for df in [orig, rev]:
            df['Date'] = pd.to_datetime(df['일시']).dt.date
            df['Hour'] = pd.to_datetime(df['일시']).dt.hour
            
        diff = rev.copy()
        diff['구분'] = '차이'
        
        numeric_cols = [
            '계량발전량\\n(kWh)', '감발량\\n(kWh)', '감발량정산금(a)\\n(원)', 
            '전력량정산금', '추가지급금\\n(예측인센티브)', '고객정산금'
        ]
        
        for col in numeric_cols:
            if col in diff.columns and col in orig.columns:
                diff[col] = pd.to_numeric(rev[col], errors='coerce').fillna(0) - pd.to_numeric(orig[col], errors='coerce').fillna(0)
                
        combined = pd.concat([orig, rev, diff], ignore_index=True)
        combined['구분'] = pd.Categorical(combined['구분'], categories=['기존', '수정', '차이'], ordered=True)
        combined = combined.sort_values(by=['발전소명', 'Date', 'Hour', '구분'])
        
        return combined.drop(columns=['Date', 'Hour'])
