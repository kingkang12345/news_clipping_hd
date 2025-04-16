from typing import List, Dict, Any, TypedDict
from langchain_core.messages import HumanMessage, AIMessage
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
    prompt: str

# 뉴스 수집기 함수
def collect_news(state: AgentState) -> AgentState:
    """뉴스를 수집하는 함수"""
    try:
        # 검색어 설정
        keyword = state.get("keyword", "삼성전자")
        
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

# 뉴스 필터링 함수
def filter_news(state: AgentState) -> AgentState:
    llm = ChatOpenAI(temperature=0)
    
    # 전일과 오늘 날짜 기준으로 필터링
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    
    # 날짜 형식 변환 함수
    def is_recent_news(date_str):
        if not date_str or date_str == '날짜 정보 없음':
            return True  # 날짜 정보가 없는 경우는 포함
        
        try:
            # 다양한 날짜 포맷 처리 시도
            formats = [
                '%a, %d %b %Y %H:%M:%S %z',  # RFC 2822 포맷
                '%a, %d %b %Y %H:%M:%S GMT',
                '%Y-%m-%d %H:%M:%S',
                '%Y년 %m월 %d일'
            ]
            
            parsed_date = None
            for fmt in formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
            
            if not parsed_date:
                return True  # 파싱 실패시 포함
                
            # 시간대 정보가 없는 경우 현지 시간으로 간주
            return parsed_date.date() >= yesterday.date()
            
        except Exception:
            return True  # 파싱 오류 시 포함
    
    # 전일, 오늘 뉴스만 필터링
    recent_news = [news for news in state["news_data"] if is_recent_news(news.get('date'))]
    
    # 뉴스가 없으면 원본 데이터 사용
    if not recent_news:
        recent_news = state["news_data"]
    
    # 회계법인 관점의 분석 프롬프트
    custom_prompt = state.get("prompt", "")
    
    # 사용자 정의 프롬프트가 없으면 기본 프롬프트 사용
    if not custom_prompt:
        prompt = """
        당신은 회계법인의 전문 애널리스트입니다. 다음 뉴스들을 분석해서 회계법인 관점에서 가장 중요한 3개의 뉴스를 선택해주세요.
        
        선택 기준:
        1. 재무상태나 실적 관련 정보
        2. 회계 이슈나 감사 관련 정보
        3. 기업가치 평가에 영향을 미치는 정보
        4. 투자나 인수합병 관련 정보
        
        각 선택한 뉴스에 대해 선택한 이유를 명확히 설명해주세요.
        
        응답 형식:
        선택된 뉴스 인덱스: [1, 2, 3] 와 같은 형식으로 먼저 알려주세요.
        그 다음 각 선택에 대한 이유를 설명해주세요.
        
        뉴스 목록:
        {news_list}
        """
    else:
        # 커스텀 프롬프트에 뉴스 목록 추가
        prompt = custom_prompt + "\n\n뉴스 목록:\n{news_list}"
    
    news_text = "\n".join([f"{i}. 제목: {news['content']}\nURL: {news['url']}\n날짜: {news.get('date', '날짜 정보 없음')}\n" 
                          for i, news in enumerate(recent_news)])
    
    response = llm.invoke([HumanMessage(content=prompt.format(news_list=news_text))])
    
    # LLM 응답에서 인덱스 추출
    try:
        # 정규식을 사용하여 [0, 1, 2]와 같은 형식의 인덱스 리스트를 찾음
        index_match = re.search(r'\[([\d\s,]+)\]', response.content)
        if index_match:
            selected_indices = [int(idx.strip()) for idx in index_match.group(1).split(',')]
        else:
            selected_indices = [0, 1, 2]  # 기본값
    except Exception as e:
        print(f"인덱스 파싱 오류: {e}")
        selected_indices = [0, 1, 2]  # 파싱 실패시 기본값
    
    # 인덱스가 범위를 벗어나지 않도록 확인
    valid_indices = [i for i in selected_indices if i < len(recent_news)]
    
    # 선택된 뉴스 가져오기
    filtered_news = [recent_news[i] for i in valid_indices]
    
    # 상태 업데이트
    return {
        "news_data": state["news_data"],
        "filtered_news": filtered_news,
        "analysis": response.content,
        "keyword": state.get("keyword", "삼성전자"),
        "prompt": state.get("prompt", "")
    }

# 노드 정의
def get_nodes():
    return {
        "collect_news": collect_news,
        "filter_news": filter_news
    }

# 에지 정의
def get_edges():
    return [
        ("collect_news", "filter_news"),
        ("filter_news", END)
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
    result = graph.invoke({"news_data": [], "filtered_news": [], "analysis": "", "keyword": "삼성전자", "prompt": ""})
    
    # 전체 뉴스 목록 출력
    print_news(result["news_data"], "전체 뉴스 (20개)")
    
    # 분석 결과 출력
    print("\n\n=== 회계법인 관점의 분석 결과 ===")
    print(result["analysis"])
    
    # 선별된 뉴스 출력
    print_news(result["filtered_news"], "회계법인 관점의 주요 뉴스 (3개)")

if __name__ == "__main__":
    main()
