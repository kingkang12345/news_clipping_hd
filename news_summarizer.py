import streamlit as st
import requests
from urllib.parse import urlparse
from web_scraper import HybridNewsWebScraper
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import os
import time
import re
from datetime import datetime

# 페이지 설정
st.set_page_config(
    page_title="뉴스 요약기",
    page_icon="📰",
    layout="wide",
)

# 환경변수 로드
import dotenv
dotenv.load_dotenv(override=True)

def clean_html_tags(text: str) -> str:
    """HTML 태그를 제거하고 깔끔한 텍스트로 변환"""
    if not text:
        return ""
    
    # HTML 태그 제거
    text = re.sub(r'<[^>]+>', '', text)
    
    # HTML 엔티티 변환
    html_entities = {
        '&amp;': '&',
        '&lt;': '<',
        '&gt;': '>',
        '&quot;': '"',
        '&#39;': "'",
        '&nbsp;': ' '
    }
    
    for entity, char in html_entities.items():
        text = text.replace(entity, char)
    
    # 연속된 공백과 줄바꿈 정리
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    return text.strip()

def generate_summary(content: str, title: str) -> str:
    """AI를 사용해 기사 요약 생성"""
    try:
        summary_prompt = f"""
다음 뉴스 기사를 현대자동차 남양연구소 PT/전동화 개발 인력 관점에서 요약해주세요.

[기사 제목]
{title}

[기사 본문]
{content}

[요약 요구사항]
1. 핵심 내용을 3-5문장으로 요약
2. 기술적 세부사항이 있다면 구체적으로 언급
3. 현대차그룹에 미치는 영향이나 시사점 포함
4. 지역별 동향이라면 해당 지역의 특성 언급

[응답 형식]
• 핵심 요약: (3-5문장으로 핵심 내용 요약)

• 기술적 세부사항: (기술 관련 구체적 내용이 있다면)

• 시사점: (현대차그룹 관점에서의 의미)

[중요] HTML 태그는 절대 사용하지 마세요. 일반 텍스트로만 응답하세요.
"""
        
        try:
            llm = ChatOpenAI(
                model="gpt-4.1",
                temperature=0.3,
                request_timeout=30,
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                openai_api_base=os.getenv("OPENAI_BASE_URL")
            )
            
            messages = [
                SystemMessage(content="당신은 자동차 산업 분석 전문가입니다. 뉴스 기사를 현대자동차 연구개발 관점에서 요약하는 작업을 수행합니다."),
                HumanMessage(content=summary_prompt)
            ]
            
            response = llm.invoke(messages)
            return clean_html_tags(response.content)
            
        except Exception as e:
            st.error(f"AI 요약 생성 실패: {e}")
            return f"요약 생성 실패: {str(e)}"
        
    except Exception as e:
        return f"요약 생성 실패: {str(e)}"

def parse_news_list(news_text: str):
    """뉴스 리스트 텍스트를 파싱하여 개별 뉴스로 분리"""
    news_items = []
    lines = news_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 다양한 형식 지원
        # 1. "제목 - 언론사 (URL)" 형식
        # 2. "제목 (URL)" 형식  
        # 3. "제목 URL" 형식
        # 4. 단순 URL만 있는 경우
        
        if line.startswith('http'):
            # URL만 있는 경우
            news_items.append({
                'title': '',
                'url': line,
                'press': ''
            })
        elif '(' in line and ')' in line and 'http' in line:
            # "제목 - 언론사 (URL)" 또는 "제목 (URL)" 형식
            url_start = line.rfind('(http')
            url_end = line.rfind(')')
            
            if url_start != -1 and url_end != -1:
                url = line[url_start+1:url_end]
                title_part = line[:url_start].strip()
                
                # 언론사 분리 시도
                if ' - ' in title_part:
                    title, press = title_part.rsplit(' - ', 1)
                    title = title.strip()
                    press = press.strip()
                else:
                    title = title_part
                    press = ''
                
                news_items.append({
                    'title': title,
                    'url': url,
                    'press': press
                })
        elif 'http' in line:
            # "제목 URL" 형식
            parts = line.split()
            url = None
            for part in parts:
                if part.startswith('http'):
                    url = part
                    break
            
            if url:
                title = line.replace(url, '').strip()
                news_items.append({
                    'title': title,
                    'url': url,
                    'press': ''
                })
        else:
            # URL이 없는 경우 - 제목만
            news_items.append({
                'title': line,
                'url': '',
                'press': ''
            })
    
    return news_items

# CSS 스타일
st.markdown("""
<style>
    .news-card {
        background-color: #f9f9f9;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
        border-left: 4px solid #d04a02;
    }
    .news-title {
        font-weight: 600;
        font-size: 1.2rem;
        color: #333;
        margin-bottom: 10px;
    }
    .news-url {
        color: #0077b6;
        font-size: 0.9rem;
        margin: 5px 0;
        word-break: break-all;
    }
    .news-summary {
        background-color: #f0f8ff;
        border-radius: 8px;
        padding: 15px;
        margin-top: 15px;
        border-left: 3px solid #0077b6;
    }
    .error-message {
        background-color: #ffe6e6;
        border-radius: 8px;
        padding: 15px;
        margin-top: 15px;
        border-left: 3px solid #ff4444;
        color: #cc0000;
    }
    .success-message {
        background-color: #e6ffe6;
        border-radius: 8px;
        padding: 15px;
        margin-top: 15px;
        border-left: 3px solid #00aa00;
        color: #006600;
    }
</style>
""", unsafe_allow_html=True)

