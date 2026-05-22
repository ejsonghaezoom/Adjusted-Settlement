import pandas as pd

def process_settlement_data(df_orig: pd.DataFrame, df_rev: pd.DataFrame) -> pd.DataFrame:
    """
    기존 정산 데이터와 수정 정산 데이터를 병합하고 차액을 계산합니다.
    """
    keys = ['일시', '시간', '발전기코드', '발전소명']
    value_cols = [
        '계량발전량(kWh)', '감발량(kWh)', '적용SMP(원/kW)',
        '전력량정산금', '감발량정산금(원)', '추가지급금(예측인센티브)', '고객정산금'
    ]
    
    # 필요한 컬럼만 추출하고 숫자형으로 변환
    for col in value_cols:
        if col in df_orig.columns:
            df_orig[col] = pd.to_numeric(df_orig[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        else:
            df_orig[col] = 0
            
        if col in df_rev.columns:
            df_rev[col] = pd.to_numeric(df_rev[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        else:
            df_rev[col] = 0

    df_orig = df_orig[keys + value_cols].copy()
    df_rev = df_rev[keys + value_cols].copy()
    
    df_orig['구분'] = '기존'
    df_rev['구분'] = '수정'
    
    # 두 데이터 프레임을 하나로 합치고 정렬을 위해 임시 인덱스 생성
    df_combined = pd.merge(df_orig, df_rev, on=keys, suffixes=('_orig', '_rev'), how='outer')
    
    result_rows = []
    
    for _, row in df_combined.iterrows():
        base_info = {k: row[k] for k in keys}
        
        # 기존 행
        row_orig = base_info.copy()
        row_orig['구분'] = '기존'
        for col in value_cols:
            row_orig[col] = row.get(f'{col}_orig', 0)
            if pd.isna(row_orig[col]):
                row_orig[col] = 0
                
        # 수정 행
        row_rev = base_info.copy()
        row_rev['구분'] = '수정'
        for col in value_cols:
            row_rev[col] = row.get(f'{col}_rev', 0)
            if pd.isna(row_rev[col]):
                row_rev[col] = 0
                
        # 차이 행
        row_diff = base_info.copy()
        row_diff['구분'] = '차이'
        for col in value_cols:
            row_diff[col] = row_rev[col] - row_orig[col]
            
        result_rows.extend([row_orig, row_rev, row_diff])
        
    df_final = pd.DataFrame(result_rows)
    
    # 컬럼 순서 재배치
    cols_order = ['구분'] + keys + value_cols
    df_final = df_final[cols_order]
    
    return df_final

def get_summary_from_diff(df_final: pd.DataFrame) -> dict:
    """
    차이 행에서 필요한 요약 정보를 추출합니다. (PDF 렌더링용)
    """
    df_diff = df_final[df_final['구분'] == '차이']
    
    summary = {}
    summary['총_차액'] = df_diff['고객정산금'].sum()
    summary['전력량정산금_차액'] = df_diff['전력량정산금'].sum()
    summary['추가지급금_차액'] = df_diff['추가지급금(예측인센티브)'].sum()
    
    # 간단한 부가세 계산 (공급가액, VAT) - 실제 비즈니스 로직에 맞게 조정 필요
    summary['공급가액'] = round(summary['총_차액'] / 1.1)
    summary['VAT'] = summary['총_차액'] - summary['공급가액']
    
    summary['총_계량발전량_차액'] = df_diff['계량발전량(kWh)'].sum()
    summary['총_제어량_차액'] = df_diff['감발량(kWh)'].sum()
    summary['데이터_개수'] = len(df_diff)
    
    # 일시(시작일-종료일)
    if '일시' in df_diff.columns and not df_diff['일시'].empty:
        dates = pd.to_datetime(df_diff['일시'], errors='coerce').dropna()
        if not dates.empty:
            summary['시작일'] = dates.min().strftime('%Y-%m-%d')
            summary['종료일'] = dates.max().strftime('%Y-%m-%d')
        else:
            summary['시작일'] = '-'
            summary['종료일'] = '-'
    else:
        summary['시작일'] = '-'
        summary['종료일'] = '-'
        
    # 첫번째 발전소명 추출
    if '발전소명' in df_diff.columns and not df_diff['발전소명'].empty:
        summary['발전소명'] = df_diff['발전소명'].iloc[0]
    else:
        summary['발전소명'] = '알 수 없음'
        
    return summary
