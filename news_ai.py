from typing import List, Dict, Any, TypedDict
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from googlenews import GoogleNews
from web_scraper import NewsWebScraper
import operator
import dotenv
import json
import re
import os
from datetime import datetime, timedelta, timezone
import streamlit as st
import time
from urllib.parse import urlparse

import dotenv #pwc
dotenv.load_dotenv(override=True) #pwc

# 한국 시간대(KST) 정의
KST = timezone(timedelta(hours=9))

# 상태 타입 정의
class AgentState(TypedDict):
    news_data: List[dict]
    filtered_news: List[dict]
    analysis: str
    keyword: str
    system_prompt: str
    user_prompt: str
    excluded_news: List[dict]
    borderline_news: List[dict]
    retained_news: List[dict]
    grouped_news: List[dict]
    final_selection: List[dict]
    system_prompt_1: str
    user_prompt_1: str
    llm_response_1: str
    system_prompt_2: str
    user_prompt_2: str
    llm_response_2: str
    system_prompt_3: str
    user_prompt_3: str
    llm_response_3: str
    not_selected_news: List[dict]
    original_news_data: List[dict]
    start_datetime: datetime
    end_datetime: datetime

# 신뢰할 수 있는 언론사 목록 (기본값으로만 사용)
TRUSTED_PRESS_ALIASES = {
    "조선일보": ["조선일보", "chosun", "chosun.com"],
    "중앙일보": ["중앙일보", "joongang", "joongang.co.kr", "joins.com"],
    "동아일보": ["동아일보", "donga", "donga.com"],
    "조선비즈": ["조선비즈", "chosunbiz", "biz.chosun.com"],
    "한국경제": ["한국경제", "한경", "hankyung", "hankyung.com", "한경닷컴"],
    "매일경제": ["매일경제", "매경", "mk", "mk.co.kr"],
    "연합뉴스": ["연합뉴스", "yna", "yna.co.kr"],
    "파이낸셜뉴스": ["파이낸셜뉴스", "fnnews", "fnnews.com"],
    "데일리팜": ["데일리팜", "dailypharm", "dailypharm.com"],
    "IT조선": ["it조선", "it.chosun.com", "itchosun"],
    "머니투데이": ["머니투데이", "mt", "mt.co.kr"],
    "비즈니스포스트": ["비즈니스포스트", "businesspost", "businesspost.co.kr"],
    "이데일리": ["이데일리", "edaily", "edaily.co.kr"],
    "아시아경제": ["아시아경제", "asiae", "asiae.co.kr"],
    "뉴스핌": ["뉴스핌", "newspim", "newspim.com"],
    "뉴시스": ["뉴시스", "newsis", "newsis.com"],
    "헤럴드경제": ["헤럴드경제", "herald", "heraldcorp", "heraldcorp.com"]
}

# 헬퍼 함수: LLM 호출
def call_llm(state: AgentState, system_prompt: str, user_prompt: str, stage: int = 1) -> str:
    """LLM을 호출하고 응답을 반환하는 함수"""
    try:
        # LLM 초기화
        llm = ChatOpenAI(
           # openai_api_key=os.getenv("OPENAI_API_KEY"), #pwc
            #openai_api_base=os.getenv("OPENAI_BASE_URL"), #pwc
            #model_name = "openai.gpt-4.1-2025-04-14",
            model_name=state.get("model", "gpt-5"),
            temperature=0.1,
            #max_tokens=2000
        )

        # 메시지 구성
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        # 프롬프트 저장
        if stage == 1:
            state["system_prompt_1"] = system_prompt
            state["user_prompt_1"] = user_prompt
        elif stage == 2:
            state["system_prompt_2"] = system_prompt
            state["user_prompt_2"] = user_prompt
        elif stage == 3:
            state["system_prompt_3"] = system_prompt
            state["user_prompt_3"] = user_prompt

        # 디버그 출력
        print(f"\n=== {stage}단계: 프롬프트 ===")
        print("\n[System Prompt]:")
        print(system_prompt)
        print("\n[User Prompt]:")
        print(user_prompt)

        # LLM 호출
        result = llm.invoke(messages).content
        
        # 응답 저장
        if stage == 1:
            state["llm_response_1"] = result
        elif stage == 2:
            state["llm_response_2"] = result
        elif stage == 3:
            state["llm_response_3"] = result
            
        print(f"\n=== {stage}단계: LLM 응답 ===")
        print(result)
        
        return result
    
    except Exception as e:
        st.error(f"LLM 호출 중 오류가 발생했습니다: {str(e)}")
        return ""

# 헬퍼 함수: JSON 파싱
def parse_json_response(response: str) -> dict:
    """LLM 응답에서 JSON을 추출하고 파싱하는 함수"""
    try:
        # 코드 블록 제거
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            # 첫 줄 제거 (```json 또는 ``` 제거)
            response = "\n".join(response.split("\n")[1:])
        if response.endswith("```"):
            # 마지막 줄 제거
            response = "\n".join(response.split("\n")[:-1])
        
        # 앞뒤 공백 제거
        response = response.strip()
        
        # JSON 시작/끝 확인
        if not response.startswith("{"):
            response = "{" + response
        if not response.endswith("}"):
            response = response + "}"
        
        # 중괄호 쌍이 맞는지 확인
        open_braces = response.count("{")
        close_braces = response.count("}")
        if open_braces > close_braces:
            response = response + "}" * (open_braces - close_braces)
        elif close_braces > open_braces:
            response = "{" * (close_braces - open_braces) + response
        
        # JSON 파싱
        return json.loads(response)
    
    except json.JSONDecodeError as e:
        print(f"JSON 파싱 오류: {str(e)}")
        print(f"원본 응답: {response}")
        raise e

