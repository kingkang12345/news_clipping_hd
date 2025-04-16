import streamlit as st

# ✅ 무조건 첫 Streamlit 명령어
st.set_page_config(
    page_title="PwC 뉴스 분석기",
    page_icon="📊",
    layout="wide",
)


from news_ai import collect_news, filter_news, AgentState
import dotenv
import os
from PIL import Image
import docx
from docx.shared import Pt, RGBColor, Inches
import io
from googlenews import GoogleNews

# 환경 변수 로드
dotenv.load_dotenv()



# 워드 파일 생성 함수
def create_word_document(keyword, filtered_news, analysis):
    # 새 워드 문서 생성
    doc = docx.Document()
    
    # 제목 스타일 설정
    title = doc.add_heading(f'PwC 뉴스 분석 보고서: {keyword}', level=0)
    for run in title.runs:
        run.font.color.rgb = RGBColor(208, 74, 2)  # PwC 오렌지 색상
    
    # 분석 결과 추가
    doc.add_heading('회계법인 관점의 분석 결과', level=1)
    doc.add_paragraph(analysis)
    
    # 선별된 주요 뉴스 추가
    doc.add_heading('선별된 주요 뉴스', level=1)
    
    for i, news in enumerate(filtered_news):
        p = doc.add_paragraph()
        p.add_run(f"{i+1}. {news['content']}").bold = True
        date_str = news.get('date', '날짜 정보 없음')
        date_paragraph = doc.add_paragraph()
        date_paragraph.add_run(f"날짜: {date_str}").italic = True
        doc.add_paragraph(f"출처: {news['url']}")
    
    # 날짜 및 푸터 추가
    from datetime import datetime
    current_date = datetime.now().strftime("%Y년 %m월 %d일")
    doc.add_paragraph(f"\n보고서 생성일: {current_date}")
    doc.add_paragraph("© 2024 PwC 뉴스 분석기 | 회계법인 관점의 뉴스 분석 도구")
    
    return doc

# BytesIO 객체로 워드 문서 저장
def get_binary_file_downloader_html(doc, file_name):
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

# 커스텀 CSS
st.markdown("""
<style>
    .title-container {
        display: flex;
        align-items: center;
        gap: 20px;
        margin-bottom: 20px;
    }
    .main-title {
        color: #d04a02;
        font-size: 2.5rem;
        font-weight: 700;
    }
    .news-card {
        background-color: #f9f9f9;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 15px;
        border-left: 4px solid #d04a02;
    }
    .news-title {
        font-weight: 600;
        font-size: 1.1rem;
    }
    .news-url {
        color: #666;
        font-size: 0.9rem;
    }
    .news-date {
        color: #666;
        font-size: 0.9rem;
        font-style: italic;
        margin-top: 5px;
    }
    .analysis-box {
        background-color: #f5f5ff;
        border-radius: 10px;
        padding: 20px;
        margin: 20px 0;
        border-left: 4px solid #d04a02;
    }
    .subtitle {
        color: #dc582a;
        font-size: 1.3rem;
        font-weight: 600;
        margin-top: 20px;
        margin-bottom: 10px;
    }
    .download-box {
        background-color: #eaf7f0;
        border-radius: 10px;
        padding: 20px;
        margin: 20px 0;
        border-left: 4px solid #00a36e;
        text-align: center;
    }
    .analysis-section {
        background-color: #f8f9fa;
        border-left: 4px solid #d04a02;
        padding: 20px;
        margin: 10px 0;
        border-radius: 5px;
    }
    .selected-news {
        border-left: 4px solid #0077b6;
        padding: 15px;
        margin: 5px 0;
        background-color: #f0f8ff;
        border-radius: 5px;
    }
    .excluded-news {
        color: #666;
        padding: 5px 0;
        margin: 5px 0;
        font-size: 0.9em;
    }
    .news-meta {
        color: #666;
        font-size: 0.9em;
        margin: 3px 0;
    }
    .selection-reason {
        color: #0077b6;
        margin: 5px 0;
    }
    .keywords {
        color: #d04a02;
        font-style: italic;
        margin-top: 3px;
    }
    .news-url {
        color: #0077b6;
        font-size: 0.9em;
        margin: 3px 0;
        word-break: break-all;
    }
    .news-title-large {
        font-size: 1.4em;
        font-weight: 700;
        color: #000;
        margin: 0 0 10px 0;
        padding: 0;
        line-height: 1.3;
    }
</style>
""", unsafe_allow_html=True)

