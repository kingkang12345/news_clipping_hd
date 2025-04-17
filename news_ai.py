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

# 뉴스 수집기 함수
def collect_news(state: AgentState) -> AgentState:
    """뉴스를 수집하는 함수"""
    try:
        # 검색어 설정
        keyword = state.get("keyword", "삼성")
        
        # 검색 결과 수 설정
        max_results = state.get("max_results", 20)
        
        # GoogleNews 객체 생성
        news = GoogleNews()
        
        # 뉴스 검색
        news_data = news.search_by_keyword(keyword, k=max_results)
        
        # 뉴스 데이터 저장
        state["news_data"] = news_data
        
        return state
    except Exception as e:
        print(f"뉴스 수집 중 오류 발생: {e}")
        return state

# 1단계: 뉴스 제외 판단
def filter_excluded_news(state: AgentState) -> AgentState:
    """뉴스를 제외/보류/유지로 분류하는 함수"""
    try:
        news_data = state.get("news_data", [])
        if not news_data:
            return state

        # 뉴스 데이터를 문자열로 변환 (원본 그대로 전달)
        news_text = "\n\n".join([
            f"인덱스: {i}\n제목: {news['content']}\nURL: {news['url']}\n발행일: {news['date']}"
            for i, news in enumerate(news_data, 1)
        ])

        # LLM 호출
        llm = ChatOpenAI(
            model_name=state.get("model", "gpt-4o"),
            temperature=0.1,
            max_tokens=2000
        )

        # 제외 판단 프롬프트
        exclusion_prompt = f"""아래 뉴스 제목들을 분석하여, 제외 기준에 따라 제거할 뉴스들을 분류해 주세요.
단, 제외 기준에 형식적으로는 해당하지만 중요한 정보일 수도 있는 경우, "보류"로 따로 구분하고 이유를 적어주세요.

[뉴스 목록]
{news_text}

[제외 기준]
{state.get("exclusion_criteria", "")}

[유효 언론사]
{state.get("valid_press", "")}

다음과 같은 JSON 형식으로 응답해주세요:
{{
  "excluded": [
    {{ "index": 3, "title": "...", "reason": "단순 CSR 캠페인 홍보 기사" }}
  ],
  "borderline": [
    {{ "index": 5, "title": "...", "reason": "신제품 출시지만 핵심 사업 전략과 관련 있음" }}
  ],
  "retain": [
    {{ "index": 1, "title": "...", "reason": "회계 감리 결과 관련 기사" }}
  ]
}}"""

        messages = [
            SystemMessage(content=state.get("system_prompt_1", "당신은 회계법인의 뉴스 분석 전문가입니다. 뉴스의 중요성을 판단하여 제외/보류/유지로 분류하는 작업을 수행합니다. 특히 회계법인의 관점에서 중요하지 않은 뉴스(예: 단순 홍보, CSR 활동, 이벤트 등)를 식별하고, 회계 감리나 재무 관련 이슈는 반드시 유지하도록 합니다.")),
            HumanMessage(content=exclusion_prompt)
        ]

        # 프롬프트와 응답 저장
        state["system_prompt_1"] = messages[0].content
        state["user_prompt_1"] = messages[1].content

        print("\n=== 1단계: 제외 판단 ===")
        print("\n[System Prompt]:")
        print(messages[0].content)
        print("\n[User Prompt]:")
        print(messages[1].content)

        result = llm.invoke(messages).content
        
        print("\n[LLM Response]:")
        print(result)
        print("\n" + "="*50)

        # LLM 응답 저장
        state["llm_response_1"] = result

        try:
            # JSON 응답 파싱
            if result.startswith("```json"):
                result = result[7:]
            if result.startswith("```"):
                result = result[3:]
            if result.endswith("```"):
                result = result[:-3]
            
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                st.error("분류 결과가 JSON 형식이 아닙니다.")
                return state
            
            classification = json.loads(result[json_start:json_end])
            
            # 상태 업데이트
            state["excluded_news"] = classification.get("excluded", [])
            state["borderline_news"] = classification.get("borderline", [])
            state["retained_news"] = classification.get("retain", [])
            
        except json.JSONDecodeError as e:
            st.error(f"분류 결과 파싱 중 오류가 발생했습니다: {str(e)}")
            st.error(f"원본 응답: {result}")
            return state

        return state

    except Exception as e:
        st.error(f"뉴스 분류 중 오류가 발생했습니다: {str(e)}")
        return state