# 뉴스 수집기 함수
def collect_news(state: AgentState) -> AgentState:
    """뉴스를 수집하는 함수"""
    try:
        # 검색어 설정 - 문자열 또는 리스트 처리
        keyword = state.get("keyword", "삼성")
        
        # 검색 결과 수는 항상 100개
        max_results = 100
        
        # 날짜 범위 가져오기
        start_datetime = state.get("start_datetime")
        end_datetime = state.get("end_datetime")
        
        # GoogleNews 객체 생성
        news = GoogleNews()
        
        # keyword가 문자열이면 리스트로 변환, 아니면 그대로 사용
        if isinstance(keyword, str):
            keywords_to_search = [keyword]
        else:
            keywords_to_search = keyword
        
        # 모든 키워드에 대한 뉴스 수집
        all_news_data = []
        
        # 키워드 언어별 지역 매핑
        def is_korean_keyword(keyword):
            """한국어 키워드인지 판단"""
            # 한글이 포함되어 있으면 한국어 키워드
            return bool(re.search(r'[가-힣]', keyword))
        
        def get_target_regions(keyword):
            """키워드에 따른 대상 지역 반환"""
            # 모든 키워드에 대해 미국에서만 검색
            return ["미국","일본"]
        
        # 각 키워드별로 뉴스 검색 및 결과 병합 (언어별 지역 최적화)
        for kw in keywords_to_search:
            target_regions = get_target_regions(kw)
            keyword_type = "한국어" if is_korean_keyword(kw) else "영어"
            
            print(f"키워드 '{kw}' ({keyword_type}) 검색 중... 대상 지역: {', '.join(target_regions)}")
            
            # 각 대상 지역에서 뉴스 검색
            keyword_results = []
            for region in target_regions:
                region_results = news.search_by_keyword(kw, k=max_results//len(target_regions), region=region)
                keyword_results.extend(region_results)
                print(f"  - {region}에서 {len(region_results)}개 뉴스 수집")
            
            all_news_data.extend(keyword_results)
            print(f"키워드 '{kw}' 총 검색 결과: {len(keyword_results)}개")
            
            # 지역별 분포 출력
            region_count = {}
            for item in keyword_results:
                region = item.get("region", "알 수 없음")
                region_count[region] = region_count.get(region, 0) + 1
            
            if region_count:
                region_summary = ", ".join([f"{region}:{count}" for region, count in region_count.items()])
                print(f"  지역별 분포: {region_summary}")
        
        # 중복 URL 제거 (같은 URL이면 중복으로 간주)
        unique_urls = set()
        unique_news_data = []
        
        for news_item in all_news_data:
            url = news_item.get('url', '')
            if url and url not in unique_urls:
                unique_urls.add(url)
                unique_news_data.append(news_item)
        
        print(f"중복 제거 후 전체 뉴스 수: {len(unique_news_data)}개")
        
        # 수집된 뉴스의 첫 몇 개 샘플 출력
        print(f"\n=== 수집된 뉴스 샘플 (처음 5개) ===")
        for i, news in enumerate(unique_news_data[:5], 1):
            print(f"{i}. 제목: {news.get('content', '제목 없음')}")
            print(f"   언론사: {news.get('press', '알 수 없음')}")
            print(f"   지역: {news.get('region', '알 수 없음')}")
            print(f"   날짜: {news.get('date', '날짜 없음')}")
            print(f"   URL: {news.get('url', 'URL 없음')[:80]}...")
            print("---")
        
        # 날짜 필터링
        if start_datetime and end_datetime:
            print(f"\n=== 날짜 필터링 시작 ===")
            print(f"필터링 범위: {start_datetime} ~ {end_datetime}")
            
            filtered_news = []
            date_parsing_stats = {
                "total": len(unique_news_data),
                "no_date": 0,
                "parse_success": 0,
                "parse_failed": 0,
                "in_range": 0,
                "out_of_range": 0
            }
            
            for news_item in unique_news_data:
                try:
                    # 뉴스 날짜 파싱
                    news_date_str = news_item.get('date', '')
                    if not news_date_str:
                        date_parsing_stats["no_date"] += 1
                        # 날짜 정보가 없는 뉴스는 포함 (최신 뉴스일 가능성)
                        filtered_news.append(news_item)
                        continue
                    
                    news_date = None
                    
                    # 다양한 날짜 형식 처리 (우선순위 순)
                    date_formats = [
                        '%a, %d %b %Y %H:%M:%S %Z',      # GMT 형식: Mon, 01 Jan 2024 12:00:00 GMT
                        '%a, %d %b %Y %H:%M:%S GMT',     # GMT 형식 (명시적)
                        '%Y-%m-%d %H:%M:%S',             # YYYY-MM-DD HH:MM:SS
                        '%Y-%m-%d',                      # YYYY-MM-DD
                        '%Y년 %m월 %d일',                # 한국어 형식
                        '%m/%d/%Y',                      # MM/DD/YYYY
                        '%d/%m/%Y',                      # DD/MM/YYYY
                        '%Y.%m.%d',                      # YYYY.MM.DD
                        '%m.%d.%Y',                      # MM.DD.YYYY
                    ]
                    
                    for date_format in date_formats:
                        try:
                            news_date = datetime.strptime(news_date_str, date_format)
                            break
                        except ValueError:
                            continue
                    
                    if news_date is None:
                        date_parsing_stats["parse_failed"] += 1
                        print(f"날짜 파싱 실패: '{news_date_str}' - 포함하여 처리")
                        # 파싱 실패한 뉴스도 포함 (최신 뉴스일 가능성)
                        filtered_news.append(news_item)
                        continue
                    
                    date_parsing_stats["parse_success"] += 1
                    
                    # GMT 시간대 변환 전 날짜 기록
                    original_news_date = news_date
                    
                    # 시간대 처리: GMT 시간을 한국 시간(KST)으로 변환
                    if 'GMT' in news_date_str or 'Z' in news_date_str:
                        # GMT 시간에 9시간 추가하여 KST로 변환
                        news_date = news_date + timedelta(hours=9)
                        # 첫 몇 개 뉴스에 대해서만 변환 정보 출력
                        if date_parsing_stats["parse_success"] <= 3:
                            print(f"GMT→KST 변환: {original_news_date} → {news_date}")
                    
                    # 파싱된 날짜에 KST 시간대 추가 (시간대가 없는 경우)
                    if news_date.tzinfo is None:
                        news_date = news_date.replace(tzinfo=KST)
                    
                    # 시간까지 고려한 정확한 범위 체크 (08:00 기준)
                    if start_datetime <= news_date <= end_datetime:
                        date_parsing_stats["in_range"] += 1
                        filtered_news.append(news_item)
                    else:
                        date_parsing_stats["out_of_range"] += 1
                        # 범위 외 뉴스 중 첫 몇 개만 출력
                        if date_parsing_stats["out_of_range"] <= 3:
                            print(f"시간 범위 외: {news_date} (범위: {start_datetime} ~ {end_datetime})")
                        
                except Exception as e:
                    date_parsing_stats["parse_failed"] += 1
                    print(f"날짜 처리 오류: {e} - 뉴스 포함하여 처리")
                    # 오류 발생한 뉴스도 포함
                    filtered_news.append(news_item)
                    continue
            
            unique_news_data = filtered_news
            
            # 날짜 필터링 통계 출력
            print(f"\n=== 날짜 필터링 통계 ===")
            print(f"전체 뉴스: {date_parsing_stats['total']}개")
            print(f"날짜 정보 없음: {date_parsing_stats['no_date']}개")
            print(f"날짜 파싱 성공: {date_parsing_stats['parse_success']}개")
            print(f"날짜 파싱 실패: {date_parsing_stats['parse_failed']}개")
            print(f"날짜 범위 내: {date_parsing_stats['in_range']}개")
            print(f"날짜 범위 외: {date_parsing_stats['out_of_range']}개")
            print(f"최종 필터링된 뉴스: {len(unique_news_data)}개")
        
        # 원래 인덱스 추가
        for i, news_item in enumerate(unique_news_data, 1):
            news_item['original_index'] = i
        
        # 원본 뉴스 데이터 저장
        state["original_news_data"] = unique_news_data.copy()
        # 필터링할 뉴스 데이터 저장
        state["news_data"] = unique_news_data
        
        # 날짜 필터링 결과 출력
        print(f"\n날짜 필터링 결과:")
        print(f"시작 날짜: {start_datetime}")
        print(f"종료 날짜: {end_datetime}")
        print(f"필터링된 뉴스 수: {len(unique_news_data)}")
        
        return state
    except Exception as e:
        print(f"뉴스 수집 중 오류 발생: {e}")
        return state

def filter_valid_press(state: AgentState) -> AgentState:
    """유효 언론사 필터링 - 글로벌 뉴스 수집을 위해 비활성화"""
    news_data = state.get("news_data", [])
    
    print(f"\n전체 수집된 뉴스 수: {len(news_data)}")
    print("🌍 글로벌 뉴스 수집을 위해 언론사 필터링을 건너뜁니다.")
    print("모든 언론사의 뉴스가 다음 단계로 전달됩니다.")
    
    # 언론사 필터링 없이 모든 뉴스를 그대로 전달
    print(f"\n유효 언론사 필터링 건너뜀: {len(news_data)}개 뉴스 모두 전달")
    
    # 각 뉴스에 지역 정보가 있다면 표시
    region_count = {}
    for news in news_data:
        region = news.get("region", "알 수 없음")
        if region in region_count:
            region_count[region] += 1
        else:
            region_count[region] = 1
    
    if region_count:
        print("\n=== 지역별 뉴스 분포 ===")
        for region, count in region_count.items():
            print(f"- {region}: {count}개 기사")
    
    # state 업데이트 (모든 뉴스 그대로 전달)
    state["news_data"] = news_data
    return state

def filter_valid_press_original(state: AgentState) -> AgentState:
    """유효 언론사 필터링 - 원본 함수 (필요시 복구용)"""
    news_data = state.get("news_data", [])
    
    # UI에서 설정한 유효 언론사 목록 가져오기
    valid_press_dict_str = state.get("valid_press_dict", "")
    
    # UI 설정 값이 문자열이면 딕셔너리로 파싱
    valid_press_config = {}
    if isinstance(valid_press_dict_str, str) and valid_press_dict_str.strip():
        print("\n[DEBUG] UI에서 설정한 언론사 문자열 파싱 시작")
        try:
            # 문자열에서 딕셔너리 파싱
            lines = valid_press_dict_str.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line and ': ' in line:
                    press_name, aliases_str = line.split(':', 1)
                    try:
                        # 문자열 형태의 리스트를 실제 리스트로 변환
                        aliases = eval(aliases_str.strip())
                        valid_press_config[press_name.strip()] = aliases
                        print(f"[DEBUG] 파싱 성공: {press_name.strip()} -> {aliases}")
                    except Exception as e:
                        print(f"[DEBUG] 파싱 실패: {line}, 오류: {str(e)}")
        except Exception as e:
            print(f"[DEBUG] 전체 파싱 실패: {str(e)}")
    # UI 설정 값이 이미 딕셔너리면 그대로 사용
    elif isinstance(valid_press_dict_str, dict):
        valid_press_config = valid_press_dict_str
        print("\n[DEBUG] UI에서 설정한 언론사 딕셔너리 직접 사용")
    
    # 파싱 결과가 비어있으면 기본값 사용
    if not valid_press_config:
        print("\n[DEBUG] 유효한 설정을 찾을 수 없어 기본값 사용")
        valid_press_config = TRUSTED_PRESS_ALIASES

    return state

# 추가 단계: 선정된 뉴스 원문 요약
def summarize_selected_articles(state: AgentState) -> AgentState:
    """선정된 뉴스 기사의 원문을 스크래핑하고 요약"""
    try:
        final_selection = state.get("final_selection", [])
        
        if not final_selection:
            print("요약할 선정된 뉴스가 없습니다.")
            return state
        
        print(f"\n=== 선정된 {len(final_selection)}개 기사 원문 요약 시작 ===")
        
        # 하이브리드 웹 스크래퍼 초기화 (AI 폴백 활성화)
        from web_scraper import HybridNewsWebScraper
        import os
        
        # 환경변수에서 OpenAI API 키 가져오기
        openai_api_key = os.getenv('OPENAI_API_KEY')
        scraper = HybridNewsWebScraper(
            openai_api_key=openai_api_key,
            enable_ai_fallback=True  # AI 폴백 활성화
        )
        
        # 각 선정된 뉴스의 원문 추출 및 요약
        summarized_articles = []
        
        for i, news in enumerate(final_selection, 1):
            url = news.get('url', '')
            title = news.get('title', '')
            
            print(f"\n[{i}/{len(final_selection)}] 기사 원문 추출 중: {title}")
            
            # 원문 추출 (새로운 ExtractionResult 객체 반환)
            extraction_result = scraper.extract_content(url, timeout=15)
            
            if extraction_result.success and extraction_result.content:
                # AI 요약 생성
                summary = _generate_article_summary(
                    extraction_result.content, 
                    title, 
                    state.get("system_prompt_3", "")
                )
                
                # 요약 결과 추가
                news_with_summary = news.copy()
                news_with_summary['full_content'] = extraction_result.content
                news_with_summary['ai_summary'] = summary
                news_with_summary['extraction_success'] = True
                news_with_summary['extraction_method'] = extraction_result.method.value
                news_with_summary['extraction_time'] = extraction_result.extraction_time
                
                summarized_articles.append(news_with_summary)
                print(f"✅ 요약 완료: {title[:50]}... (방법: {extraction_result.method.value})")
                
            else:
                # 원문 추출 실패
                error_msg = extraction_result.error_message if extraction_result else "알 수 없는 오류"
                news_with_summary = news.copy()
                news_with_summary['full_content'] = ""
                news_with_summary['ai_summary'] = f"원문 추출 실패로 요약할 수 없습니다. ({error_msg})"
                news_with_summary['extraction_success'] = False
                news_with_summary['extraction_method'] = extraction_result.method.value if extraction_result else "unknown"
                news_with_summary['extraction_time'] = extraction_result.extraction_time if extraction_result else 0
                
                summarized_articles.append(news_with_summary)
                print(f"❌ 원문 추출 실패: {title[:50]}... ({error_msg})")
            
            # 요청 간 지연 (서버 부하 방지)
            if i < len(final_selection):
                time.sleep(1)
        
        # 결과 업데이트
        state["final_selection"] = summarized_articles
        
        print(f"\n원문 요약 완료: {len(summarized_articles)}개 기사")
        success_count = sum(1 for article in summarized_articles if article.get('extraction_success', False))
        print(f"성공: {success_count}개, 실패: {len(summarized_articles) - success_count}개")
        
        return state
        
    except Exception as e:
        print(f"기사 요약 중 오류 발생: {e}")
        return state

def _generate_article_summary(content: str, title: str, system_prompt: str) -> str:
    """AI를 사용해 기사 요약 생성"""
    try:
        # 요약 프롬프트 먼저 정의
        summary_prompt = f"""
다음 뉴스 기사를 현대자동차 남양연구소 PT/전동화 개발 인력 관점에서 요약해주세요.

[기사 제목]
{title}

[기사 본문]
{content}

[요약 요구사항]
1. 제목을 한국어로 번역
2. 핵심 내용을 1-2문장으로 요약
3. 세부 내용을 3-5개 항목으로 나눠서 정리
4. 기술적 세부사항이 있다면 구체적으로 언급

[응답 형식]
JSON 형식으로 응답해주세요:
{{
  "title_korean": "제목 한국어 번역",
  "summary_oneline": "핵심 내용 1-2문장 요약",
  "details": [
    "세부 내용 1",
    "세부 내용 2", 
    "세부 내용 3"
  ]
}}

[예시]
{{
  "title_korean": "VW, BEV (ID. 시리즈) 가격 동결",
  "summary_oneline": "폭스바겐이 '26년식부터 ID. 시리즈, T-Roc 등 BEV는 연례 가격 인상에서 제외, ICE는 평균 1.5% 인상 예정",
  "details": [
    "작년 '25년식 출시 모델에 대한 가격 연례 인상 시 ICE가격 2.1%에서 3.2%로 인상 및 BEV 가격은 동결한 것과 유사 행보",
    "올해 독일 내 VW 판매 차종 5대 중 1대는 BEV 모델인 점 등 시장 침투율 고려하여 BEV 가격 경쟁력 유지 및 소비자 부담 절감 목표",
    "다만 동결한 BEV 가격의 경우 정가에만 해당하며 외관 컬러, 스포츠·디자인 패키지 등 개별 추가 옵션의 가격은 상향 예정",
    "첫 차량 LS6에 8월 15일 사전 판매 시작, 플래그십 SUV LS9는 2025년 4분기 공식 출시 예정"
  ]
}}

[중요] 반드시 완전한 JSON 형식으로만 응답하세요. 다른 텍스트나 설명은 포함하지 말 것.
[중요] 모든 문장은 한국어로 작성할 것.  
[중요] 문체는 자연스러운 보고서 요약체(예: ~함, ~임, ~음)로 작성할 것.  
"""
        
        # OpenAI 클라이언트 초기화 (수정된 방식)
        try:
            llm = ChatOpenAI(
                #model="openai.gpt-4.1-2025-04-14",  #pwc
                model="gpt-4.1",
                temperature=0.3,
                request_timeout=30,
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                openai_api_base=os.getenv("OPENAI_BASE_URL")
            )
            
            # AI 요약 생성
            messages = [
                SystemMessage(content="당신은 자동차 산업 분석 전문가입니다. 뉴스 기사를 현대자동차 연구개발 관점에서 요약하는 작업을 수행합니다."),
                HumanMessage(content=summary_prompt)
            ]
            
            response = llm.invoke(messages)
            # JSON 응답 파싱 및 포맷팅
            summary_content = response.content
            return _format_json_summary(summary_content)
            
        except Exception as e:
            print(f"ChatOpenAI 초기화 또는 호출 실패: {e}")
            # 간단한 OpenAI 클라이언트로 대체
            try:
                from openai import OpenAI
                client = OpenAI(
                    api_key=os.getenv("OPENAI_API_KEY"),
                    base_url=os.getenv("OPENAI_BASE_URL")
                )
                
                # 직접 API 호출
                response = client.chat.completions.create(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": "당신은 자동차 산업 분석 전문가입니다. 뉴스 기사를 현대자동차 연구개발 관점에서 요약하는 작업을 수행합니다."},
                        {"role": "user", "content": summary_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1000
                )
                # JSON 응답 파싱 및 포맷팅
                summary_content = response.choices[0].message.content
                return _format_json_summary(summary_content)
                
            except Exception as fallback_error:
                print(f"OpenAI 직접 호출도 실패: {fallback_error}")
                return f"요약 생성 실패: {str(fallback_error)}"
        
    except Exception as e:
        print(f"AI 요약 생성 실패: {e}")
        return f"요약 생성 실패: {str(e)}"

def _clean_html_tags(text: str) -> str:
    """HTML 태그를 제거하고 깔끔한 텍스트로 변환"""
    import re
    
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

def _format_json_summary(json_response: str) -> str:
    """요약 JSON 응답을 HTML 형식으로 변환"""
    import json
    import re
    
    try:
        # JSON 응답에서 코드 블록 제거
        json_text = json_response.strip()
        if json_text.startswith("```json"):
            json_text = json_text[7:]
        if json_text.startswith("```"):
            json_text = "\n".join(json_text.split("\n")[1:])
        if json_text.endswith("```"):
            json_text = "\n".join(json_text.split("\n")[:-1])
        
        json_text = json_text.strip()
        
        # JSON 파싱
        summary_data = json.loads(json_text)
        
        # HTML 형식으로 변환
        title_korean = summary_data.get('title_korean', '제목 없음')
        summary_oneline = summary_data.get('summary_oneline', '요약 없음')
        details = summary_data.get('details', [])
        
        # HTML 포맷팅
        html_content = f"""
<div style="margin-bottom: 15px;">
    <h4 style="color: #333; margin-bottom: 10px; font-size: 1.2em; font-weight: bold;">{title_korean}</h4>
    <div style="background-color: #f0f8ff; padding: 12px; border-radius: 6px; margin-bottom: 12px; border-left: 3px solid #0077b6;">
        <strong>*</strong> {summary_oneline}
    </div>
</div>
"""
        
        if details:
            html_content += "<div style='margin-top: 8px;'>\n"
            for detail in details:
                html_content += f"<div style='margin-bottom: 6px; line-height: 1.4;'>- {detail}</div>\n"
            html_content += "</div>"
        
        return html_content
        
    except json.JSONDecodeError as e:
        print(f"JSON 파싱 오류: {e}")
        print(f"원본 응답: {json_response}")
        # JSON 파싱 실패 시 원본 텍스트 반환
        return f"<div style='color: #666;'>요약 파싱 오류:<br>{json_response}</div>"
    except Exception as e:
        print(f"요약 포맷팅 오류: {e}")
        return f"<div style='color: #666;'>요약 포맷팅 오류:<br>{json_response}</div>"

# 1단계: 뉴스 제외 판단
def filter_excluded_news(state: AgentState) -> AgentState:
    """뉴스를 제외/보류/유지로 분류하는 함수"""
    try:
        # 시스템 프롬프트 설정
        system_prompt = state.get("system_prompt_1", "당신은 뉴스 분석 전문가입니다. 뉴스의 중요성을 판단하여 제외/보류/유지로 분류하는 작업을 수행합니다. 특히 회계법인의 관점에서 중요하지 않은 뉴스(예: 단순 홍보, CSR 활동, 이벤트 등)를 식별하고, 회계 감리나 재무 관련 이슈는 반드시 유지하도록 합니다.")
        
        # 뉴스 데이터 준비
        news_data = state.get("news_data", [])
        if not news_data:
            st.error("분석할 뉴스가 없습니다.")
            return state
            
        # 뉴스 목록 문자열 생성 - 원래 인덱스 사용
        news_list = ""
        for news in news_data:
            press = news.get('press', '알 수 없음')
            original_index = news.get('original_index')
            news_list += f"{original_index}. {news['content']} ({press})\n"
            
        # 제외 판단 프롬프트
        exclusion_prompt = f"""아래 뉴스 목록을 분석하여 제외/보류/유지로 분류해주세요.
각 뉴스의 번호는 고유 식별자이므로 변경하지 말고 그대로 응답에 사용해주세요.

[뉴스 목록]
{news_list}

[제외 기준]
{state.get("exclusion_criteria", "")}

[응답 요구사항]
1. 제외/보류/유지 사유는 간단명료하게 작성
2. 각 카테고리별 최대 20개까지만 포함
3. 응답은 완전한 JSON 형식이어야 함

다음과 같은 JSON 형식으로 응답해주세요:
{{
  "excluded": [
    {{
      "index": 1,
      "title": "뉴스 제목",
      "reason": "제외 사유"
    }}
  ],
  "borderline": [
    {{
      "index": 2,
      "title": "뉴스 제목",
      "reason": "보류 사유"
    }}
  ],
  "retained": [
    {{
      "index": 3,
      "title": "뉴스 제목",
      "reason": "유지 사유"
    }}
  ]
}}"""

        # 최대 3번까지 시도
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # LLM 호출 (헬퍼 함수 사용)
                result = call_llm(state, system_prompt, exclusion_prompt, stage=1)
                
                # JSON 파싱 (헬퍼 함수 사용)
                classification = parse_json_response(result)
                
                # 필수 필드 확인
                if not all(key in classification for key in ["excluded", "borderline", "retained"]):
                    raise ValueError("필수 필드가 누락되었습니다.")
                
                # 상태 업데이트 시 원래 인덱스 유지
                for category in ["excluded", "borderline", "retained"]:
                    for item in classification.get(category, []):
                        original_index = item['index']
                        item['original_index'] = original_index
                
                state["excluded_news"] = classification.get("excluded", [])
                state["borderline_news"] = classification.get("borderline", [])
                state["retained_news"] = classification.get("retained", [])
                
                print("\n[분류 결과]")
                print(f"제외: {len(state['excluded_news'])}개")
                print(f"보류: {len(state['borderline_news'])}개")
                print(f"유지: {len(state['retained_news'])}개")
                
                # 각 카테고리별 샘플 출력
                if state['excluded_news']:
                    print(f"\n제외된 뉴스 샘플 (처음 3개):")
                    for i, news in enumerate(state['excluded_news'][:3], 1):
                        print(f"  {i}. {news.get('title', '제목 없음')} - {news.get('reason', '이유 없음')}")
                
                if state['retained_news']:
                    print(f"\n유지된 뉴스 샘플 (처음 3개):")
                    for i, news in enumerate(state['retained_news'][:3], 1):
                        print(f"  {i}. {news.get('title', '제목 없음')} - {news.get('reason', '이유 없음')}")
                
                if state['borderline_news']:
                    print(f"\n보류된 뉴스 샘플:")
                    for i, news in enumerate(state['borderline_news'], 1):
                        print(f"  {i}. {news.get('title', '제목 없음')} - {news.get('reason', '이유 없음')}")
                
                # 성공적으로 파싱되면 루프 종료
                break
                
            except (json.JSONDecodeError, ValueError) as e:
                print(f"\n파싱 시도 {attempt + 1} 실패: {str(e)}")
                if attempt == max_retries - 1:  # 마지막 시도에서도 실패
                    st.error(f"분류 결과 파싱 중 오류가 발생했습니다: {str(e)}")
                    return state
                # 다음 시도를 위해 잠시 대기
                time.sleep(1)

        return state

    except Exception as e:
        st.error(f"뉴스 분류 중 오류가 발생했습니다: {str(e)}")
        return state

# 2단계: 뉴스 그룹핑 + 대표 기사 선택
def group_and_select_news(state: AgentState) -> AgentState:
    try:
        # 디버깅 정보 출력
        print("\n=== 그룹핑 전 인덱스 정보 ===")
        print(f"보류 뉴스 인덱스: {[news['index'] for news in state['borderline_news']]}")
        print(f"유지 뉴스 인덱스: {[news['index'] for news in state['retained_news']]}")

        # 유지 및 보류 뉴스 합치기
        retained_indices = [news["index"] for news in state["retained_news"]]
        borderline_indices = [news["index"] for news in state["borderline_news"]]
        target_indices = retained_indices + borderline_indices
        
        print(f"대상 뉴스 인덱스: {target_indices}")
        
        # 대상 뉴스 필터링 (원래 인덱스 매핑)
        target_news = []
        for news in state["news_data"]:
            original_index = news.get("original_index")
            if original_index in target_indices:
                print(f"매칭된 뉴스: index={original_index}, title={news['content']}")
                news["current_index"] = original_index  # current_index에 original_index 저장
                target_news.append(news)
        
        print(f"필터링된 대상 뉴스 수: {len(target_news)}")
        
        if not target_news:
            print("필터링된 뉴스가 없습니다!")
            return state

        # 뉴스 데이터를 문자열로 변환 (current_index 사용)
        news_text = "\n\n".join([
            f"인덱스: {news['current_index']}\n제목: {news['content']}\n언론사: {news.get('press', '알 수 없음')}\n발행일: {news.get('date', '알 수 없음')}"
            for news in target_news
        ])

        # 그룹핑 프롬프트
        system_prompt = state.get("system_prompt_2", "당신은 뉴스 분석 전문가입니다. 유사한 뉴스를 그룹화하고 대표성을 갖춘 기사를 선택하는 작업을 수행합니다. 같은 사안에 대해 숫자, 기업 ,계열사, 맥락, 주요 키워드 등이 유사하면 중복으로 판단합니다. 언론사의 신뢰도와 기사의 상세도를 고려하여 대표 기사를 선정합니다.")
        
        grouping_prompt = f"""유사한 뉴스끼리 그룹으로 묶고, 각 그룹에서 가장 대표성 있는 뉴스 1건만 선택해 주세요.
주어진 인덱스 번호를 정확히 사용해주세요. 인덱스 번호를 임의로 변경하지 마세요.

[뉴스 목록]
{news_text}

[중복 처리 기준]
{state.get("duplicate_handling", "")}

다음과 같은 JSON 형식으로 응답해주세요:
{{
  "groups": [
    {{
      "indices": [2, 4],
      "selected_index": 2,
      "reason": "동일한 회원권 관련 보도이며, 2번이 더 자세하고 언론사 우선순위가 높음"
    }},
    {{
      "indices": [5],
      "selected_index": 5,
      "reason": "단독 기사"
    }}
  ]
}}"""

        try:
            # LLM 호출 (헬퍼 함수 사용)
            result = call_llm(state, system_prompt, grouping_prompt, stage=2)
            
            # JSON 파싱 (헬퍼 함수 사용)
            grouping = parse_json_response(result)
            grouped_news = grouping.get("groups", [])
            
            # 그룹핑된 뉴스의 인덱스들을 모두 수집
            grouped_indices = set()
            for group in grouped_news:
                grouped_indices.update(group.get("indices", []))
            
            # 그룹핑되지 않은 뉴스들을 찾아서 각각 단일 그룹으로 추가
            current_indices = set(news["current_index"] for news in target_news)
            ungrouped_indices = current_indices - grouped_indices
            
            # 미그룹 뉴스들을 각각 단일 그룹으로 추가
            for idx in ungrouped_indices:
                new_group = {
                    "indices": [idx],
                    "selected_index": idx,
                    "reason": "개별 뉴스로 처리"
                }
                grouped_news.append(new_group)
            
            # 그룹핑 결과 저장
            state["grouped_news"] = grouped_news
            
            # 디버깅 정보 출력
            print("\n=== 그룹핑 결과 ===")
            for group in grouped_news:
                print(f"그룹: {group['indices']}, 선택된 인덱스: {group['selected_index']}")
            
            return state

        except json.JSONDecodeError as e:
            st.error(f"그룹핑 결과 파싱 중 오류가 발생했습니다: {str(e)}")
            return state

    except Exception as e:
        st.error(f"뉴스 그룹핑 중 오류가 발생했습니다: {str(e)}")
        return state

# 3단계: 중요도 평가 + 최종 선정
def evaluate_importance(state: AgentState) -> AgentState:
    try:
        # 선택된 뉴스 추출
        selected_news = []
        index_map = {}  # 리스트 인덱스와 원래 인덱스 간의 매핑
        
        # 디버깅 정보 출력
        print("\n=== 중요도 평가 시작 ===")
        print(f"그룹 수: {len(state['grouped_news'])}")
        
        # 각 그룹에서 선택된 뉴스 찾기
        for i, group in enumerate(state["grouped_news"], 1):
            selected_index = group["selected_index"]
            
            # 원래 뉴스 데이터에서 selected_index와 일치하는 뉴스 찾기
            selected_article = next(
                (news for news in state["news_data"] 
                 if news.get("original_index") == selected_index),
                None
            )
            
            if selected_article:
                print(f"그룹 {i}, 선택된 인덱스 {selected_index}: 제목 = {selected_article['content']}")
                # 리스트 인덱스를 i로, 원래 인덱스를 selected_index로 매핑
                index_map[i] = selected_index
                selected_article["list_index"] = i
                selected_article["group_info"] = group
                selected_news.append(selected_article)
            else:
                print(f"그룹 {i}, 선택된 인덱스 {selected_index}: 해당 뉴스를 찾을 수 없음")
        
        if not selected_news:
            print("선택된 뉴스가 없습니다!")
            return state

        # 뉴스 데이터를 문자열로 변환 (list_index 사용)
        news_text = "\n\n".join([
            f"인덱스: {news['list_index']}\n제목: {news['content']}\n언론사: {news.get('press', '알 수 없음')}\n발행일: {news.get('date', '알 수 없음')}"
            for news in selected_news
        ])

        # 중요도 평가 프롬프트
        system_prompt = state.get("system_prompt_3", "당신은 회계법인의 전문 애널리스트입니다. 뉴스의 중요도를 평가하고 최종 선정하는 작업을 수행합니다. 특히 회계 감리, 재무제표, 경영권 변동, 주요 계약, 법적 분쟁 등 회계법인의 관점에서 중요한 이슈를 식별하고, 그 중요도를 '상' 또는 '중'으로 평가합니다. 또한 각 뉴스의 핵심 키워드와 관련 계열사를 식별하여 보고합니다.")
        
        evaluation_prompt = f"""아래 기사들에 대해 중요도를 평가하고, 모든 뉴스에 대해 평가 결과를 알려주세요.
중요도 '상' 또는 '중'인 뉴스는 최종 선정하고, '하'인 뉴스는 선정하지 않습니다.

[뉴스 목록]
{news_text}

[선택 기준]
{state.get("selection_criteria", "")}

[응답 요구사항]
1. 중요도는 "상", "중", "하" 중 하나로 평가
2. 미선정 사유는 간단명료하게 작성
3. 응답은 완전한 JSON 형식이어야 함

다음과 같은 JSON 형식으로 응답해주세요:
{{
  "final_selection": [
        {{
            "index": 2,
            "title": "뉴스 제목",
            "importance": "상",
            "reason": "선정 사유",
            "keywords": ["키워드1", "키워드2"],
            "affiliates": ["계열사1", "계열사2"],
            "press": "언론사명",
            "date": "발행일"
        }}
  ],
  "not_selected": [
    {{
      "index": 3,
      "title": "뉴스 제목",
      "importance": "하",
      "reason": "미선정 사유"
    }}
  ]
}}"""

        # 최대 3번까지 시도
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # LLM 호출 (헬퍼 함수 사용)
                result = call_llm(state, system_prompt, evaluation_prompt, stage=3)
                
                # JSON 파싱 (헬퍼 함수 사용)
                evaluation = parse_json_response(result)
                
                # 필수 필드 확인
                if not all(key in evaluation for key in ["final_selection", "not_selected"]):
                    raise ValueError("필수 필드가 누락되었습니다.")
                
                # 최종 선정된 뉴스 처리
                for news in evaluation["final_selection"]:
                    list_index = news["index"]
                    if list_index in index_map:
                        original_index = index_map[list_index]
                        original_news = next(
                            (n for n in selected_news if n["list_index"] == list_index),
                            None
                        )
                        if original_news:
                            # 원본 데이터의 메타데이터를 그대로 사용
                            news.update({
                                "url": original_news.get("url", ""),
                                "press": original_news.get("press", ""),  # LLM이 제공한 press 대신 원본 press 사용
                                "date": original_news.get("date", ""),
                                "original_index": original_index,
                                "group_info": original_news["group_info"]
                            })
                            print(f"최종 선정 뉴스: 인덱스={original_index}, 제목={news['title']}")

                # 미선정 뉴스도 동일하게 처리
                for news in evaluation["not_selected"]:
                    list_index = news["index"]
                    if list_index in index_map:
                        original_index = index_map[list_index]
                        original_news = next(
                            (n for n in selected_news if n["list_index"] == list_index),
                            None
                        )
                        if original_news:
                            news.update({
                                "url": original_news.get("url", ""),
                                "press": original_news.get("press", ""),  # LLM이 제공한 press 대신 원본 press 사용
                                "date": original_news.get("date", ""),
                                "original_index": original_index,
                                "group_info": original_news["group_info"]
                            })
                            print(f"미선정 뉴스: 인덱스={original_index}, 제목={news['title']}")
                
                state["final_selection"] = evaluation.get("final_selection", [])
                state["not_selected_news"] = evaluation.get("not_selected", [])
                
                print(f"최종 선정 뉴스 수: {len(state['final_selection'])}")
                print(f"미선정 뉴스 수: {len(state['not_selected_news'])}")
                
                # 최종 선정된 뉴스 상세 정보 출력
                if state['final_selection']:
                    print(f"\n=== 최종 선정된 뉴스 ===")
                    for i, news in enumerate(state['final_selection'], 1):
                        print(f"{i}. {news.get('title', '제목 없음')}")
                        print(f"   중요도: {news.get('importance', '없음')}")
                        print(f"   언론사: {news.get('press', '알 수 없음')}")
                        print(f"   선정 사유: {news.get('reason', '이유 없음')}")
                        print("---")
                else:
                    print("\n⚠️ 최종 선정된 뉴스가 없습니다!")
                    
                # 미선정 뉴스 샘플 출력
                if state['not_selected_news']:
                    print(f"\n미선정 뉴스 샘플 (처음 3개):")
                    for i, news in enumerate(state['not_selected_news'][:3], 1):
                        print(f"  {i}. {news.get('title', '제목 없음')} - {news.get('reason', '이유 없음')}")
                
                return state

            except (json.JSONDecodeError, ValueError) as e:
                print(f"\n파싱 시도 {attempt + 1} 실패: {str(e)}")
                if attempt == max_retries - 1:  # 마지막 시도에서도 실패
                    st.error(f"중요도 평가 결과 파싱 중 오류가 발생했습니다: {str(e)}")
                    return state
                # 다음 시도를 위해 잠시 대기
                time.sleep(1)

        return state

    except Exception as e:
        st.error(f"중요도 평가 중 오류가 발생했습니다: {str(e)}")
        return state

# 노드 정의
def get_nodes():
    return {
        "collect_news": collect_news,
        "filter_valid_press": filter_valid_press,
        "filter_excluded_news": filter_excluded_news,
        "group_and_select_news": group_and_select_news,
        "evaluate_importance": evaluate_importance
    }

# 에지 정의
def get_edges():
    return [
        ("collect_news", "filter_valid_press"),
        ("filter_valid_press", "filter_excluded_news"),
        ("filter_excluded_news", "group_and_select_news"),
        ("group_and_select_news", "evaluate_importance"),
        ("evaluate_importance", END)
    ]

# 뉴스 출력 함수
def print_news(news_list, title):
    print(f"\n=== {title} ===")
    for i, news in enumerate(news_list):
        print(f"\n[{i+1}] 제목: {news['content']}")
        print(f"    URL: {news['url']}")

# 메인 실행 함수
def main():
    # 노드 및 에지 가져오기
    nodes = get_nodes()
    edges = get_edges()
    
    # 그래프 생성
    builder = StateGraph(AgentState)
    
    # 노드 추가
    for node_name, node_fn in nodes.items():
        builder.add_node(node_name, node_fn)
    
    # 에지 추가
    for start, end in edges:
        builder.add_edge(start, end)
    
    # 시작점 설정
    builder.set_entry_point("collect_news")
    
    # 그래프 컴파일
    graph = builder.compile()
    
    # 실행
    # 빈 초기 상태로 시작
    result = graph.invoke({
        "news_data": [],
        "filtered_news": [],
        "analysis": "",
        "keyword": "삼성전자",
        "system_prompt": "",
        "user_prompt": "",
        "excluded_news": [],
        "borderline_news": [],
        "retained_news": [],
        "grouped_news": [],
        "final_selection": [],
        "system_prompt_1": "",
        "user_prompt_1": "",
        "llm_response_1": "",
        "system_prompt_2": "",
        "user_prompt_2": "",
        "llm_response_2": "",
        "system_prompt_3": "",
        "user_prompt_3": "",
        "llm_response_3": "",
        "not_selected_news": [],
        "original_news_data": [],
        "start_datetime": datetime.now(),
        "end_datetime": datetime.now() + timedelta(days=7)
    })
    
    # 전체 뉴스 목록 출력
    print_news(result["original_news_data"], "전체 뉴스 (50개)")
    
    # 분석 결과 출력
    print("\n\n=== 회계법인 관점의 분석 결과 ===")
    print(result["analysis"])
    
    # 선별된 뉴스 출력
    print_news(result["filtered_news"], "회계법인 관점의 주요 뉴스")

if __name__ == "__main__":
    main()