# 로고와 제목
col1, col2 = st.columns([1, 5])
with col1:
    # 로고 표시
    logo_path = "pwc_logo.png"
    if os.path.exists(logo_path):
        st.image(logo_path, width=100)
    else:
        st.error("로고 파일을 찾을 수 없습니다. 프로젝트 루트에 'pwc_logo.png' 파일을 추가해주세요.")

with col2:
    st.markdown("<h1 class='main-title'>PwC 뉴스 분석기</h1>", unsafe_allow_html=True)
    st.markdown("회계법인 관점에서 중요한 뉴스를 자동으로 분석하는 AI 도구")

# 프롬프트 템플릿 정의
CUSTOM_PROMPT_TEMPLATE = '''당신은 회계법인의 전문 애널리스트입니다. 아래 뉴스 목록을 분석하여 회계법인 관점에서 가장 중요한 뉴스를 선별하세요. 

[중요: 선택 기준]
다음 기준에 해당하는 뉴스가 있다면 반드시 선택해야 합니다:

1. 재무/실적 관련 정보 (최우선 순위)
   - 매출, 영업이익, 순이익 등 실적 발표
   - 재무제표 관련 정보
   - 주가 및 시가총액 변동
   - 배당 정책 변경

2. 회계/감사 관련 정보 (최우선 순위)
   - 회계처리 방식 변경
   - 감사의견 관련 내용
   - 내부회계관리제도
   - 회계 감리 결과

3. 기업가치 영향 정보 (높은 우선순위)
   - 대규모 투자 계획
   - 신규 사업 진출
   - 주요 계약 체결
   - 경영진 변동

4. 기업구조 변경 정보 (높은 우선순위)
   - 인수합병(M&A)
   - 자회사 설립/매각
   - 지분 변동
   - 조직 개편

[제외 대상]
다음 조건 중 하나라도 해당하는 뉴스는 즉시 제외하고, 선택하지 마십시오:

1. 스포츠/경기 관련
   - 야구단, 축구단, 구단, KBO, 프로야구, 감독, 선수 관련

2. 홍보/CSR 활동
   - 신제품 출시
   - 사회공헌/ESG 활동
   - 기부, 환경 캠페인
   - 브랜드 홍보

3. IT 시스템 관련
   - 서비스 장애/버그
   - 시스템 점검
   - 업데이트 문제

4. 기술/품질 홍보
   - 기술력 우수성
   - 품질 테스트 결과
   - 성능 비교

[응답 요구사항]
1. 반드시 최소 3개 이상의 뉴스를 선택해야 합니다.
2. 선택 기준에 부합하는 뉴스가 많다면 최대 5개까지 선택 가능합니다.
3. 선택 기준에 부합하는 뉴스가 3개 미만인 경우, 다음 순위로 중요한 뉴스를 추가 선택하여 총 3개를 채웁니다.
4. 선택 기준에 부합하는 뉴스가 없다면, 그 이유를 명확히 설명해주세요.

[응답 형식]
선택된 뉴스 인덱스: [1, 3, 5]와 같은 형식으로 알려주세요.

각 선택된 뉴스에 대해:
제목: (뉴스 제목)
언론사: (언론사명)
발행일: (발행일자)
선정 사유: (위의 선택 기준 중 어떤 항목에 해당하는지 구체적으로 설명)
관련 키워드: (재무, 회계, M&A 등 관련 키워드)

[제외된 주요 뉴스]
제외된 뉴스들 중 중요해 보이지만 제외된 뉴스에 대해:
인덱스: (뉴스 인덱스)
제목: (뉴스 제목)
제외 사유: (위의 제외 대상 중 어떤 항목에 해당하는지 구체적으로 설명)

[유효 언론사]
{유효_언론사}

[중복 처리 기준]
{중복_처리}'''

