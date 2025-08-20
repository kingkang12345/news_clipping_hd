import requests
import time
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

class ImprovedNewsExtractor:
    """조선일보 및 기타 언론사 최적화 추출기"""
    
    def __init__(self):
        self.session = requests.Session()
        # 더 강력한 헤더 설정
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        })
        
        # 조선일보 전용 다중 셀렉터
        self.chosun_selectors = {
            'title': [
                'h1.article-header__headline',
                'h1.news_title_text',
                '.article-title h1',
                'h1[class*="title"]',
                '.headline h1',
                '.news-headline',
                'h1'  # 마지막 폴백
            ],
            'content': [
                'div.article-body',
                'div.news_text_area', 
                '.article-content',
                '#article_body',
                '.article-text',
                '.news-content',
                '.content-body',
                'div[class*="content"]',
                'div[class*="article"]'
            ],
            'date': [
                'time.article-header__date',
                'span.news_date',
                '.date',
                'time',
                '[datetime]'
            ]
        }
    
    def extract_chosun_biz_advanced(self, url):
        """조선일보 비즈 고급 추출기"""
        print(f"🏢 조선일보 비즈 전용 추출기 실행: {url}")
        
        try:
            # 1단계: 일반 요청
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 제목 추출
            title = self._extract_with_selectors(soup, self.chosun_selectors['title'])
            print(f"📰 추출된 제목: {title[:100] if title else 'None'}...")
            
            # 본문 추출
            content = self._extract_content_advanced(soup)
            print(f"📄 추출된 본문 길이: {len(content) if content else 0}자")
            
            # 발행일 추출
            date = self._extract_with_selectors(soup, self.chosun_selectors['date'])
            
            if title and content and len(content) > 200:
                return {
                    'title': title,
                    'content': content,
                    'publish_date': date,
                    'url': url,
                    'method': '조선일보 전용 파서',
                    'confidence': 0.9,
                    'success': True
                }
            else:
                print("⚠️ 추출 결과 부족 - Selenium 시도 필요")
                return self._extract_with_selenium_advanced(url)
                
        except Exception as e:
            print(f"❌ 일반 요청 실패: {e}")
            return self._extract_with_selenium_advanced(url)
    
    def _extract_with_selectors(self, soup, selectors):
        """다중 셀렉터로 텍스트 추출"""
        for selector in selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text().strip()
                    if text and len(text) > 10:
                        return text
            except Exception:
                continue
        return None
    
    def _extract_content_advanced(self, soup):
        """고급 본문 추출"""
        for selector in self.chosun_selectors['content']:
            try:
                element = soup.select_one(selector)
                if element:
                    # 불필요한 요소 제거
                    for unwanted in element.find_all(['script', 'style', 'nav', 'header', 'footer', 
                                                     '.ad', '.advertisement', '.related', '.comment',
                                                     '[class*="ad"]', '[id*="ad"]']):
                        unwanted.decompose()
                    
                    # 텍스트 추출 및 정제
                    text = element.get_text(separator='\n', strip=True)
                    
                    # 의미있는 문장만 필터링
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    meaningful_lines = [line for line in lines if len(line) > 20 and not self._is_junk_line(line)]
                    
                    if len(meaningful_lines) >= 3:
                        return '\n\n'.join(meaningful_lines)
                        
            except Exception as e:
                continue
        
        # 폴백: 전체 페이지에서 본문 추정
        return self._fallback_content_extraction(soup)
    
    def _is_junk_line(self, line):
        """쓸모없는 라인 판별"""
        junk_patterns = [
            r'^\s*\d+\s*$',  # 숫자만
            r'^\s*[^\w\s]*\s*$',  # 특수문자만
            r'관련\s*기사',
            r'더\s*보기',
            r'이전\s*기사',
            r'다음\s*기사',
            r'^\s*AD\s*$',
            r'광고',
            r'구독',
            r'로그인',
            r'회원가입'
        ]
        
        for pattern in junk_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False
    
    def _fallback_content_extraction(self, soup):
        """폴백 본문 추출"""
        # 가장 긴 텍스트 블록 찾기
        all_divs = soup.find_all(['div', 'article', 'section', 'main'])
        best_content = ""
        
        for div in all_divs:
            text = div.get_text().strip()
            if len(text) > len(best_content) and len(text) > 300:
                # 너무 많은 링크가 있으면 스킵
                links = div.find_all('a')
                if len(links) < len(text) / 100:  # 텍스트 100자당 링크 1개 미만
                    best_content = text
        
        return best_content
    
    def _extract_with_selenium_advanced(self, url):
        """고급 Selenium 추출"""
        print("🌐 Selenium 고급 모드로 재시도...")
        
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        
        # Google 관련 에러 방지
        options.add_argument('--disable-background-networking')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-backgrounding-occluded-windows')
        options.add_argument('--disable-breakpad')
        options.add_argument('--disable-client-side-phishing-detection')
        options.add_argument('--disable-component-extensions-with-background-pages')
        options.add_argument('--disable-default-apps')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-hang-monitor')
        options.add_argument('--disable-ipc-flooding-protection')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-prompt-on-repost')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-sync')
        options.add_argument('--force-fieldtrials=*BackgroundTracing/default/')
        options.add_argument('--metrics-recording-only')
        options.add_argument('--no-crash-upload')
        options.add_argument('--no-first-run')
        
        options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 2
        })
        
        driver = None
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
            # 추가 스크립트로 봇 탐지 우회
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            print("🌐 페이지 로딩 중...")
            driver.get(url)
            
            # 페이지 완전 로딩 대기
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # 추가 대기 (동적 콘텐츠)
            time.sleep(3)
            
            # 스크롤해서 모든 콘텐츠 로딩
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            # 제목 추출
            title = self._extract_with_selectors(soup, self.chosun_selectors['title'])
            
            # 본문 추출
            content = self._extract_content_advanced(soup)
            
            if title and content and len(content) > 200:
                print("✅ Selenium으로 성공적 추출!")
                return {
                    'title': title,
                    'content': content,
                    'url': url,
                    'method': 'Selenium 고급 모드',
                    'confidence': 0.85,
                    'success': True
                }
            else:
                print("❌ Selenium으로도 충분한 내용 추출 실패")
                return {
                    'title': title or "제목 추출 실패",
                    'content': content or "본문 추출 실패",
                    'url': url,
                    'method': 'Selenium (부분 실패)',
                    'confidence': 0.3,
                    'success': False,
                    'error': 'Insufficient content extracted'
                }
                
        except Exception as e:
            print(f"❌ Selenium 실패: {e}")
            return {
                'url': url,
                'method': 'Selenium 실패',
                'success': False,
                'error': str(e)
            }
        finally:
            if driver:
                driver.quit()

# 테스트 코드
if __name__ == "__main__":
    extractor = ImprovedNewsExtractor()
    
    # 조선일보 테스트
    chosun_url = "https://biz.chosun.com/stock/finance/2025/08/19/AMZGKTJ4FFFBZF6VOYDZVJ3V2U/"
    
    print("🚀 조선일보 비즈 고급 추출기 테스트 시작")
    print("="*80)
    
    result = extractor.extract_chosun_biz_advanced(chosun_url)
    
    print("\n📊 결과:")
    print("="*80)
    if result.get('success'):
        print(f"✅ 성공: {result['method']}")
        print(f"📰 제목: {result['title']}")
        print(f"📄 본문 길이: {len(result['content'])}자")
        print(f"📄 본문 미리보기: {result['content'][:200]}...")
        print(f"🎯 신뢰도: {result['confidence']*100}%")
    else:
        print(f"❌ 실패: {result.get('error', '알 수 없는 오류')}")
        print(f"🔧 시도한 방법: {result.get('method', 'N/A')}")
