from typing import List, TypedDict

# 상태 타입 정의
class AgentState(TypedDict):
    news_data: List[dict]
    filtered_news: List[dict]
    analysis: str
    keyword: str
    prompt: str

# 뉴스 수집기 함수 (더미 데이터 사용)
def collect_news(state: AgentState) -> AgentState:
    dummy_news = [
        {"content": "삼성전자, 역대 최대 분기 실적 달성", "url": "https://example.com/1", "date": "2025-04-15"},
        {"content": "감사보고서 제출 지연 논란", "url": "https://example.com/2", "date": "2025-04-14"},
        {"content": "반도체 AI 투자 확대 발표", "url": "https://example.com/3", "date": "2025-04-14"},
    ]
    state["news_data"] = dummy_news
    return state

# 뉴스 필터링 함수 (더미 분석 결과 반환)
def filter_news(state: AgentState) -> AgentState:
    filtered_news = state["news_data"][:2]  # 상위 2개만 필터링했다고 가정
    analysis = (
        "1번 뉴스는 재무성과에 직접적인 영향을 주는 실적 발표 내용이며, "
        "2번 뉴스는 감사 이슈로 회계 리스크에 해당됩니다."
    )

    return {
        "news_data": state["news_data"],
        "filtered_news": filtered_news,
        "analysis": analysis,
        "keyword": state.get("keyword", "삼성전자"),
        "prompt": state.get("prompt", "")
    }
