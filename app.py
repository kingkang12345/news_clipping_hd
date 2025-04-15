import streamlit as st
from news_ai import collect_news, filter_news, AgentState
import dotenv
import os
from PIL import Image
import docx
from docx.shared import Pt, RGBColor, Inches
import io
import streamlit as st



# 환경 변수 로드
dotenv.load_dotenv()

# 페이지 설정
st.set_page_config(
    page_title="PwC 뉴스 분석기",
    page_icon="📊",
    layout="wide",
)

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

# 사이드바 설정
st.sidebar.title("🔍 분석 설정")

# 키워드 입력
keyword = st.sidebar.text_input("분석할 키워드를 입력하세요", value="삼성전자")

# 프롬프트 입력
st.sidebar.markdown("### 분석 프롬프트")
default_prompt = """당신은 회계법인의 전문 애널리스트입니다. 다음 뉴스들을 분석해서 회계법인 관점에서 가장 중요한 3개의 뉴스를 선택해주세요.

선택 기준:
1. 재무상태나 실적 관련 정보
2. 회계 이슈나 감사 관련 정보
3. 기업가치 평가에 영향을 미치는 정보
4. 투자나 인수합병 관련 정보

각 선택한 뉴스에 대해 선택한 이유를 명확히 설명해주세요.

응답 형식:
선택된 뉴스 인덱스: [1, 2, 3] 와 같은 형식으로 먼저 알려주세요.
그 다음 각 선택에 대한 이유를 설명해주세요."""

analysis_prompt = st.sidebar.text_area("분석 프롬프트를 수정하세요", value=default_prompt, height=300)

st.sidebar.markdown("""
### 분석 기준
- 재무상태 및 실적 정보
- 회계 이슈 및 감사 정보
- 기업가치 평가 관련 정보
- 투자 및 인수합병 소식
""")

# 메인 컨텐츠
if st.button("뉴스 분석 시작", type="primary"):
    with st.spinner("뉴스를 수집하고 분석 중입니다..."):
        # 초기 상태 설정
        initial_state = {"news_data": [], "filtered_news": [], "analysis": "", "keyword": keyword, "prompt": analysis_prompt}
        
        # 뉴스 수집
        state_after_collection = collect_news(initial_state)
        
        # 뉴스 필터링 및 분석
        final_state = filter_news(state_after_collection)
        
        # 전체 뉴스 표시
        st.markdown(f"<div class='subtitle'>📰 '{keyword}' 관련 전체 뉴스</div>", unsafe_allow_html=True)
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
        st.markdown(f"""
        <div class="analysis-box">
            {final_state["analysis"]}
        </div>
        """, unsafe_allow_html=True)
        
        # 선별된 주요 뉴스 표시
        st.markdown("<div class='subtitle'>⭐ 선별된 주요 뉴스</div>", unsafe_allow_html=True)
        for i, news in enumerate(final_state["filtered_news"]):
            date_str = news.get('date', '날짜 정보 없음')
            st.markdown(f"""
            <div class="news-card">
                <div class="news-title">{i+1}. {news['content']}</div>
                <div class="news-date">📅 {date_str}</div>
                <div class="news-url">🔗 <a href="{news['url']}" target="_blank">{news['url']}</a></div>
            </div>
            """, unsafe_allow_html=True)
        
        # 워드 파일 다운로드 기능 추가
        st.markdown("<div class='subtitle'>📥 보고서 다운로드</div>", unsafe_allow_html=True)
        st.markdown("""
        <div class="download-box">
            <p>분석 결과와 선별된 뉴스를 워드 문서로 다운로드할 수 있습니다.</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 워드 문서 생성
        doc = create_word_document(keyword, final_state["filtered_news"], final_state["analysis"])
        
        # 다운로드 버튼
        docx_bytes = get_binary_file_downloader_html(doc, f"PwC_{keyword}_뉴스분석.docx")
        st.download_button(
            label="📎 워드 문서로 다운로드",
            data=docx_bytes,
            file_name=f"PwC_{keyword}_뉴스분석.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
else:
    # 초기 화면 설명
    st.markdown("""
    ### 👋 PwC 뉴스 분석기에 오신 것을 환영합니다!
    
    이 도구는 입력한 키워드에 대한 최신 뉴스를 자동으로 수집하고, 회계법인 관점에서 중요한 뉴스를 선별하여 분석해드립니다.
    
    #### 주요 기능:
    1. 최신 뉴스 자동 수집 (최대 10개)
    2. AI 기반 뉴스 중요도 분석
    3. 회계법인 관점의 주요 뉴스 선별 (상위 3개)
    4. 선별된 뉴스에 대한 전문가 분석
    5. 분석 결과 워드 문서로 다운로드
    
    시작하려면 사이드바에서 키워드를 입력하고 "뉴스 분석 시작" 버튼을 클릭하세요.
    """)

# 푸터
st.markdown("---")
st.markdown("© 2024 PwC 뉴스 분석기 | 회계법인 관점의 뉴스 분석 도구")
