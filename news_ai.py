from typing import List, Dict, Any, TypedDict
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from googlenews import GoogleNews
import operator
import dotenv
import json
import re
import os
from datetime import datetime, timedelta
import streamlit as st
import time
from urllib.parse import urlparse

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

# 신뢰할 수 있는 언론사 목록
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

# 뉴스 수집기 함수
def collect_news(state: AgentState) -> AgentState:
    """뉴스를 수집하는 함수"""
    try:
        # 검색어 설정
        keyword = state.get("keyword", "삼성")
        
        # 검색 결과 수 설정 (state에서 가져옴)
        max_results = state.get("max_results", 50)
        
        # GoogleNews 객체 생성
        news = GoogleNews()
        
        # 뉴스 검색
        news_data = news.search_by_keyword(keyword, k=max_results)
        
        # 원래 인덱스 추가
        for i, news_item in enumerate(news_data, 1):
            news_item['original_index'] = i
        
        # 원본 뉴스 데이터 저장
        state["original_news_data"] = news_data.copy()
        # 필터링할 뉴스 데이터 저장
        state["news_data"] = news_data
        
        return state
    except Exception as e:
        print(f"뉴스 수집 중 오류 발생: {e}")
        return state

def filter_valid_press(state: AgentState) -> AgentState:
    """유효 언론사 필터링"""
    news_data = state.get("news_data", [])
    
    # Get keyword and max_results from state
    keyword = state.get("keyword", "삼성")  # Default to "삼성" if not specified
    max_results = state.get("max_results", 50)  # Default to 50 if not specified
    
    # UI에서 설정한 유효 언론사 목록 사용
    valid_press_config = state.get("valid_press_dict", {})
    if not valid_press_config:
        # 기본값으로 하드코딩된 값 사용
        valid_press_config = TRUSTED_PRESS_ALIASES
    
    # 유효 언론사 뉴스 필터링
    valid_press_news = []
    for news in news_data:
        press = news.get("press", "").lower()
        url = news.get("url", "").lower()
        
        # 언론사명이나 URL이 신뢰할 수 있는 언론사 목록에 포함되는지 확인
        is_valid = False
        for main_press, aliases in valid_press_config.items():
            domain = urlparse(url).netloc.lower()
            if any(alias.lower() == press for alias in aliases) or \
               any(alias.lower() == domain for alias in aliases):
                is_valid = True
                break
        
        if is_valid:
            valid_press_news.append(news)
    
    # 결과 출력
    print(f"\n유효 언론사 목록: {list(valid_press_config.keys())}")
    print(f"총 뉴스 수: {len(news_data)}")
    print(f"유효 언론사 뉴스 수: {len(valid_press_news)}")
    
    # 유효 언론사 뉴스가 20개 미만인 경우 추가 수집
    if len(valid_press_news) < 20:
        print(f"\n유효 언론사 뉴스가 20개 미만({len(valid_press_news)}개)이므로 추가 수집을 시작합니다...")
        
        # GoogleNews 객체 생성
        news_collector = GoogleNews()
        
        # 추가 수집 시도 (최대 3번)
        for attempt in range(3):
            # 추가 뉴스 수집 (기존 max_results의 1.5배)
            additional_news = news_collector.search_by_keyword(keyword, k=int(max_results * 1.5))
            
            # 원래 인덱스 추가
            for i, news_item in enumerate(additional_news, len(news_data) + 1):
                news_item['original_index'] = i
            
            # 추가 수집된 뉴스에 대해 유효 언론사 필터링
            for add_news in additional_news:
                add_press = add_news.get("press", "").lower()
                add_url = add_news.get("url", "").lower()
                
                add_is_valid = False
                for main_press, aliases in valid_press_config.items():
                    add_domain = urlparse(add_url).netloc.lower()
                    if any(alias.lower() == add_press for alias in aliases) or \
                       any(alias.lower() == add_domain for alias in aliases):
                        add_is_valid = True
                        break
                
                if add_is_valid:
                    # 이미 필터링된 리스트에 있는지 중복 확인 후 추가
                    if not any(existing_news['url'] == add_news['url'] for existing_news in valid_press_news):
                         valid_press_news.append(add_news)
            
            print(f"추가 수집 시도 {attempt + 1}: {len(valid_press_news)}개의 유효 언론사 뉴스")
            
            # 20개 이상이면 중단
            if len(valid_press_news) >= 20:
                break
            
            # 마지막 시도가 아니면 잠시 대기
            if attempt < 2:
                time.sleep(1)
    
    # 최종 결과 출력
    print(f"\n최종 유효 언론사 뉴스 수: {len(valid_press_news)}")
    
    # 유효 언론사 뉴스가 없는 경우
    if not valid_press_news:
        print("유효 언론사의 뉴스가 없습니다.")
        state["news_data"] = [] # 빈 리스트로 업데이트
        return state
    
    # state 업데이트
    state["news_data"] = valid_press_news
    return state