# 주요 기업 리스트 정의
COMPANIES = ["삼성", "SK", "현대차", "LG", "롯데", "포스코", "한화"]

# 사이드바 설정
st.sidebar.title("🔍 분석 설정")

# 새로운 기업 추가 섹션
new_company = st.sidebar.text_input(
    "새로운 기업 추가",
    value="",
    help="분석하고 싶은 기업명을 입력하고 Enter를 누르세요. (예: 네이버, 카카오, 현대중공업 등)"
)

# 새로운 기업 추가 로직 수정
if new_company and new_company not in COMPANIES:
    COMPANIES.append(new_company)

# 키워드 선택을 multiselect로 변경
selected_companies = st.sidebar.multiselect(
    "분석할 기업을 선택하세요 (최대 7개)",
    options=COMPANIES,
    default=COMPANIES[:7],  # 처음 7개 기업만 기본 선택으로 설정
    max_selections=7,
    help="분석하고자 하는 기업을 선택하세요. 한 번에 최대 7개까지 선택 가능합니다."
)

# 선택된 키워드를 바로 사용
keywords = selected_companies.copy()

# 구분선 추가
st.sidebar.markdown("---")

# 검색 결과 수 선택
max_results = st.sidebar.selectbox(
    "검색할 뉴스 수",
    options=[10, 20, 30, 40, 50],
    index=1,  # 기본값을 20으로 설정 (index=1)
    help="검색할 뉴스의 최대 개수를 선택하세요."
)

# 프롬프트 설정 섹션
st.sidebar.markdown("### ⚙️ 프롬프트 설정")

# 분석 관점 설정
analysis_perspective = st.sidebar.text_area(
    "💡 분석 관점",
    value="회계법인의 전문 애널리스트 관점에서 분석하여, 기업의 재무적 가치와 위험 요소를 평가합니다.",
    help="분석의 주요 관점과 목적을 설정하세요."
)

# 선택 기준 설정
selection_criteria = st.sidebar.text_area(
    "✅ 선택 기준",
    value="""다음 기준에 따라 중요한 뉴스를 선정하세요:
(1) 재무상태나 실적 관련 정보
(2) 회계 이슈나 감사 관련 정보
(3) 기업가치에 영향을 미치는 정보
(4) 투자나 인수합병(M&A), 자회사 설립, 지분 매각 관련 정보""",
    help="뉴스 선택에 적용할 주요 기준들을 나열하세요."
)

# 제외 기준 설정
exclusion_criteria = st.sidebar.text_area(
    "❌ 제외 기준",
    value="""다음 조건 중 하나라도 해당하는 뉴스는 제외하세요:

1. 경기 관련 내용
   - 스포츠단 관련 내용
   - 키워드: 야구단, 축구단, 구단, KBO, 프로야구, 감독, 선수

2. 신제품 홍보, 사회공헌, ESG, 기부 등
   - 키워드: 출시, 기부, 환경 캠페인, 브랜드 홍보, 사회공헌, 나눔, 캠페인 진행, 소비자 반응

3. 단순 시스템 장애, 버그, 서비스 오류
   - 키워드: 일시 중단, 접속 오류, 서비스 오류, 버그, 점검 중, 업데이트 실패

4. 기술 성능, 품질, 테스트 관련 보도
   - 키워드: 우수성 입증, 기술력 인정, 성능 비교, 품질 테스트, 기술 성과""",
    help="분석에서 제외할 뉴스의 기준을 설정하세요."
)

# 유효 언론사 설정
valid_press = st.sidebar.text_area(
    "📰 유효 언론사",
    value="""다음 언론사의 기사만 포함합니다:
조선일보, 중앙일보, 동아일보, 조선비즈, 한국경제, 매일경제, 연합뉴스, 파이낸셜뉴스, 데일리팜, IT조선, 
머니투데이, 비즈니스포스트, 이데일리, 아시아경제, 뉴스핌, 뉴시스, 헤럴드경제""",
    help="분석에 포함할 신뢰할 수 있는 언론사 목록을 설정하세요."
)