# 메인 UI
st.title("📰 뉴스 요약기")
st.markdown("Google 뉴스 리스트를 입력하면 각 기사를 요약해드립니다.")

# 사이드바 설정
st.sidebar.title("⚙️ 설정")

# 요약 옵션
summary_mode = st.sidebar.selectbox(
    "요약 모드",
    ["자동차/전동화 관점", "일반 요약"],
    help="요약 관점을 선택하세요"
)

# 최대 기사 수 설정
max_articles = st.sidebar.slider(
    "최대 요약 기사 수",
    min_value=1,
    max_value=20,
    value=10,
    help="한 번에 요약할 최대 기사 수를 설정하세요"
)

# 뉴스 리스트 입력
st.markdown("### 📋 뉴스 리스트 입력")
news_input = st.text_area(
    "뉴스 리스트를 입력하세요",
    placeholder="""예시:
Toyota Reinvents the Hybrid: Triple-Fuel Prius Aims at Carbon Cuts - MSN (https://example.com/news1)
Ford's $5.8 Billion EV Battery Plant In Kentucky Powers Up (https://example.com/news2)
https://example.com/news3
Hyundai Motor to up ante in US with full hybrid lineup in 2026""",
    height=200
)

if st.button("🚀 요약 시작", type="primary"):
    if not news_input.strip():
        st.error("뉴스 리스트를 입력해주세요.")
    else:
        # 뉴스 리스트 파싱
        news_items = parse_news_list(news_input)
        
        if not news_items:
            st.error("유효한 뉴스를 찾을 수 없습니다.")
        else:
            st.success(f"총 {len(news_items)}개의 뉴스를 발견했습니다.")
            
            # 최대 기사 수 제한
            if len(news_items) > max_articles:
                news_items = news_items[:max_articles]
                st.warning(f"설정된 최대 기사 수({max_articles}개)로 제한합니다.")
            
            # 웹 스크래퍼 초기화
            scraper = HybridNewsWebScraper(
                openai_api_key=os.getenv('OPENAI_API_KEY'),
                enable_ai_fallback=True
            )
            
            # 각 뉴스 처리
            progress_bar = st.progress(0)
            
            for i, news_item in enumerate(news_items):
                progress_bar.progress((i + 1) / len(news_items))
                
                title = news_item['title'] or "제목 없음"
                url = news_item['url']
                press = news_item['press'] or "언론사 정보 없음"
                
                st.markdown(f"""
                <div class="news-card">
                    <div class="news-title">{i+1}. {title}</div>
                    <div style="color: #666; font-size: 0.9rem;">📰 {press}</div>
                    <div class="news-url">🔗 <a href="{url}" target="_blank">{url}</a></div>
                """, unsafe_allow_html=True)
                
                if url:
                    with st.spinner(f"기사 {i+1} 요약 중..."):
                        # 원문 추출
                        extraction_result = scraper.extract_content(url, timeout=15)
                        
                        if extraction_result.success and extraction_result.content:
                            # AI 요약 생성
                            summary = generate_summary(extraction_result.content, title)
                            
                            st.markdown(f"""
                                <div class="news-summary">
                                    <strong>🤖 AI 요약:</strong><br>
                                    {summary.replace(chr(10), '<br>')}
                                </div>
                            """, unsafe_allow_html=True)
                            
                            st.markdown(f"""
                                <div class="success-message">
                                    ✅ 요약 완료 (방법: {extraction_result.method.value}, 
                                    소요시간: {extraction_result.extraction_time:.1f}초)
                                </div>
                            """, unsafe_allow_html=True)
                            
                        else:
                            error_msg = extraction_result.error_message if extraction_result else "알 수 없는 오류"
                            st.markdown(f"""
                                <div class="error-message">
                                    ❌ 원문 추출 실패: {error_msg}
                                </div>
                            """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                        <div class="error-message">
                            ❌ URL이 없어서 요약할 수 없습니다.
                        </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("</div>", unsafe_allow_html=True)
                st.markdown("---")
                
                # 요청 간 지연 (서버 부하 방지)
                if i < len(news_items) - 1:
                    time.sleep(1)
            
            progress_bar.progress(1.0)
            st.success("모든 기사 요약이 완료되었습니다! 🎉")

# 사용법 안내
with st.expander("📖 사용법 안내"):
    st.markdown("""
    ### 지원하는 입력 형식:
    
    1. **완전한 형식**: `제목 - 언론사 (URL)`
       ```
       Toyota Reinvents the Hybrid - MSN (https://example.com/news1)
       ```
    
    2. **제목과 URL**: `제목 (URL)`
       ```
       Ford's EV Battery Plant Powers Up (https://example.com/news2)
       ```
    
    3. **제목과 URL 분리**: `제목 URL`
       ```
       Hyundai Motor hybrid lineup https://example.com/news3
       ```
    
    4. **URL만**: 
       ```
       https://example.com/news4
       ```
    
    ### 팁:
    - 한 줄에 하나의 뉴스를 입력하세요
    - Google 뉴스에서 복사한 내용을 그대로 붙여넣기 하면 됩니다
    - 최대 20개까지 한 번에 처리 가능합니다
    - 각 기사는 현대자동차 PT/전동화 관점에서 요약됩니다
    """)

# 푸터
st.markdown("---")
st.markdown("© 2024 뉴스 요약기 | 현대자동차 남양연구소 PT/전동화 팀 전용")
