import feedparser
from urllib.parse import quote
from typing import List, Dict, Optional


class GoogleNews:
    """
    구글 뉴스를 검색하고 결과를 반환하는 클래스입니다.
    """

    def __init__(self):
        """GoogleNews 클래스를 초기화합니다."""
        self.base_url = "https://news.google.com/rss"

    def search_by_keyword(self, keyword: Optional[str] = None, k: int = 20) -> List[Dict[str, str]]:
        """
        키워드로 뉴스를 검색합니다.

        Args:
            keyword (Optional[str]): 검색할 키워드 (기본값: None)
            k (int): 검색할 뉴스의 최대 개수 (기본값: 20)

        Returns:
            List[Dict[str, str]]: URL, 제목, 언론사, 발행일을 포함한 딕셔너리 리스트
        """
        # URL 생성
        if keyword:
            encoded_keyword = quote(keyword)
            url = f"{self.base_url}/search?q={encoded_keyword}&hl=ko&gl=KR&ceid=KR:ko"
        else:
            url = f"{self.base_url}?hl=ko&gl=KR&ceid=KR:ko"
        
        # 뉴스 데이터 파싱
        news_data = feedparser.parse(url)
        
        # 수집된 뉴스가 없는 경우
        if not news_data.entries:
            print(f"'{keyword}' 관련 뉴스를 찾을 수 없습니다.")
            return []
            
        # 결과 가공
        result = []
        for entry in news_data.entries[:k]:
            # 뉴스 제목에서 언론사 추출 (예: "제목 - 언론사명" 형식)
            title = entry.title
            press = "알 수 없음"
            
            # "-" 또는 "–"로 구분된 경우
            if " - " in title:
                parts = title.split(" - ")
                if len(parts) > 1:
                    press = parts[-1].strip()
                    title = " - ".join(parts[:-1]).strip()
            elif " – " in title:
                parts = title.split(" – ")
                if len(parts) > 1:
                    press = parts[-1].strip()
                    title = " – ".join(parts[:-1]).strip()

            result.append({
                "url": entry.link, 
                "content": title,
                "press": press,
                "date": entry.get('published', '날짜 정보 없음')
            })

        return result