# 중복 처리 기준 설정
duplicate_handling = st.sidebar.text_area(
    "🔄 중복 처리 기준",
    value="""중복 뉴스가 존재할 경우 다음 우선순위로 1개만 선택하십시오:

1. 언론사 우선순위 (높은 순위부터)
   - 1순위: 경제 전문지 (한국경제, 매일경제, 조선비즈, 파이낸셜뉴스)
   - 2순위: 종합 일간지 (조선일보, 중앙일보, 동아일보)
   - 3순위: 통신사 (연합뉴스, 뉴스핌, 뉴시스)
   - 4순위: 기타 언론사

2. 발행 시간 (같은 언론사 내에서)
   - 최신 기사 우선
   - 정확한 시간 정보가 없는 경우, 날짜만 비교

3. 기사 내용의 완성도
   - 더 자세한 정보를 포함한 기사 우선
   - 주요 인용문이나 전문가 의견이 포함된 기사 우선
   - 단순 보도보다 분석적 내용이 포함된 기사 우선

4. 제목의 명확성
   - 더 구체적이고 명확한 제목의 기사 우선
   - 핵심 키워드가 포함된 제목 우선

[중복 기사 판단 기준]
1. 핵심 내용 비교
   - 주요 사실이나 정보가 90% 이상 일치하는 경우에만 중복으로 판단
   - 기사의 핵심 키워드가 4개 이상 일치하는 경우에만 중복으로 판단
   - 인용문이나 전문가 의견이 동일한 경우에만 중복으로 판단

2. 제목 유사도
   - 제목의 핵심 키워드가 3개 이상 일치하는 경우에만 중복 검토 대상
   - 제목의 구조나 표현이 매우 유사한 경우에만 중복 검토 대상

3. 예외 사항 (다음 조건 중 하나라도 해당하면 별도 기사로 처리)
   - 다른 관점이나 해석이 있는 경우
   - 추가 정보나 새로운 사실이 포함된 경우
   - 다른 전문가의 의견이 포함된 경우
   - 다른 계열사나 부서가 관련된 경우 (예: 삼성전자 vs 삼성전기)
   - 다른 제품이나 서비스가 언급된 경우 (예: 자율차 핵심소재 vs MLCC)
   - 다른 맥락이나 배경이 설명된 경우 (예: 이재용 중국 방문 성과)

[주의사항]
- 동일한 사건에 대한 후속 보도는 별도로 고려
- 각 언론사의 특성과 신뢰도를 고려하여 판단
- 기사의 객관성과 전문성을 중요하게 평가
- 중복 판단 시 기사의 전체적인 맥락과 맥락을 고려
- 비슷한 주제라도 다른 관점이나 정보가 있다면 별도 기사로 처리""",
    help="중복된 뉴스를 처리하는 기준을 설정하세요."
)

# 응답 형식 설정
response_format = st.sidebar.text_area(
    "📝 응답 형식",
    value="""선택된 뉴스 인덱스: [1, 3, 5]와 같은 형식으로 알려주세요.

각 선택된 뉴스에 대해:
제목: (뉴스 제목)
언론사: (언론사명)
발행일: (발행일자)
선정 사유: (구체적인 선정 이유)
분석 키워드: (해당 기업 그룹의 주요 계열사들)

[제외된 주요 뉴스]
제외된 중요 뉴스들에 대해:
인덱스: (뉴스 인덱스)
제목: (뉴스 제목)
제외 사유: (구체적인 제외 이유)""",
    help="분석 결과의 출력 형식을 설정하세요."
)

# 최종 프롬프트 생성
analysis_prompt = CUSTOM_PROMPT_TEMPLATE.format(
    분석_관점=analysis_perspective,
    선택_기준=selection_criteria,
    제외_기준=exclusion_criteria,
    유효_언론사=valid_press,
    중복_처리=duplicate_handling,
    응답_형식=response_format
)