# 2단계: 뉴스 그룹핑 + 대표 기사 선택
def group_and_select_news(state: AgentState) -> AgentState:
    """유사한 뉴스를 그룹화하고 대표 기사를 선택하는 함수"""
    try:
        # 유지 및 보류 뉴스 합치기
        retained_indices = [news["index"] for news in state["retained_news"]]
        borderline_indices = [news["index"] for news in state["borderline_news"]]
        target_indices = retained_indices + borderline_indices
        
        # 대상 뉴스 필터링
        target_news = [news for i, news in enumerate(state["news_data"], 1) if i in target_indices]
        
        if not target_news:
            return state

        # 뉴스 데이터를 문자열로 변환
        news_text = "\n\n".join([
            f"인덱스: {i}\n제목: {news['content']}\n언론사: {news.get('press', '알 수 없음')}\n발행일: {news.get('date', '알 수 없음')}"
            for i, news in enumerate(target_news, 1)
        ])

        # LLM 호출
        llm = ChatOpenAI(
            model_name=state.get("model", "gpt-4o"),
            temperature=0.1,
            max_tokens=2000
        )

        # 그룹핑 프롬프트
        grouping_prompt = f"""유사한 뉴스끼리 그룹으로 묶고, 각 그룹에서 가장 대표성 있는 뉴스 1건만 선택해 주세요.

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
            if result.startswith("```json"):
                result = result[7:]
            if result.startswith("```"):
                result = result[3:]
            if result.endswith("```"):
                result = result[:-3]
            
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                st.error("그룹핑 결과가 JSON 형식이 아닙니다.")
                return state
            
            grouping = json.loads(result[json_start:json_end])
            state["grouped_news"] = grouping.get("groups", [])
            
        except json.JSONDecodeError as e:
            st.error(f"그룹핑 결과 파싱 중 오류가 발생했습니다: {str(e)}")
            st.error(f"원본 응답: {result}")
            return state

        return state

    except Exception as e:
        st.error(f"뉴스 그룹핑 중 오류가 발생했습니다: {str(e)}")
        return state

# 3단계: 중요도 평가 + 최종 선정
def evaluate_importance(state: AgentState) -> AgentState:
    """대표 뉴스들의 중요도를 평가하고 최종 선정하는 함수"""
    try:
        # 대표 뉴스 인덱스 추출
        selected_indices = [group["selected_index"] for group in state["grouped_news"]]
        
        # 대표 뉴스 필터링
        selected_news = [news for i, news in enumerate(state["news_data"], 1) if i in selected_indices]
        
        if not selected_news:
            return state

        # 뉴스 데이터를 문자열로 변환
        news_text = "\n\n".join([
            f"인덱스: {i}\n제목: {news['content']}\n언론사: {news.get('press', '알 수 없음')}\n발행일: {news['date']}\nURL: {news['url']}"
            for i, news in enumerate(selected_news, 1)
        ])

        # LLM 호출
        llm = ChatOpenAI(
            model_name=state.get("model", "gpt-4o"),
            temperature=0.1,
            max_tokens=2000
        )

        # 중요도 평가 프롬프트
        evaluation_prompt = f"""아래 기사들에 대해 회계법인의 시각으로 중요도를 평가하고, 그중 중요도 '상' 또는 '중'인 뉴스만 최종 선정해 주세요.

[뉴스 목록]
{news_text}

[선택 기준]
{state.get("selection_criteria", "")}

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
      "url": "기사 URL",
      "press": "언론사명",
      "date": "발행일"
    }}
  ]
}}

[응답 요구사항]
1. importance는 "상" 또는 "중"만 사용
2. reason은 회계법인 관점에서의 중요성을 명확히 설명
3. keywords는 기사의 핵심 키워드 2-3개
4. affiliates는 해당 뉴스와 관련된 계열사명
5. url은 기사의 원본 URL
6. press는 기사의 언론사명
7. date는 기사의 발행일"""

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

        result = llm.invoke(messages).content
        
        print("\n[LLM Response]:")
        print(result)
        print("\n" + "="*50)

        # LLM 응답 저장
        state["llm_response_3"] = result

        try:
            # JSON 응답 파싱
            if result.startswith("```json"):
                result = result[7:]
            if result.startswith("```"):
                result = result[3:]
            if result.endswith("```"):
                result = result[:-3]
            
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                st.error("중요도 평가 결과가 JSON 형식이 아닙니다.")
                return state
            
            evaluation = json.loads(result[json_start:json_end])
            state["final_selection"] = evaluation.get("final_selection", [])
            
            # 최종 선택된 뉴스 필터링
            final_indices = [news["index"] for news in state["final_selection"]]
            state["filtered_news"] = [news for i, news in enumerate(state["news_data"], 1) if i in final_indices]
            
        except json.JSONDecodeError as e:
            st.error(f"중요도 평가 결과 파싱 중 오류가 발생했습니다: {str(e)}")
            st.error(f"원본 응답: {result}")
            return state

        return state

    except Exception as e:
        st.error(f"중요도 평가 중 오류가 발생했습니다: {str(e)}")
        return state

# 노드 정의
def get_nodes():
    return {
        "collect_news": collect_news,
        "filter_excluded_news": filter_excluded_news,
        "group_and_select_news": group_and_select_news,
        "evaluate_importance": evaluate_importance
    }

# 에지 정의
def get_edges():
    return [
        ("collect_news", "filter_excluded_news"),
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
        "llm_response_3": ""
    })
    
    # 전체 뉴스 목록 출력
    print_news(result["news_data"], "전체 뉴스 (20개)")
    
    # 분석 결과 출력
    print("\n\n=== 회계법인 관점의 분석 결과 ===")
    print(result["analysis"])
    
    # 선별된 뉴스 출력
    print_news(result["filtered_news"], "회계법인 관점의 주요 뉴스")

if __name__ == "__main__":
    main()
