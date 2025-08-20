import feedparser
from urllib.parse import quote
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


class GoogleNews:
    """
    구글 뉴스를 검색하고 결과를 반환하는 클래스입니다.
    """

    def __init__(self):
        """GoogleNews 클래스를 초기화합니다."""
        self.base_url = "https://news.google.com/rss"
        
        # 지역별 설정 (현대자동차 남양연구소 우선순위 기준: 북미→서유럽→중국→아태→브라질→한국)
        self.regions = {
            "한국": {"hl": "ko", "gl": "KR", "ceid": "KR:ko"},
            "미국": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
            "독일": {"hl": "de", "gl": "DE", "ceid": "DE:de"},
            "중국": {"hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"},
            "일본": {"hl": "ja", "gl": "JP", "ceid": "JP:ja"},
            "영국": {"hl": "en-GB", "gl": "GB", "ceid": "GB:en"},
            #"프랑스": {"hl": "fr", "gl": "FR", "ceid": "FR:fr"},
            #"이탈리아": {"hl": "it", "gl": "IT", "ceid": "IT:it"},
            #"캐나다": {"hl": "en-CA", "gl": "CA", "ceid": "CA:en"},
            #"브라질": {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"},
            "인도": {"hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
            #"인도네시아": {"hl": "id", "gl": "ID", "ceid": "ID:id"},
            "글로벌": {"hl": "en", "gl": "US", "ceid": "US:en"}  # 기본 글로벌 설정
        }

    def search_by_keyword(self, keyword: Optional[str] = None, k: int = 20, region: str = "한국", timeout: int = 10) -> List[Dict[str, str]]:
        """
        키워드로 뉴스를 검색합니다.

        Args:
            keyword (Optional[str]): 검색할 키워드 (기본값: None)
            k (int): 검색할 뉴스의 최대 개수 (기본값: 20)
            region (str): 검색할 지역 (기본값: "한국")
            timeout (int): HTTP 요청 타임아웃 (기본값: 10초)

        Returns:
            List[Dict[str, str]]: URL, 제목, 언론사, 발행일, 지역을 포함한 딕셔너리 리스트
        """
        # 지역 설정 확인
        if region not in self.regions:
            print(f"지원하지 않는 지역입니다: {region}. 기본값 '한국'을 사용합니다.")
            region = "한국"
        
        region_config = self.regions[region]
        
        # URL 생성
        if keyword:
            encoded_keyword = quote(keyword)
            url = f"{self.base_url}/search?q={encoded_keyword}&hl={region_config['hl']}&gl={region_config['gl']}&ceid={region_config['ceid']}"
        else:
            url = f"{self.base_url}?hl={region_config['hl']}&gl={region_config['gl']}&ceid={region_config['ceid']}"
        
        # 뉴스 데이터 파싱 (타임아웃 적용)
        try:
            # feedparser에는 직접적인 timeout 옵션이 없으므로 전체 작업에 대한 timeout 처리
            start_time = time.time()
            news_data = feedparser.parse(url)
            
            # 타임아웃 체크
            if time.time() - start_time > timeout:
                print(f"'{keyword}' 검색이 {region}에서 타임아웃되었습니다.")
                return []
                
        except Exception as e:
            print(f"'{keyword}' 검색 중 {region}에서 오류 발생: {e}")
            return []
        
        # 수집된 뉴스가 없는 경우
        if not news_data.entries:
            print(f"'{keyword}' 관련 뉴스를 {region}에서 찾을 수 없습니다.")
            return []
            
        # 결과 가공
        result = []
        for entry in news_data.entries[:k]:
            # source 태그에서 직접 언론사 정보 추출
            press = entry.get('source', {}).get('title', '알 수 없음')
            
            result.append({
                "url": entry.link, 
                "content": entry.title,  # 제목은 그대로 사용
                "press": press,
                "date": entry.get('published', '날짜 정보 없음'),
                "region": region  # 지역 정보 추가
            })

        return result
    
    def _search_single_region_worker(self, args) -> List[Dict[str, str]]:
        """
        단일 지역 검색을 위한 워커 함수 (병렬 처리용)
        
        Args:
            args: (keyword, k, region, timeout) 튜플
            
        Returns:
            List[Dict[str, str]]: 해당 지역의 뉴스 리스트
        """
        keyword, k, region, timeout = args
        try:
            return self.search_by_keyword(keyword, k, region, timeout)
        except Exception as e:
            print(f"{region} 검색 중 오류 발생: {e}")
            return []

    def search_multi_region(self, keyword: Optional[str] = None, k: int = 20, regions: List[str] = None, parallel: bool = True, max_workers: int = 6, timeout: int = 10) -> List[Dict[str, str]]:
        """
        여러 지역에서 키워드로 뉴스를 검색합니다.

        Args:
            keyword (Optional[str]): 검색할 키워드 (기본값: None)
            k (int): 각 지역별 검색할 뉴스의 최대 개수 (기본값: 20)
            regions (List[str]): 검색할 지역 리스트 (기본값: ["한국", "미국", "독일", "중국"])
            parallel (bool): 병렬 처리 사용 여부 (기본값: True)
            max_workers (int): 최대 동시 스레드 수 (기본값: 6)
            timeout (int): 각 지역별 검색 타임아웃 (기본값: 10초)

        Returns:
            List[Dict[str, str]]: 모든 지역의 뉴스를 합친 리스트
        """
        if regions is None:
            # 현대자동차 남양연구소 우선순위 기준 기본 지역
            regions = ["한국", "미국", "독일", "중국", "일본", "인도"]
        
        all_results = []
        
        if parallel and len(regions) > 1:
            # 병렬 처리
            print(f"병렬 처리로 {len(regions)}개 지역에서 '{keyword}' 검색 시작 (최대 {max_workers}개 스레드)")
            start_time = time.time()
            
            # 각 지역별 검색 파라미터 준비
            search_args = [(keyword, k, region, timeout) for region in regions]
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 모든 지역 검색을 병렬로 실행
                future_to_region = {
                    executor.submit(self._search_single_region_worker, args): args[2] 
                    for args in search_args
                }
                
                # 완료된 작업부터 결과 수집
                for future in as_completed(future_to_region):
                    region = future_to_region[future]
                    try:
                        region_results = future.result()
                        all_results.extend(region_results)
                        print(f"{region}: {len(region_results)}개 뉴스 수집 완료")
                    except Exception as e:
                        print(f"{region} 검색 중 오류 발생: {e}")
            
            elapsed_time = time.time() - start_time
            print(f"병렬 검색 완료: 총 {len(all_results)}개 뉴스, 소요시간 {elapsed_time:.2f}초")
            
        else:
            # 순차 처리 (기존 방식)
            print(f"순차 처리로 {len(regions)}개 지역에서 '{keyword}' 검색 시작")
            start_time = time.time()
            
            for region in regions:
                try:
                    region_results = self.search_by_keyword(keyword, k, region, timeout)
                    all_results.extend(region_results)
                    print(f"{region}: {len(region_results)}개 뉴스 수집")
                except Exception as e:
                    print(f"{region} 검색 중 오류 발생: {e}")
                    continue
            
            elapsed_time = time.time() - start_time
            print(f"순차 검색 완료: 총 {len(all_results)}개 뉴스, 소요시간 {elapsed_time:.2f}초")
        
        return all_results
    
    def search_priority_regions(self, keyword: Optional[str] = None, k: int = 20, parallel: bool = True, max_workers: int = 6, timeout: int = 10) -> List[Dict[str, str]]:
        """
        현대자동차 남양연구소 우선순위 지역에서 뉴스를 검색합니다.
        우선순위: 북미→서유럽→중국→아태→브라질→한국

        Args:
            keyword (Optional[str]): 검색할 키워드 (기본값: None)
            k (int): 각 지역별 검색할 뉴스의 최대 개수 (기본값: 20)
            parallel (bool): 병렬 처리 사용 여부 (기본값: True)
            max_workers (int): 최대 동시 스레드 수 (기본값: 6)
            timeout (int): 각 지역별 검색 타임아웃 (기본값: 10초)

        Returns:
            List[Dict[str, str]]: 우선순위 지역의 뉴스를 합친 리스트
        """
        priority_regions = [
            "미국",  # 북미
            "독일", "영국",  # 서유럽
            "중국",  # 중국
            "일본", "인도",  # 아태
            "한국"  # 한국
        ]
        
        return self.search_multi_region(keyword, k, priority_regions, parallel, max_workers, timeout)
    
    def search_multiple_keywords(self, keywords: List[str], k: int = 20, regions: List[str] = None, parallel: bool = True, max_workers: int = 8, timeout: int = 10) -> Dict[str, List[Dict[str, str]]]:
        """
        여러 키워드를 병렬로 검색합니다.

        Args:
            keywords (List[str]): 검색할 키워드 리스트
            k (int): 각 키워드별 뉴스의 최대 개수 (기본값: 20)
            regions (List[str]): 검색할 지역 리스트 (기본값: 우선순위 지역)
            parallel (bool): 병렬 처리 사용 여부 (기본값: True)
            max_workers (int): 최대 동시 스레드 수 (기본값: 8)
            timeout (int): 각 키워드별 검색 타임아웃 (기본값: 10초)

        Returns:
            Dict[str, List[Dict[str, str]]]: 키워드별 뉴스 딕셔너리
        """
        if not keywords:
            return {}
            
        if regions is None:
            regions = ["한국", "미국", "독일", "중국", "일본", "인도"]
        
        results = {}
        
        if parallel and len(keywords) > 1:
            # 키워드별 병렬 처리
            print(f"키워드별 병렬 처리로 {len(keywords)}개 키워드 검색 시작 (최대 {max_workers}개 스레드)")
            start_time = time.time()
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 각 키워드별로 멀티 지역 검색을 병렬 실행
                future_to_keyword = {
                    executor.submit(self.search_multi_region, keyword, k, regions, True, max_workers//2, timeout): keyword 
                    for keyword in keywords
                }
                
                # 완료된 작업부터 결과 수집
                for future in as_completed(future_to_keyword):
                    keyword = future_to_keyword[future]
                    try:
                        keyword_results = future.result()
                        results[keyword] = keyword_results
                        print(f"'{keyword}': {len(keyword_results)}개 뉴스 수집 완료")
                    except Exception as e:
                        print(f"'{keyword}' 검색 중 오류 발생: {e}")
                        results[keyword] = []
            
            elapsed_time = time.time() - start_time
            total_news = sum(len(news_list) for news_list in results.values())
            print(f"키워드별 병렬 검색 완료: 총 {total_news}개 뉴스, 소요시간 {elapsed_time:.2f}초")
            
        else:
            # 순차 처리
            print(f"순차 처리로 {len(keywords)}개 키워드 검색 시작")
            start_time = time.time()
            
            for keyword in keywords:
                try:
                    keyword_results = self.search_multi_region(keyword, k, regions, parallel, max_workers, timeout)
                    results[keyword] = keyword_results
                    print(f"'{keyword}': {len(keyword_results)}개 뉴스 수집")
                except Exception as e:
                    print(f"'{keyword}' 검색 중 오류 발생: {e}")
                    results[keyword] = []
            
            elapsed_time = time.time() - start_time
            total_news = sum(len(news_list) for news_list in results.values())
            print(f"키워드별 순차 검색 완료: 총 {total_news}개 뉴스, 소요시간 {elapsed_time:.2f}초")
        
        return results
    
    def get_available_regions(self) -> List[str]:
        """
        사용 가능한 지역 목록을 반환합니다.

        Returns:
            List[str]: 사용 가능한 지역 목록
        """
        return list(self.regions.keys())


# 사용 예시
if __name__ == "__main__":
    # 테스트 코드
    gn = GoogleNews()
    
    print("=== 사용 가능한 지역 ===")
    print(gn.get_available_regions())
    
    print("\n=== 한국에서 현대차 검색 ===")
    korean_news = gn.search_by_keyword("현대차", k=3, region="한국")
    for news in korean_news:
        print(f"[{news['region']}] {news['content']} - {news['press']}")
    
    print("\n=== 미국에서 Hyundai 검색 ===")
    us_news = gn.search_by_keyword("Hyundai", k=3, region="미국")
    for news in us_news:
        print(f"[{news['region']}] {news['content']} - {news['press']}")
    
    print("\n=== 우선순위 지역에서 전기차기술 검색 (각 지역 2개씩) - 병렬 처리 ===")
    priority_news = gn.search_priority_regions("전기차기술", k=2, parallel=True, max_workers=4)
    print(f"총 {len(priority_news)}개 뉴스 수집")
    for news in priority_news[:10]:  # 상위 10개만 출력
        print(f"[{news['region']}] {news['content']} - {news['press']}")
    
    print("\n=== 다중 키워드 병렬 검색 테스트 ===")
    keywords = ["현대자동차", "전기차", "수소차"]
    multi_results = gn.search_multiple_keywords(keywords, k=2, parallel=True, max_workers=6)
    for keyword, news_list in multi_results.items():
        print(f"\n'{keyword}' 관련 뉴스 {len(news_list)}개:")
        for news in news_list[:3]:  # 상위 3개만 출력
            print(f"  [{news['region']}] {news['content']} - {news['press']}")