# 프롬프트 미리보기
with st.sidebar.expander("🔍 최종 프롬프트 미리보기 및 수정"):
    modified_prompt = st.text_area(
        "프롬프트 직접 수정",
        value=analysis_prompt,
        height=400,
        help="생성된 프롬프트를 검토하고 필요한 경우 직접 수정할 수 있습니다."
    )
    if modified_prompt != analysis_prompt:
        analysis_prompt = modified_prompt
        st.sidebar.success("프롬프트가 수정되었습니다!")

st.sidebar.markdown("""
### 분석 기준
- 재무상태 및 실적 정보
- 회계 이슈 및 감사 정보
- 기업가치 평가 관련 정보
- 투자 및 인수합병 소식
""")

# 메인 컨텐츠
if st.button("뉴스 분석 시작", type="primary"):
    for keyword in keywords:
        with st.spinner(f"'{keyword}' 관련 뉴스를 수집하고 분석 중입니다..."):
            # 각 키워드별 상태 초기화
            initial_state = {
                "news_data": [], 
                "filtered_news": [], 
                "analysis": "", 
                "keyword": keyword, 
                "prompt": analysis_prompt,
                "max_results": max_results
            }
            
            # 뉴스 수집 및 분석
            state_after_collection = collect_news(initial_state)
            final_state = filter_news(state_after_collection)
            
            # 키워드별 섹션 구분
            st.markdown(f"## 📊 {keyword} 분석 결과")
            
            # 전체 뉴스 표시
            with st.expander(f"📰 '{keyword}' 관련 전체 뉴스"):
                for i, news in enumerate(final_state["news_data"]):
                    date_str = news.get('date', '날짜 정보 없음')
                    st.markdown(f"""
                    <div class="news-card">
                        <div class="news-title">{i+1}. {news['content']}</div>
                        <div class="news-date">📅 {date_str}</div>
                        <div class="news-url">🔗 <a href="{news['url']}" target="_blank">{news['url']}</a></div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # 분석 결과 표시
            st.markdown("<div class='subtitle'>🔍 회계법인 관점의 분석 결과</div>", unsafe_allow_html=True)

            # 분석 결과를 파싱하여 구조화된 형태로 표시
            analysis_text = final_state["analysis"]

            # 디버그 섹션 추가
            with st.expander("🔧 LLM 원본 답변 (디버그용)"):
                st.text_area(
                    "LLM의 원본 답변",
                    value=analysis_text,
                    height=300,
                    help="LLM이 생성한 원본 답변입니다. 디버깅 목적으로만 사용하세요."
                )

            # 선택된 뉴스 처리
            if "선택된 뉴스" in analysis_text:
                selected_news = analysis_text.split("선택된 뉴스:")[1].split("제외된 주요 뉴스:")[0]
                st.markdown("### ⭐ 선택된 주요 뉴스")
                
                # 각 뉴스 항목 처리
                news_items = selected_news.strip().split("\n\n")
                for i, item in enumerate(news_items):
                    if not item.strip():
                        continue
                    
                    # 각 뉴스 항목의 모든 내용을 하나의 문자열로 구성
                    news_content = []
                    
                    # 제목과 메타 정보
                    if "제목:" in item:
                        title = item.split("제목:")[1].split("언론사:")[0].strip()
                        index = item.split("인덱스:")[1].split("제목:")[0].strip() if "인덱스:" in item else ""
                        title_with_index = f"[{index}] {title}" if index else title
                        news_content.append(f"<div class='news-title-large'>{title_with_index}</div>")
                        
                        # 메타 정보 (언론사, 발행일)
                        meta = []
                        if "언론사:" in item:
                            press = item.split("언론사:")[1].split("발행일:")[0].strip()
                            meta.append(f"📰 {press}")
                        if "발행일:" in item:
                            date = item.split("발행일:")[1].split("선정 사유:")[0].strip()
                            meta.append(f"📅 {date}")
                        if meta:
                            news_content.append(f"<div class='news-meta'>{' | '.join(meta)}</div>")
                        
                        # URL 추가
                        for news in final_state["filtered_news"]:
                            if news['content'] == title:
                                news_content.append(f"<div class='news-url'>🔗 <a href='{news['url']}' target='_blank'>{news['url']}</a></div>")
                                break
                        
                        # 선정 사유
                        if "선정 사유:" in item:
                            reason = item.split("선정 사유:")[1].split("관련 키워드:")[0].strip()
                            news_content.append(f"<div class='selection-reason'>💡 {reason}</div>")
                        
                        # 키워드
                        if "관련 키워드:" in item:
                            keywords = item.split("관련 키워드:")[1].strip()
                            news_content.append(f"<div class='keywords'>🏷️ {keywords}</div>")
                    
                    # 모든 내용을 하나의 파란색 박스로 감싸기
                    st.markdown(
                        f"<div class='selected-news'>{' '.join(news_content)}</div>",
                        unsafe_allow_html=True
                    )

            # 제외된 뉴스 처리
            if "제외된 주요 뉴스:" in analysis_text:
                excluded_news = analysis_text.split("제외된 주요 뉴스:")[1]
                st.markdown("### ❌ 제외된 뉴스")
                
                excluded_items = excluded_news.strip().split("\n\n")
                for item in excluded_items:
                    if not item.strip() or "인덱스:" not in item or "제목:" not in item:
                        continue
                    
                    index = item.split("인덱스:")[1].split("제목:")[0].strip()
                    title = item.split("제목:")[1].split("제외 사유:")[0].strip()
                    reason = item.split("제외 사유:")[1].strip() if "제외 사유:" in item else ""
                    
                    st.markdown(f"<div class='excluded-news'>[{index}] {title}<br/>└ {reason}</div>", unsafe_allow_html=True)
            
            # 워드 파일 다운로드
            st.markdown("<div class='subtitle'>📥 보고서 다운로드</div>", unsafe_allow_html=True)
            doc = create_word_document(keyword, final_state["filtered_news"], final_state["analysis"])
            docx_bytes = get_binary_file_downloader_html(doc, f"PwC_{keyword}_뉴스분석.docx")
            st.download_button(
                label=f"📎 {keyword} 분석 보고서 다운로드",
                data=docx_bytes,
                file_name=f"PwC_{keyword}_뉴스분석.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            
            # 키워드 구분선 추가
            st.markdown("---")
else:
    # 초기 화면 설명
    st.markdown("""
    ### 👋 PwC 뉴스 분석기에 오신 것을 환영합니다!
    
    이 도구는 입력한 키워드에 대한 최신 뉴스를 자동으로 수집하고, 회계법인 관점에서 중요한 뉴스를 선별하여 분석해드립니다.
    
    #### 주요 기능:
    1. 최신 뉴스 자동 수집 (언론사 필터링 시 최대 20개, 필터링 미사용 시 최대 30개)
    2. AI 기반 뉴스 중요도 분석
    3. 회계법인 관점의 주요 뉴스 선별 (상위 3개)
    4. 선별된 뉴스에 대한 전문가 분석
    5. 분석 결과 워드 문서로 다운로드
    
    시작하려면 사이드바에서 키워드를 입력하고 "뉴스 분석 시작" 버튼을 클릭하세요.
    """)

# 푸터
st.markdown("---")
st.markdown("© 2024 PwC 뉴스 분석기 | 회계법인 관점의 뉴스 분석 도구")

def collect_news(state):
    """뉴스를 수집하고 state를 업데이트하는 함수"""
    try:
        # 검색어 설정
        keyword = state.get("keyword", "삼성전자")
        
        # 검색 결과 수 설정
        max_results = state.get("max_results", 20)
        
        # GoogleNews 객체 생성
        news = GoogleNews()
        
        # 뉴스 검색
        news_data = news.search_by_keyword(keyword, k=max_results)
        
        # 수집된 뉴스가 없는 경우
        if not news_data:
            st.error("수집된 뉴스가 없습니다. 다른 키워드로 시도해보세요.")
            return state
        
        # state 업데이트
        state["news_data"] = news_data
        state["filtered_news"] = news_data
        
        return state
        
    except Exception as e:
        st.error(f"뉴스 수집 중 오류가 발생했습니다: {str(e)}")
        return state