# 1단계: 뉴스 제외 판단
def filter_excluded_news(state: AgentState) -> AgentState:
    """뉴스를 제외/보류/유지로 분류하는 함수"""
    try:
        # 시스템 프롬프트 설정
        system_prompt = state.get("system_prompt_1", "")
        
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
        exclusion_prompt = f"""아래 뉴스 목록을 회계법인의 관점에서 분석하여 제외/보류/유지로 분류해주세요.
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

        # LLM 호출
        llm = ChatOpenAI(
            model_name=state.get("model", "gpt-4o"),
            temperature=0.1,
            max_tokens=2000
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=exclusion_prompt)
        ]

        # 프롬프트와 응답 저장
        state["system_prompt_1"] = system_prompt
        state["user_prompt_1"] = exclusion_prompt

        print("\n=== 1단계: 제외 판단 ===")
        print("\n[System Prompt]:")
        print(system_prompt)
        print("\n[User Prompt]:")
        print(exclusion_prompt)

        # 최대 3번까지 시도
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = llm.invoke(messages).content
                
                print("\n[LLM Response]:")
                print(result)
                print("\n" + "="*50)

                # LLM 응답 저장
                state["llm_response_1"] = result

                # JSON 응답 파싱
                if result.startswith("```json"):
                    result = result[7:]
                if result.startswith("```"):
                    result = result[3:]
                if result.endswith("```"):
                    result = result[:-3]
                
                # JSON 형식 정리
                result = result.strip()
                if not result.startswith("{"):
                    result = "{" + result
                if not result.endswith("}"):
                    result = result + "}"
                
                # 중괄호 쌍이 맞는지 확인
                open_braces = result.count("{")
                close_braces = result.count("}")
                if open_braces > close_braces:
                    result = result + "}" * (open_braces - close_braces)
                elif close_braces > open_braces:
                    result = "{" * (close_braces - open_braces) + result
                
                # JSON 파싱 시도
                classification = json.loads(result)
                
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
                
                # 성공적으로 파싱되면 루프 종료
                break
                
            except (json.JSONDecodeError, ValueError) as e:
                print(f"\n파싱 시도 {attempt + 1} 실패: {str(e)}")
                if attempt == max_retries - 1:  # 마지막 시도에서도 실패
                    st.error(f"분류 결과 파싱 중 오류가 발생했습니다: {str(e)}")
                    st.error(f"원본 응답: {result}")
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
        print(f"news_data의 original_index: {[news.get('original_index') for news in state['news_data']]}")
        
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

        # LLM 호출
        llm = ChatOpenAI(
            model_name=state.get("model", "gpt-4o"),
            temperature=0.1,
            max_tokens=2000
        )

        # 그룹핑 프롬프트
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

        messages = [
            SystemMessage(content=state.get("system_prompt_2", "당신은 회계법인의 뉴스 분석 전문가입니다. 유사한 뉴스를 그룹화하고 대표성을 갖춘 기사를 선택하는 작업을 수행합니다. 특히 회계법인의 관점에서 중요한 정보를 포함하고 있는 기사를 우선적으로 선택하며, 언론사의 신뢰도와 기사의 상세도를 고려하여 대표 기사를 선정합니다.")),
            HumanMessage(content=grouping_prompt)
        ]

        # 프롬프트와 응답 저장
        state["system_prompt_2"] = messages[0].content
        state["user_prompt_2"] = messages[1].content

        print("\n=== 2단계: 그룹핑 ===")
        print("\n[System Prompt]:")
        print(messages[0].content)
        print("\n[User Prompt]:")
        print(messages[1].content)

        result = llm.invoke(messages).content
        
        print("\n[LLM Response]:")
        print(result)
        print("\n" + "="*50)

        # LLM 응답 저장
        state["llm_response_2"] = result

        try:
            # JSON 응답 파싱
            result_text = result
            # 코드 블록 마커 제거
            if result_text.startswith("```"):
                # 첫 줄 제거 (```json 또는 ``` 제거)
                result_text = "\n".join(result_text.split("\n")[1:])
            if result_text.endswith("```"):
                # 마지막 줄 제거
                result_text = "\n".join(result_text.split("\n")[:-1])
            
            # 앞뒤 공백 제거
            result_text = result_text.strip()
            
            # JSON 파싱
            grouping = json.loads(result_text)
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
            st.error(f"원본 응답: {result}")
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

        # LLM 호출
        llm = ChatOpenAI(
            model_name=state.get("model", "gpt-4o"),
            temperature=0.1,
            max_tokens=2000
        )

        # 중요도 평가 프롬프트
        evaluation_prompt = f"""아래 기사들에 대해 회계법인의 시각으로 중요도를 평가하고, 모든 뉴스에 대해 평가 결과를 알려주세요.
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

        messages = [
            SystemMessage(content=state.get("system_prompt_3", "당신은 회계법인의 전문 애널리스트입니다. 뉴스의 중요도를 평가하고 최종 선정하는 작업을 수행합니다. 특히 회계 감리, 재무제표, 경영권 변동, 주요 계약, 법적 분쟁 등 회계법인의 관점에서 중요한 이슈를 식별하고, 그 중요도를 '상' 또는 '중'으로 평가합니다. 또한 각 뉴스의 핵심 키워드와 관련 계열사를 식별하여 보고합니다.")),
            HumanMessage(content=evaluation_prompt)
        ]

        # 프롬프트와 응답 저장
        state["system_prompt_3"] = messages[0].content
        state["user_prompt_3"] = messages[1].content

        print("\n=== 3단계: 중요도 평가 ===")
        print("\n[System Prompt]:")
        print(messages[0].content)
        print("\n[User Prompt]:")
        print(messages[1].content)

        # 최대 3번까지 시도
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = llm.invoke(messages).content
                
                print("\n[LLM Response]:")
                print(result)
                print("\n" + "="*50)

                # LLM 응답 저장
                state["llm_response_3"] = result

                # JSON 응답 파싱
                if result.startswith("```json"):
                    result = result[7:]
                if result.startswith("```"):
                    result = result[3:]
                if result.endswith("```"):
                    result = result[:-3]
                
                # JSON 형식 정리
                result = result.strip()
                if not result.startswith("{"):
                    result = "{" + result
                if not result.endswith("}"):
                    result = result + "}"
                
                # 중괄호 쌍이 맞는지 확인
                open_braces = result.count("{")
                close_braces = result.count("}")
                if open_braces > close_braces:
                    result = result + "}" * (open_braces - close_braces)
                elif close_braces > open_braces:
                    result = "{" * (close_braces - open_braces) + result
                
                # JSON 파싱 시도
                evaluation = json.loads(result)
                
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
                
                return state

            except (json.JSONDecodeError, ValueError) as e:
                print(f"\n파싱 시도 {attempt + 1} 실패: {str(e)}")
                if attempt == max_retries - 1:  # 마지막 시도에서도 실패
                    st.error(f"중요도 평가 결과 파싱 중 오류가 발생했습니다: {str(e)}")
                    st.error(f"원본 응답: {result}")
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
        "original_news_data": []
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
